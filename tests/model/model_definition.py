import numpy as np
from lume_model.base import LUMEBaseModel
from lume_model.variables import ScalarVariable


# This is the model definition as in other examples
class ExampleModel(LUMEBaseModel):
    def _evaluate(self, input_dict):
        output_dict = {}
        output_dict['y'] = np.max([input_dict['x1'], input_dict['x2']])
        return output_dict


# We use this to create a model instance, we need this to yield a fully functional model instance
class ModelFactory:
    def __init__(self):
        input_variables = [
            ScalarVariable(name='x1', default_value=0, value_range=[-100000, 1000000]),
            ScalarVariable(name='x2', default_value=0, value_range=[-100000, 1000000]),
        ]
        output_variables = [ScalarVariable(name='y')]
        lume_model = ExampleModel(
            input_variables=input_variables, output_variables=output_variables
        )
        self.model = lume_model

    def get_model(self):
        return self.model
