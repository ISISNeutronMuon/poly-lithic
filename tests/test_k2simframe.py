import os

from uuid import uuid4

import pytest, requests, time

from poly_lithic.src.interfaces import registered_interfaces
from poly_lithic.src.logging_utils.make_logger import make_logger
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer


k2simFrameInterface = registered_interfaces['k2simFrame']


logger = make_logger('k2simFrame_test')


# check if we can connect to kafka 

def setup():
    # load creds 
    try:
        with open('./tests/kafka.cred', 'r') as f:
            os.environ['KAFKA_URL'] = f.read().strip()
    except FileNotFoundError:
        logger.error("Kafka credentials file not found. Skipping k2simFrame tests.")
        
        
setup()

@pytest.mark.skipif(os.environ.get('KAFKA_URL') is None,
                    reason='KAFKA_URL is not set')
def test_k2simFrame():
    """Test the k2simFrame interface."""
    # create a k2simFrame instance
    
    config = {
        'host': 'localhost',
        'port': 9091,
        'kafka_url': os.environ['KAFKA_URL'],
        'settings': {}
    }
    
    k2sim_frame = k2simFrameInterface(config)
    k2sim_frame.run() # this should start the server in a separate thread
    
    time.sleep(2)  # wait for the server to start
    # test requests
    
    response = requests.get(f'http://{config["host"]}:{config["port"]}/ping')
    assert response.status_code == 200
    assert response.json() == {'message': 'pong'}

    logger.info("k2simFrame interface is running and responding to requests.")
    
    test_payload = {
        "model": "test_model",
        "beam": {"data":[1,3,4,5]},
        "lattice": "test_lattice",
        "job_id": "test_job_123"
    }
    
    test_producer = Producer({
        'bootstrap.servers': config['kafka_url'],
        'client.id': f'test_producer-{uuid4()}',
    })
    
    # self.data should be empty initially
    k2sim_frame.data.clear()
    assert k2sim_frame.data == {}
    
    test_producer.produce('pl_job_requests', key='test_key', value=str(test_payload))
    
    test_producer.flush()
    
    logger.info("Test payload sent to Kafka topic 'pl_job_requests'.")
    
    # data should be updated after consuming the message
    time.sleep(1)  # wait for the consumer to process the message
    assert k2sim_frame.data == {'test_key': str(test_payload)}
    
    
    

