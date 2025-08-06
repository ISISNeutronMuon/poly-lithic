import time, json
from uuid import uuid4

import uvicorn, threading
from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from poly_lithic.src.logging_utils import get_logger

from .BaseInterface import BaseInterface

logger = get_logger()


class k2simFrame(BaseInterface):
    def __init__(self, config):
        """Initialize the k2simFrame interface."""
        self.app = FastAPI()
        self.port = config["port"]
        self.host = config["host"]
        self.kafka_url = config["kafka_url"]
        self.settings = config["settings"]
        self.data = {}
        self.output_data = {}
        self.data_version = 0
        self.client_id = f'k2simFrame-{uuid4()}'
        self.kafka_producer = Producer({
            'bootstrap.servers': self.kafka_url,
            'client.id': self.client_id,
        })
        self.kafka_consumer = Consumer({
            'bootstrap.servers': self.kafka_url,
            'group.id': f'k2simFrame-{uuid4()}',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': False, # 
            'client.id': self.client_id,
        })
        
        
        
        # subscribe to pl_job_requests
        self.kafka_consumer.subscribe(['pl_job_requests'])
        self.variable_list = ["jobs"]
        
        # initialise data key for vairable_list
        for key in self.variable_list:
            self.data[key] = {"value": None}
        
        
        logger.debug(f'k2simFrame initialized with host={self.host}, port={self.port}, kafka_url={self.kafka_url}')
        self.consumer_thread = threading.Thread(
            target=self._consume_messages,
            daemon=True
        )
        self.consumer_thread.start()
        
        
        # Initialize server and thread

        self.server = None
        self.server_thread = None
        
        logger.debug(f'Initializing k2simFrame interface on {self.host}:{self.port}')
        
        
        ## setup api routes

        @self.app.get('/ping', status_code=status.HTTP_200_OK)
        async def ping():
            """A simple ping endpoint to check if the server is running."""
            return JSONResponse(
                content={'message': 'pong'}, status_code=status.HTTP_200_OK
            )

        @self.app.get('/get_settings', status_code=status.HTTP_200_OK)
        async def get_settings():
            """Returns the settings for the beam format."""
            # This is a placeholder for actual settings retrieval logic
            return self.settings
        
    def _consume_messages(self):
        """Consume messages from Kafka topic."""
        logger.info(f"Starting Kafka consumer thread for {self.client_id}")
        while True:
            try:
                msg = self.kafka_consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        raise KafkaException(msg.error())
                # Process the message
                logger.debug(f"Received message: {msg.value()}")
                self.data["jobs"] ={"value": json.loads(msg.value().decode('utf-8') )}
            except Exception as e:
                logger.error(f"Error consuming messages: {e}")
            time.sleep(0.1)

    # not a route, but a method to set the settings from the program
    def set_settings(self, settings):
        """Sets the settings for the beam format."""
        self.settings = settings


    def run(self):
        """Start the FastAPI server in a separate thread (non-blocking)."""
        if self.server_thread is not None and self.server_thread.is_alive():
            logger.warning("Server is already running")
            return
            
        self.server_thread = threading.Thread(
            target=uvicorn.run, 
            args=(self.app,), 
            kwargs={
                'host': self.host,
                'port': self.port,
                'log_level': 'info',
            },
            daemon=True
        )
        self.server_thread.start()
        logger.info(f"Server started on {self.host}:{self.port}")

    def close(self):
        """Stop the FastAPI server."""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Stopping server...")
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                logger.warning("Server thread did not terminate gracefully.")

    def is_running(self):
        """Check if the server is running."""
        return self.server_thread is not None and self.server_thread.is_alive()
        ### Implementing abstract methods from BaseInterface

    def monitor(self, name, handler, **kwargs):
        """Placeholder for monitor method implementation."""
        pass

    def get(self, name, **kwargs):
        """get name and return value"""
        return name , self.data[name]

    def get_many(self, data, **kwargs):
        """get many names and return values"""
        output_dict = {}
        for name in data:
            value = self.get(name)
            if value is not None:
                output_dict[name] = value
        return output_dict

    def put(self, name, value, **kwargs):
        """put name and value"""
        self.kafka_producer.produce(
            'pl_job_results',
            json.dumps(value).encode('utf-8')
        )

    def put_many(self, data, **kwargs):
        """put many names and values"""
        for name, value in data.items():
            self.put(name, value, **kwargs)