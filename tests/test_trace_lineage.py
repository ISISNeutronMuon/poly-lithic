# Tests for trace lineage completeness.
# Verifies that parent_trace_ids aggregates trace_ids from ALL contributing
# inputs, not just the triggering message.

import pytest

from poly_lithic.src.utils.messaging import (
    Message,
    TransformerObserver,
    ModelObserver,
)
from poly_lithic.src.transformers.BaseTransformers import (
    SimpleTransformer,
    PassThroughTransformer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_value_struct(value, trace_id):
    """Build a value struct with embedded trace metadata."""
    return {
        'value': value,
        'metadata': {'trace': {'trace_id': trace_id}},
    }


class _MockModel:
    def evaluate(self, value):
        return {'out': sum(value.values())}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_transformer():
    config = {
        'variables': {
            'x': {'formula': 'PV_A'},
            'y': {'formula': 'PV_B'},
        },
        'symbols': ['PV_A', 'PV_B'],
    }
    return SimpleTransformer(config)


@pytest.fixture
def passthrough_transformer():
    config = {
        'variables': {
            'OUT_A': 'PV_A',
            'OUT_B': 'PV_B',
        },
    }
    return PassThroughTransformer(config)


# ---------------------------------------------------------------------------
# TransformerObserver — SimpleTransformer
# ---------------------------------------------------------------------------

class TestTransformerObserverLineage:
    """TransformerObserver output should list trace_ids from ALL inputs."""

    def test_seed_then_single_event(self, simple_transformer):
        """Seed both PVs, then trigger via one PV change.
        The output parent_trace_ids must contain both the seed trace_id
        AND the event trace_id."""
        obs = TransformerObserver(simple_transformer, 'in_transformer')

        # --- Seed: simulate get_all delivering both PVs in one message ---
        seed_msg = Message(
            topic='in_interface',
            source='test',
            value={
                'PV_A': _make_value_struct(1.0, 'seed-1'),
                'PV_B': _make_value_struct(2.0, 'seed-1'),
            },
        )
        seed_out = obs.update(seed_msg)
        assert seed_out is not None  # transform fires (all inputs present)

        # --- Event: only PV_B changes ---
        event_msg = Message(
            topic='in_interface',
            source='test',
            value={
                'PV_B': _make_value_struct(3.0, 'event-2'),
            },
        )
        event_out = obs.update(event_msg)
        assert event_out is not None

        pids = set(event_out.parent_trace_ids)
        # Must contain the event message trace_id
        assert event_msg.trace_id in pids
        # Must contain PV_A's trace_id from seeding (still in latest_input_struct)
        assert 'seed-1' in pids

    def test_both_pvs_updated_separately(self, simple_transformer):
        """Two separate single-PV messages.  Output should reference both."""
        obs = TransformerObserver(simple_transformer, 'in_transformer')

        msg_a = Message(
            topic='in_interface',
            source='test',
            value={'PV_A': _make_value_struct(1.0, 'trace-a')},
        )
        out_a = obs.update(msg_a)
        # Only one input present — transformer should NOT fire
        assert out_a is None

        msg_b = Message(
            topic='in_interface',
            source='test',
            value={'PV_B': _make_value_struct(2.0, 'trace-b')},
        )
        out_b = obs.update(msg_b)
        assert out_b is not None

        pids = set(out_b.parent_trace_ids)
        assert 'trace-a' in pids
        assert 'trace-b' in pids

    def test_seed_message_trace_id_also_included(self, simple_transformer):
        """The message-level trace_id (not just embedded metadata) should
        always appear in parent_trace_ids."""
        obs = TransformerObserver(simple_transformer, 'in_transformer')

        seed_msg = Message(
            topic='in_interface',
            source='test',
            value={
                'PV_A': _make_value_struct(1.0, 'meta-seed'),
                'PV_B': _make_value_struct(2.0, 'meta-seed'),
            },
        )
        out = obs.update(seed_msg)
        assert out is not None
        assert seed_msg.trace_id in out.parent_trace_ids


# ---------------------------------------------------------------------------
# TransformerObserver — PassThroughTransformer
# ---------------------------------------------------------------------------

class TestPassThroughTransformerLineage:
    """Same lineage behaviour for PassThroughTransformer."""

    def test_seed_then_single_event(self, passthrough_transformer):
        obs = TransformerObserver(passthrough_transformer, 'out_transformer')

        seed_msg = Message(
            topic='model',
            source='test',
            value={
                'PV_A': _make_value_struct(10, 'pt-seed'),
                'PV_B': _make_value_struct(20, 'pt-seed'),
            },
        )
        seed_out = obs.update(seed_msg)
        assert seed_out is not None

        event_msg = Message(
            topic='model',
            source='test',
            value={'PV_B': _make_value_struct(30, 'pt-event')},
        )
        event_out = obs.update(event_msg)
        assert event_out is not None

        pids = set(event_out.parent_trace_ids)
        assert event_msg.trace_id in pids
        assert 'pt-seed' in pids


# ---------------------------------------------------------------------------
# ModelObserver
# ---------------------------------------------------------------------------

class TestModelObserverLineage:
    """ModelObserver output should aggregate trace_ids from input metadata."""

    def test_multiple_input_traces(self):
        model_obs = ModelObserver(model=_MockModel(), topic='model')

        msg = Message(
            topic='in_transformer',
            source='test',
            value={
                'x': _make_value_struct(1.0, 'input-trace-x'),
                'y': _make_value_struct(2.0, 'input-trace-y'),
            },
        )
        results = model_obs.update(msg)
        assert len(results) == 1
        out = results[0]

        pids = set(out.parent_trace_ids)
        assert msg.trace_id in pids
        assert 'input-trace-x' in pids
        assert 'input-trace-y' in pids

    def test_single_input_trace(self):
        """When all inputs share the same trace_id, no duplicates."""
        model_obs = ModelObserver(model=_MockModel(), topic='model')

        msg = Message(
            topic='in_transformer',
            source='test',
            value={
                'x': _make_value_struct(1.0, 'same-trace'),
                'y': _make_value_struct(2.0, 'same-trace'),
            },
        )
        results = model_obs.update(msg)
        out = results[0]

        # 'same-trace' + msg.trace_id — at most 2 entries
        assert 'same-trace' in out.parent_trace_ids
        assert msg.trace_id in out.parent_trace_ids

    def test_no_metadata_no_crash(self):
        """Inputs without metadata should not cause errors."""
        model_obs = ModelObserver(model=_MockModel(), topic='model')

        msg = Message(
            topic='in_transformer',
            source='test',
            value={
                'x': {'value': 1.0},
                'y': {'value': 2.0},
            },
        )
        results = model_obs.update(msg)
        out = results[0]

        # Only the message trace_id
        assert out.parent_trace_ids == [msg.trace_id]


# ---------------------------------------------------------------------------
# Transformer without latest_input_struct (e.g. CAImageTransformer)
# ---------------------------------------------------------------------------

class TestTransformerWithoutInputStruct:
    """Transformers that lack latest_input_struct should still work
    (fallback to triggering message trace_id only)."""

    def test_getattr_fallback(self):
        from poly_lithic.src.transformers.BaseTransformer import BaseTransformer

        class MinimalTransformer(BaseTransformer):
            def __init__(self):
                self.updated = False
                self.latest_transformed = {}

            def transform(self):
                pass

            def handler(self, pv_name, value):
                self.latest_transformed = {'out': value}
                self.updated = True

        t = MinimalTransformer()
        obs = TransformerObserver(t, 'test_topic')

        msg = Message(
            topic='input',
            source='test',
            value={'PV_X': {'value': 42}},
        )
        out = obs.update(msg)
        assert out is not None
        # Only the message trace_id — no latest_input_struct to read from
        assert msg.trace_id in out.parent_trace_ids
