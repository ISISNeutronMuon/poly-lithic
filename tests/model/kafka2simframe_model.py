import os


class ModelFactory:
    # can do more complex things here but we will just load the model from a locally saved file
    def __init__(self):
        print('ModelFactory initialized')   
        self.model = SimpleModel()
        
    def get_model(self):
        return self.model


class SimpleModel():
    def __init__(self):
        print('SimpleModel initialized')

    # this method is necessary for the model to be evaluated by poly-lithic
    def evaluate(self, x: dict) -> dict:
        return x