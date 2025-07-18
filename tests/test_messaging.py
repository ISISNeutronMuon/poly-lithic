import pytest
from poly_lithic.src.utils.messaging import (
    Message,
    MessageBroker,
    Observer,
    TransformerObserver,
)
from poly_lithic.src.transformers.BaseTransformers import SimpleTransformer
import logging


class TestObserver(Observer):
    def __init__(self):
        self.messages = []

    def update(self, message: Message) -> Message:
        self.messages.append(message)
        return message


@pytest.fixture
def message_broker():
    return MessageBroker()


@pytest.fixture
def test_observer():
    return TestObserver()


def test_attach_observer(message_broker, test_observer):
    message_broker.attach(test_observer, 'test_topic')
    assert 'test_topic' in message_broker._observers
    assert test_observer in message_broker._observers['test_topic']


def test_detach_observer(message_broker, test_observer):
    message_broker.attach(test_observer, 'test_topic')
    assert test_observer in message_broker._observers['test_topic']
    message_broker.detach(test_observer, 'test_topic')
    assert test_observer not in message_broker._observers['test_topic']


def test_notify_observers(message_broker, test_observer, caplog):
    caplog.set_level(logging.DEBUG)
    message_broker.attach(test_observer, 'test_topic')
    message = Message(topic='test_topic', source='source', value={'key': {'value': 1}})
    message_broker.notify(message)
    assert len(test_observer.messages) == 1
    assert test_observer.messages[0] == message


# def test_notify_no_observers(message_broker, caplog):
#     caplog.set_level(logging.DEBUG)
#     message = Message(topic="test_topic", source="source", value={"key": {"value": 1}})
#     message_broker.notify(message)
#     print(caplog.text)
# assert "no observers for test_topic" in caplog.text # fails when running all tests but passes when running only this test


def test_parse_queue(message_broker, test_observer):
    test_observer.messages = []
    message_broker.attach(test_observer, 'test_topic')
    message = Message(topic='test_topic', source='source', value={'key': {'value': 1}})
    message_broker.queue.append(message)
    message_broker.parse_queue()
    assert len(test_observer.messages) == 1
    assert test_observer.messages[0] == message


def test_TransformerObserver(message_broker, test_observer):
    config1 = {
        'variables': {'x2': {'formula': 'A1 * B1'}, 'x1': {'formula': 'A1'}},
        'symbols': ['A1', 'B1'],
    }
    st = SimpleTransformer(config1)
    stObserver = TransformerObserver(st, 'test_topic')

    message1 = Message(topic='test_topic', source='source', value={'A1': {'value': 2}})
    message2 = Message(topic='test_topic', source='source', value={'B1': {'value': 2}})

    message_broker.attach(stObserver, 'test_topic')
    message_broker.notify(message1)
    assert st.updated is False
    message_broker.notify(message2)
    assert st.updated is False
    assert st.latest_transformed['x2'] == 2 * 2
    assert st.latest_transformed['x1'] == 2
