import pytest
from poly_lithic.src.utils.messaging import (
    Message,
    ModelObserver,
    InterfaceObserver,
    MessageBroker,
    TransformerObserver,
)
from poly_lithic.src.transformers.BaseTransformers import SimpleTransformer
from poly_lithic.src.interfaces import registered_interfaces
import os
import logging


class MockModel:
    def __init__(self):
        self.predictions = []

    def evaluate(self, value):
        """our model expects a dictionary with {"name": {"value": value}, ...}"""
        logging.info(f'Model received: {value}')
        self.predictions.append(value)
        # the next layer expects a dictionary with {"name": {"value": value}, ...} so we have to retrun it as follows
        return {'pred0': value['x1'] + value['x2']}


@pytest.fixture
def message_broker():
    return MessageBroker()


@pytest.fixture
def mock_model():
    return MockModel()


@pytest.fixture
def p4p_server():
    config = {
        'variables': {
            'A1': {'name': 'A1', 'proto': 'pva', 'type': 'scalar', 'default': 2.0},
            'B1': {'name': 'B1', 'proto': 'pva', 'type': 'scalar', 'default': 1.0},
        }
    }
    p4p = registered_interfaces['p4p_server'](config)
    yield p4p
    p4p.close()


@pytest.fixture
def p4p_server_out():
    config = {
        'variables': {
            'out_scaled': {
                'name': 'out_scaled',
                'proto': 'pva',
                'type': 'scalar',
                'default': 0.0,
            }
        }
    }

    p4p = registered_interfaces['p4p_server'](config)
    yield p4p
    p4p.close()


@pytest.fixture
def model_observer(mock_model):
    return ModelObserver(model=mock_model, topic='model_out')


@pytest.fixture
def interface_observer(p4p_server):
    return InterfaceObserver(p4p_server, 'in_interface')


@pytest.fixture
def interface_observer_out(p4p_server_out):
    return InterfaceObserver(p4p_server_out, 'out_interface')


@pytest.fixture
def transformer_observer_in():
    config1 = {
        'variables': {'x2': {'formula': 'A1 + B1'}, 'x1': {'formula': 'A1'}},
        'symbols': ['A1', 'B1'],
    }
    return TransformerObserver(SimpleTransformer(config1), 'in_transformer')


@pytest.fixture
def transformer_observer_out():
    os.environ['PUBLISH'] = 'True'

    config2 = {
        'variables': {'out_scaled': {'formula': 'pred0 / 10.0'}},
        'symbols': ['pred0'],
    }
    return TransformerObserver(
        SimpleTransformer(config2), 'out_transformer', unpack_output=True
    )


# we want to test if the data goes from interface -> transformer -> model


def test_interface_observer_put(
    interface_observer,
    interface_observer_out,
    transformer_observer_in,
    transformer_observer_out,
    model_observer,
    message_broker,
    caplog,
):
    caplog.set_level(logging.DEBUG)
    # Broker setup
    message_broker.attach(interface_observer, 'get_all')
    message_broker.attach(transformer_observer_in, 'in_interface')
    message_broker.attach(model_observer, 'in_transformer')
    message_broker.attach(transformer_observer_out, 'model_out')
    message_broker.attach(interface_observer_out, 'out_transformer')

    # get_all
    message = Message(topic='get_all', source='clock', value={'dummy': {'value': 1}})

    # this should trigger the interface to get all variables
    message_broker.notify(message)
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    for message in message_broker.queue:
        assert message.topic == 'in_interface'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'in_transformer'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'model_out'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'out_transformer'
    assert (
        message_broker.queue[0].value['out_scaled']['value'] == 0.5
    )  # if you are looking at this and wondering why it returns a different shape looks for the unpack_output=True in the transformer_observer_out fixture
    message_broker.parse_queue()
    assert len(message_broker.queue) == 0  # no messages left in the queue
