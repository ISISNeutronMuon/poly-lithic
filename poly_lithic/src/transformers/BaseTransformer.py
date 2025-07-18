from abc import abstractmethod


class BaseTransformer:
    @abstractmethod
    def __init__(self, config: dict):
        """
        config: dict passed from the pv_mappings.yaml files.
        """
        pass

    @abstractmethod
    def transform(self):
        """
        Call transform function to transform the input data, see SimpleTransformer in model_manager/src/transformers/BaseTransformers.py for an example.
        """
        pass

    @abstractmethod
    def handler(self, pv_name: str, value: dict | float | int):
        """
        Handler function to handle the input data, in most cases it initiates the transform function when all the input data is available.
        Handler is the only function exposed to the main loop of the program aside from initial configuration.
        """
        pass
