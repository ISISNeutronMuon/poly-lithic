# defines a compound transformer that can be used add multiple transformers together
import time

from poly_lithic.src.logging_utils.make_logger import get_logger
from poly_lithic.src.transformers import registered_transformers

from poly_lithic.src.transformers.BaseTransformer import BaseTransformer

logger = get_logger()


# config4 = {
#     "transformers": {
#         "transformer_1": {"type": "SimpleTransformer", "config": config2},
#         "transformer_2": {"type": "CAImageTransfomer", "config": config3},
#     }
# }


class CompoundTransformer(BaseTransformer):
    def __init__(self, config):
        logger.debug('Initializing CompoundTransformer')
        self.transformers = []
        self.latest_input = {}
        self.latest_transformed = {}
        self.input_list = []
        for transformer in config['transformers']:
            # print(transformer, config["transformers"][transformer])
            transformer_type = config['transformers'][transformer]['type']
            transformer_config = config['transformers'][transformer]['config']
            self.transformers.append(
                registered_transformers[transformer_type](transformer_config)
            )
            self.input_list += self.transformers[-1].input_list
            # merge dicts
            self.latest_transformed = {
                **self.latest_transformed,
                **self.transformers[-1].latest_transformed,
            }
            self.latest_input = {
                **self.latest_input,
                **self.transformers[-1].latest_input,
            }
        self.updated = False
        self.handler_time = 0

    def transform(self, data):
        for transformer in self.transformers:
            data = transformer.transform(data)

        return data

    def handler(self, name, data):
        time_start = time.time()
        logger.debug(f'CompoundTransformer handler for {name}')
        for transformer in self.transformers:
            if name in transformer.input_list:
                transformer.handler(name, data)
                if transformer.updated:
                    self.updated = True
                    self.latest_transformed = {
                        **self.latest_transformed,
                        **transformer.latest_transformed,
                    }
                    self.latest_input = {
                        **self.latest_input,
                        **transformer.latest_input,
                    }
        time_end = time.time()
        self.handler_time = time_end - time_start
