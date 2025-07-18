from poly_lithic.src.utils.builder import Builder
from poly_lithic.src.utils.messaging import Message
import pytest
import os
import json
import logging
import requests  # to check if we can rech the mlflow server


@pytest.fixture
def make_builder():
    def _make_builder(config_path):
        return Builder(config_path)

    return _make_builder


@pytest.fixture(scope='session', autouse=True)
def load_env():
    env_config('./tests/env.json')


def env_config(env_config):
    """Set the environment variables."""
    logging.debug(f'Setting environment variables from: {env_config}')
    try:
        # load json
        with open(env_config) as stream:
            data = json.load(stream)
        for key, value in data.items():
            os.environ[key] = value
    except Exception as e:
        logging.error(f'Error setting environment variables: {e}')

ENV_LOADED = env_config('./tests/env.json')

def test_build(caplog, make_builder):
    # caplog.set_level(logging.DEBUG)
    builder = make_builder('./tests/pv_mapping.yaml')
    message_broker = builder.build()
    message = Message(topic='get_all', source='clock', value={'dummy': {'value': 1}})

    message_broker.notify(message)


# only run this test if the MLflow server is reachable
@pytest.mark.skipif(
    os.environ.get('MLFLOW_TRACKING_URI') is None,
    reason='MLFLOW_TRACKING_URI is not set',
)
def test_mlflow_legacy(caplog, make_builder):
    # caplog.set_level(logging.DEBUG)
    try:
        response = requests.get('http://athena.isis.rl.ac.uk:5000/health')
        assert response.status_code == 200
    except Exception:
        pytest.skip(
            f'MLflow server is not reachable: {os.environ["MLFLOW_TRACKING_URI"]}'
        )
    # caplog.set_level(logging.DEBUG)
    builder = make_builder('./tests/pv_mapping_mlflow_legacy.yaml')
    message_broker = builder.build()
    caplog.set_level(logging.INFO)
    builder.config.draw_routing_graph()  # for debugging
    # caplog.set_level(logging.DEBUG)
    # lets run it
    message = Message(topic='get_all', source='clock', value={'dummy': {'value': 1}})

    message_broker.notify(message)
    assert (
        len(message_broker.queue) == 1
    )  # we have an extra here with the S variable we  should see A,B and S variables
    logging.info(message_broker.queue)
    for message in message_broker.queue:
        assert message.topic == 'in_interface'
    message_broker.parse_queue()
    assert (
        len(message_broker.queue) == 1
    )  # A and B get transformed S is discarded since its not in the transformer symbol list
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'in_transformer'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'model'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'out_transformer'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 0  # no messages left in the queue

@pytest.mark.skipif(
    os.environ.get('MLFLOW_TRACKING_URI') is None,
    reason='MLFLOW_TRACKING_URI is not set',
)
def test_mlflow(caplog, make_builder):
    # caplog.set_level(logging.DEBUG)
    try:
        response = requests.get('http://athena.isis.rl.ac.uk:5000/health')
        assert response.status_code == 200
    except Exception:
        pytest.skip(
            f'MLflow server is not reachable: {os.environ["MLFLOW_TRACKING_URI"]}'
        )
    # caplog.set_level(logging.DEBUG)
    builder = make_builder('./tests/pv_mapping_mlflow.yaml')
    message_broker = builder.build()
    caplog.set_level(logging.INFO)
    builder.config.draw_routing_graph()  # for debugging
    # caplog.set_level(logging.DEBUG)
    # lets run it
    message = Message(topic='get_all', source='clock', value={'dummy': {'value': 1}})

    message_broker.notify(message)
    assert (
        len(message_broker.queue) == 1
    )  # we have an extra here with the S variable we  should see A,B and S variables
    logging.info(message_broker.queue)
    for message in message_broker.queue:
        assert message.topic == 'in_interface'
    message_broker.parse_queue()
    assert (
        len(message_broker.queue) == 1
    )  # A and B get transformed S is discarded since its not in the transformer symbol list
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'in_transformer'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'model'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 1
    logging.info(message_broker.queue)
    assert message_broker.queue[0].topic == 'out_transformer'
    message_broker.parse_queue()
    assert len(message_broker.queue) == 0  # no messages left in the queue
