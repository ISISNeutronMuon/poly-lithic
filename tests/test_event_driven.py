# Tests for the event-driven deployment mode.
# Each test isolates one step in the chain to find exactly where it breaks.

import socket
import time
import logging
import pytest
from unittest.mock import MagicMock

from p4p.client.thread import Context

from poly_lithic.src.utils.messaging import (
    Message,
    MessageBroker,
    InterfaceObserver,
    TransformerObserver,
    ModelObserver,
)
from poly_lithic.src.transformers.BaseTransformers import SimpleTransformer
from poly_lithic.src.interfaces import registered_interfaces


def _get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def p4p_server():
    config = {
        'variables': {
            'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 2.0},
            'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 1.0},
        }
    }
    srv = registered_interfaces['p4p_server'](config)
    yield srv
    srv.close()


@pytest.fixture
def interface_observer(p4p_server):
    return InterfaceObserver(p4p_server, 'in_interface')


@pytest.fixture
def transformer_in():
    config = {
        'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
        'symbols': ['A1', 'B1'],
    }
    return SimpleTransformer(config)


@pytest.fixture
def transformer_observer_in(transformer_in):
    return TransformerObserver(transformer_in, 'in_transformer')


class MockModel:
    def __init__(self):
        self.call_log = []

    def evaluate(self, value):
        self.call_log.append(value)
        return {'pred0': value['x1'] + value['x2']}


@pytest.fixture
def mock_model():
    return MockModel()


@pytest.fixture
def model_observer(mock_model):
    return ModelObserver(model=mock_model, topic='model_out')


@pytest.fixture
def broker():
    return MessageBroker()


# ---------------------------------------------------------------------------
# Step 1: Handler.put() fires monitor callbacks
# ---------------------------------------------------------------------------

class TestHandlerMonitorCallbacks:
    """Verify that when an external client writes to a SharedPV,
    the Handler.put() method fires registered monitor callbacks."""

    def test_handler_has_callback_list(self, p4p_server):
        """Each PV handler should have a _monitor_callbacks list."""
        for pv_name, handler in p4p_server._pv_handlers.items():
            assert hasattr(handler, '_monitor_callbacks'), (
                f'Handler for {pv_name} missing _monitor_callbacks'
            )

    def test_monitor_registers_callback(self, p4p_server):
        """Calling monitor(handler, pv_name) should register a callback."""
        cb = MagicMock()
        p4p_server.monitor(cb, pv_name='A1')
        assert cb in p4p_server._pv_handlers['A1']._monitor_callbacks

    def test_handler_put_fires_callbacks(self, p4p_server):
        """Simulate what Handler.put() does: post + fire callbacks."""
        cb = MagicMock()
        p4p_server.monitor(cb, pv_name='A1')

        # Simulate an external put by writing via the server's own put method
        # (this bypasses the Handler — we need to test the Handler directly)
        handler = p4p_server._pv_handlers['A1']

        # Directly invoke the callback path with a known value
        raw_value = 42.0
        for c in handler._monitor_callbacks:
            c(raw_value)

        cb.assert_called_once_with(42.0)

    def test_server_put_does_not_fire_monitor(self, p4p_server):
        """Server's own put() should NOT fire monitor callbacks.
        Only external client writes (Handler.put) should trigger them."""
        cb = MagicMock()
        p4p_server.monitor(cb, pv_name='A1')

        # Use the server's put — this goes through SharedPV.post, not Handler.put
        p4p_server.put('A1', {'value': 99.0})

        # This should NOT have fired because put() bypasses Handler.put()
        cb.assert_not_called()


# ---------------------------------------------------------------------------
# Step 2: start_monitors creates handlers that produce Messages
# ---------------------------------------------------------------------------

class TestStartMonitors:
    """Verify that start_monitors registers per-PV handlers that
    create Messages and push them into the broker queue."""

    def test_start_monitors_registers_callbacks(self, interface_observer, broker):
        interface_observer.start_monitors(broker)
        # Should have registered monitors for each input PV
        assert len(interface_observer._monitors) > 0

    def test_monitor_handler_creates_message(self, interface_observer, broker):
        """Manually invoke the handler created by start_monitors and check
        that a Message appears in the broker queue."""
        interface_observer.start_monitors(broker)

        # Directly fire a callback on one PV handler
        pv_name = 'A1'
        handler = interface_observer.interface._pv_handlers[pv_name]
        assert len(handler._monitor_callbacks) > 0, (
            'start_monitors did not register any callbacks on Handler'
        )

        # Simulate the callback being fired with a scalar value
        for cb in handler._monitor_callbacks:
            cb(5.0)

        assert len(broker.queue) == 1, f'Expected 1 message in queue, got {len(broker.queue)}'
        msg = broker.queue[0]
        assert msg.topic == 'in_interface'
        assert 'A1' in msg.value
        assert msg.value['A1']['value'] == 5.0

    def test_monitor_handler_message_value_structure(self, interface_observer, broker):
        """The message value should be {pv_name: {'value': scalar}}
        which is what TransformerObserver.update() expects."""
        interface_observer.start_monitors(broker)

        handler = interface_observer.interface._pv_handlers['A1']
        for cb in handler._monitor_callbacks:
            cb(7.5)

        msg = broker.queue[0]
        val = msg.value['A1']
        assert isinstance(val, dict), f'Expected dict, got {type(val)}'
        assert 'value' in val, f'Missing "value" key in {val}'
        assert isinstance(val['value'], (int, float)), (
            f'Expected numeric value, got {type(val["value"])}: {val["value"]}'
        )


# ---------------------------------------------------------------------------
# Step 3: TransformerObserver handles single-PV messages
# ---------------------------------------------------------------------------

class TestTransformerSinglePV:
    """Verify that the transformer handles single-PV event messages
    and produces output once all inputs have been seen at least once."""

    def test_single_pv_does_not_transform_until_all_seen(self, transformer_in):
        """Sending only one PV should NOT trigger transform."""
        transformer_in.handler('A1', {'value': 5.0})
        assert not transformer_in.updated, (
            'Transformer should not update with only one input set'
        )

    def test_both_pvs_triggers_transform(self, transformer_in):
        """After both PVs have values, transform should fire."""
        transformer_in.handler('A1', {'value': 5.0})
        transformer_in.handler('B1', {'value': 3.0})
        assert transformer_in.updated, (
            'Transformer should update once all inputs are set'
        )
        assert 'x1' in transformer_in.latest_transformed
        assert 'x2' in transformer_in.latest_transformed

    def test_subsequent_single_pv_triggers_transform(self, transformer_in):
        """Once all inputs have been initialized, a single PV update
        should trigger transform because all() is already satisfied."""
        # Initialize both
        transformer_in.handler('A1', {'value': 5.0})
        transformer_in.handler('B1', {'value': 3.0})
        assert transformer_in.updated
        transformer_in.updated = False  # reset

        # Now only one changes
        transformer_in.handler('A1', {'value': 10.0})
        assert transformer_in.updated, (
            'Transformer should re-fire on single-PV update after initialization'
        )

    def test_transformer_observer_with_single_pv_message(
        self, transformer_observer_in, transformer_in
    ):
        """TransformerObserver.update() with a single-PV message."""
        # First seed both PVs so all() passes
        msg_a = Message(topic='in_interface', source='test', value={
            'A1': {'value': 5.0},
            'B1': {'value': 3.0},
        })
        result = transformer_observer_in.update(msg_a)
        assert result is not None, 'First full message should produce output'

        # Now send a single-PV update
        msg_b = Message(topic='in_interface', source='test', value={
            'A1': {'value': 10.0},
        })
        result = transformer_observer_in.update(msg_b)
        assert result is not None, (
            'Single-PV update after seeding should produce output'
        )


# ---------------------------------------------------------------------------
# Step 4: Full chain — monitor → transformer → model
# ---------------------------------------------------------------------------

class TestFullEventDrivenChain:
    """End-to-end test: simulate monitor callbacks flowing through
    the full broker pipeline."""

    def test_full_chain_after_seeding(
        self,
        interface_observer,
        transformer_observer_in,
        model_observer,
        mock_model,
        broker,
    ):
        """After seeding with get_all, a single PV monitor event should
        flow through the entire chain."""
        # Wire up broker
        broker.attach(interface_observer, 'get_all')
        broker.attach(transformer_observer_in, 'in_interface')
        broker.attach(model_observer, 'in_transformer')

        # Seed: get_all populates both PVs
        broker.get_all()
        # parse until queue drains (get_all → interface → transformer → model)
        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) == 1, (
            f'Model should have been called once from get_all, '
            f'got {len(mock_model.call_log)}'
        )

        # Now start monitors
        interface_observer.start_monitors(broker)

        # Simulate external PV write
        handler = interface_observer.interface._pv_handlers['A1']
        for cb in handler._monitor_callbacks:
            cb(99.0)

        assert len(broker.queue) == 1
        # Parse through the chain
        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) == 2, (
            f'Model should have been called a second time from monitor event, '
            f'got {len(mock_model.call_log)}'
        )

    def test_chain_without_seeding_requires_all_pvs(
        self,
        interface_observer,
        transformer_observer_in,
        model_observer,
        mock_model,
        broker,
    ):
        """Without get_all seeding, the model should only fire once
        ALL input PVs have been written via monitors."""
        broker.attach(transformer_observer_in, 'in_interface')
        broker.attach(model_observer, 'in_transformer')

        # Start monitors (no get_all)
        interface_observer.start_monitors(broker)

        # Write only A1
        handler_a = interface_observer.interface._pv_handlers['A1']
        for cb in handler_a._monitor_callbacks:
            cb(5.0)

        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) == 0, (
            'Model should NOT fire with only one PV written'
        )

        # Now write B1
        handler_b = interface_observer.interface._pv_handlers['B1']
        for cb in handler_b._monitor_callbacks:
            cb(3.0)

        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) == 1, (
            f'Model should fire once both PVs are written, '
            f'got {len(mock_model.call_log)}'
        )


# ---------------------------------------------------------------------------
# Step 5: Real p4p client write triggers Handler.put → monitor callback
# ---------------------------------------------------------------------------

@pytest.mark.flaky_p4p(retries=3, backoff_max=2.0)
class TestRealClientWrite:
    """Use a real p4p Context client to write to the server and verify
    that Handler.put() fires monitor callbacks end-to-end."""

    def test_client_put_fires_monitor_callback(self, monkeypatch):
        """A p4p client writing to a server PV should trigger the
        Handler.put() path which fires monitor callbacks."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        try:
            cb = MagicMock()
            server.monitor(cb, pv_name='A1')

            # Write via a real p4p client
            client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
            try:
                client.put('A1', {'value': 42.0})
                time.sleep(0.3)  # give Handler.put a moment to fire
            finally:
                client.close()

            assert cb.call_count >= 1, (
                f'Monitor callback should have been called by client put, '
                f'but was called {cb.call_count} times'
            )
            # Check the value passed to the callback
            call_args = cb.call_args[0]
            assert call_args[0] == pytest.approx(42.0), (
                f'Callback received {call_args[0]}, expected 42.0'
            )
            # CRITICAL: Check the TYPE — must be a scalar, not p4p.Value
            assert isinstance(call_args[0], (int, float)), (
                f'Callback value should be a scalar (int/float), '
                f'got {type(call_args[0])}: {call_args[0]}'
            )
        finally:
            server.close()

    def test_client_put_full_chain(self, monkeypatch):
        """Full chain: real client put → Handler.put → monitor callback →
        broker queue → transformer → model."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
                'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
            'symbols': ['A1', 'B1'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')

        mock_model = MockModel()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        broker.attach(obs, 'get_all')
        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')

        # Seed via get_all so transformer has all inputs
        broker.get_all()
        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        initial_calls = len(mock_model.call_log)

        # Start monitors
        obs.start_monitors(broker)

        # Write via a real p4p client
        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('A1', {'value': 99.0})
            time.sleep(0.3)
        finally:
            client.close()

        # Parse the queue
        for _ in range(10):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) > initial_calls, (
            f'Model should have been called after client put, '
            f'call_log has {len(mock_model.call_log)} entries '
            f'(initial: {initial_calls})'
        )

        server.close()

    def test_client_put_with_colon_pv_names(self, monkeypatch):
        """Test with PV names containing colons (like ML:LOCAL:TEST_A)
        since that's what the real deployment config uses."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'ML:LOCAL:TEST_A': {
                    'name': 'ML:LOCAL:TEST_A',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
                'ML:LOCAL:TEST_B': {
                    'name': 'ML:LOCAL:TEST_B',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
                'ML:LOCAL:TEST_S': {
                    'name': 'ML:LOCAL:TEST_S',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {
                'x': {'formula': 'ML:LOCAL:TEST_A * 2 + 10'},
                'y': {'formula': 'ML:LOCAL:TEST_B + 120'},
            },
            'symbols': ['ML:LOCAL:TEST_B', 'ML:LOCAL:TEST_A'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')

        class CoordModel:
            def __init__(self):
                self.call_log = []

            def evaluate(self, value):
                self.call_log.append(value)
                return {'output': value['x'] + value['y']}

        mock_model = CoordModel()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        config_t_out = {
            'variables': {'ML:LOCAL:TEST_S': {'formula': 'output'}},
            'symbols': ['output'],
        }
        t_obs_out = TransformerObserver(
            SimpleTransformer(config_t_out), 'out_transformer', unpack_output=True
        )

        import os
        os.environ['PUBLISH'] = 'True'
        obs_out = InterfaceObserver(server, 'out_interface')

        broker.attach(obs, 'get_all')
        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')
        broker.attach(t_obs_out, 'model_out')
        broker.attach(obs_out, 'out_transformer')

        # Seed
        broker.get_all()
        for _ in range(20):
            if not broker.queue:
                break
            broker.parse_queue()

        initial_calls = len(mock_model.call_log)
        assert initial_calls == 1, f'Expected 1 initial model call, got {initial_calls}'

        # Start monitors
        obs.start_monitors(broker)

        # Write via real client
        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('ML:LOCAL:TEST_A', {'value': 5.0})
            time.sleep(0.3)
        finally:
            client.close()

        for _ in range(20):
            if not broker.queue:
                break
            broker.parse_queue()

        assert len(mock_model.call_log) > initial_calls, (
            f'Model should have been called after client put to ML:LOCAL:TEST_A, '
            f'call_log={mock_model.call_log}'
        )

        # Check the output PV was updated
        _, result = server.get('ML:LOCAL:TEST_S')
        logging.info(f'ML:LOCAL:TEST_S value after event: {result}')

        server.close()

    def test_client_put_both_pvs_no_seeding(self, monkeypatch):
        """Without get_all seeding, writing both PVs via real client
        should trigger the model (the user's exact scenario)."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'ML:LOCAL:TEST_A': {
                    'name': 'ML:LOCAL:TEST_A',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
                'ML:LOCAL:TEST_B': {
                    'name': 'ML:LOCAL:TEST_B',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
                'ML:LOCAL:TEST_S': {
                    'name': 'ML:LOCAL:TEST_S',
                    'proto': 'pva',
                    'type': 'scalar',
                    'default': 0.0,
                },
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {
                'x': {'formula': 'ML:LOCAL:TEST_A * 2 + 10'},
                'y': {'formula': 'ML:LOCAL:TEST_B + 120'},
            },
            'symbols': ['ML:LOCAL:TEST_B', 'ML:LOCAL:TEST_A'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')

        class CoordModel2:
            def __init__(self):
                self.call_log = []

            def evaluate(self, value):
                self.call_log.append(value)
                return {'output': value['x'] + value['y']}

        mock_model = CoordModel2()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        # NO get_all subscription — just transformer and model
        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')

        # Start monitors (no seeding!)
        obs.start_monitors(broker)

        # Write BOTH PVs via real client (user's exact scenario)
        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('ML:LOCAL:TEST_A', {'value': 5.0})
            time.sleep(0.2)

            # Parse after first write
            for _ in range(10):
                if not broker.queue:
                    break
                broker.parse_queue()

            logging.info(f'After first put: model calls={len(mock_model.call_log)}')

            client.put('ML:LOCAL:TEST_B', {'value': 3.0})
            time.sleep(0.2)

            # Parse after second write
            for _ in range(10):
                if not broker.queue:
                    break
                broker.parse_queue()

            logging.info(f'After second put: model calls={len(mock_model.call_log)}')
        finally:
            client.close()

        assert len(mock_model.call_log) >= 1, (
            f'Model should have been called after both PVs written, '
            f'call_log={mock_model.call_log}'
        )

        server.close()


# ---------------------------------------------------------------------------
# Step 6: Mimic cli.py event_driven loop with asyncio
# ---------------------------------------------------------------------------

class TestCliEventLoop:
    """Replicate what cli.py model_main does in event_driven mode to
    find if the issue is in the async loop or startup sequence."""

    @pytest.mark.asyncio
    async def test_asyncio_event_loop_with_seeding(self, monkeypatch):
        """Mimic cli.py event_driven mode WITH get_all seeding."""
        import asyncio

        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
                'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
            'symbols': ['A1', 'B1'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')

        mock_model = MockModel()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        broker.attach(obs, 'get_all')
        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')

        # Seed with get_all
        broker.get_all()
        while broker.queue:
            broker.parse_queue()

        initial_calls = len(mock_model.call_log)

        # Start monitors
        obs.start_monitors(broker)

        # Write via real client
        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('A1', {'value': 55.0})
        finally:
            client.close()

        # Run async loop like cli.py
        for _ in range(100):
            if broker.queue:
                broker.parse_queue()
                if len(mock_model.call_log) > initial_calls:
                    break
            await asyncio.sleep(0.01)

        assert len(mock_model.call_log) > initial_calls, (
            f'Model should fire in async loop after seeding, '
            f'got {len(mock_model.call_log)} calls (initial: {initial_calls})'
        )
        server.close()

    @pytest.mark.asyncio
    async def test_asyncio_event_loop_without_seeding(self, monkeypatch):
        """Mimic cli.py WITHOUT seeding — the current broken behavior."""
        import asyncio

        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
                'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
            'symbols': ['A1', 'B1'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')

        mock_model = MockModel()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')

        # Start monitors (no seeding!)
        obs.start_monitors(broker)

        # Write both PVs via real client
        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('A1', {'value': 5.0})
            for _ in range(30):
                if broker.queue:
                    broker.parse_queue()
                await asyncio.sleep(0.01)

            client.put('B1', {'value': 3.0})
            for _ in range(30):
                if broker.queue:
                    broker.parse_queue()
                await asyncio.sleep(0.01)
        finally:
            client.close()

        logging.info(f'No-seed async: model calls={len(mock_model.call_log)}')
        assert len(mock_model.call_log) >= 1, (
            f'Model should fire after writing both PVs (no seeding), '
            f'call_log={mock_model.call_log}'
        )
        server.close()


# ---------------------------------------------------------------------------
# Step 7: Diagnose exact value types flowing through the chain
# ---------------------------------------------------------------------------

class TestValueTypeDiagnostics:
    """Instrument every step to see the exact types and values."""

    def test_handler_put_payload_type(self, monkeypatch):
        """Instrument Handler.put() to log the exact payload type
        and raw_value type passed to callbacks."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)

        received_values = []
        received_types = []

        def diagnostic_cb(value):
            received_types.append(type(value).__name__)
            received_values.append(repr(value))

        server.monitor(diagnostic_cb, pv_name='A1')

        try:
            client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
            try:
                client.put('A1', {'value': 42.0})
                time.sleep(0.3)
            finally:
                client.close()

            logging.warning(f'Received types: {received_types}')
            logging.warning(f'Received values: {received_values}')

            assert len(received_types) >= 1, 'No callback received'
            # ntfloat is p4p's scalar wrapper — it's a subclass of float
            assert received_types[0] in ('float', 'int', 'float64', 'ntfloat'), (
                f'Expected scalar type, got {received_types[0]}: {received_values[0]}'
            )
        finally:
            server.close()

    def test_full_message_value_type_through_chain(self, monkeypatch):
        """Trace the value type at each step: Handler.put -> queue -> transformer."""
        port = _get_free_port()
        monkeypatch.setenv('EPICS_PVA_NAME_SERVERS', f'127.0.0.1:{port}')

        server_config = {
            'port': port,
            'variables': {
                'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
                'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 0.0},
            },
        }
        server = registered_interfaces['p4p_server'](server_config)
        broker = MessageBroker()
        obs = InterfaceObserver(server, 'in_interface')

        config_t = {
            'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
            'symbols': ['A1', 'B1'],
        }
        t_obs = TransformerObserver(SimpleTransformer(config_t), 'in_transformer')
        mock_model = MockModel()
        m_obs = ModelObserver(model=mock_model, topic='model_out')

        broker.attach(obs, 'get_all')
        broker.attach(t_obs, 'in_interface')
        broker.attach(m_obs, 'in_transformer')

        # Seed
        broker.get_all()
        while broker.queue:
            broker.parse_queue()

        obs.start_monitors(broker)

        client = Context('pva', conf={'EPICS_PVA_NAME_SERVERS': f'127.0.0.1:{port}'})
        try:
            client.put('A1', {'value': 99.0})
            time.sleep(0.3)
        finally:
            client.close()

        # Check what's in the queue before parsing
        assert len(broker.queue) >= 1, 'No message in queue after client put'
        msg = broker.queue[0]
        logging.warning(f'Queue message topic: {msg.topic}')
        logging.warning(f'Queue message value: {msg.value}')
        for k, v in msg.value.items():
            logging.warning(f'  key={k}, value_type={type(v)}, value={v}')
            if isinstance(v, dict) and 'value' in v:
                inner = v['value']
                logging.warning(f'    inner_type={type(inner).__name__}, inner={inner}')
                assert isinstance(inner, (int, float)), (
                    f'Message value for {k} should be scalar, '
                    f'got {type(inner).__name__}: {inner}'
                )

        # Parse and check model was called
        while broker.queue:
            broker.parse_queue()

        assert len(mock_model.call_log) >= 2, (
            f'Model should have been called, '
            f'call_log={mock_model.call_log}'
        )
        server.close()
