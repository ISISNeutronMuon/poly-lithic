import torch
import os


class ModelFactory:
    # can do more complex things here but we will just load the model from a locally saved file
    def __init__(self):
        # add this path to python environment
        os.environ['PYTHONPATH'] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        print('PYTHONPATH set to:', os.environ['PYTHONPATH'])
        self.model = SimpleModel()
        model_path = 'examples/base/local/model.pth'
        if os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path))
            print('Model loaded successfully.')
        else:
            print(
                f"Warning: Model file '{model_path}' not found. Using untrained model."
            )
        print('ModelFactory initialized')

    # this method is necessary for the model to be retrieved by poly-lithic
    def get_model(self):
        return self.model


class SimpleModel(torch.nn.Module):
    def __init__(self):
        super(SimpleModel, self).__init__()
        self.linear1 = torch.nn.Linear(2, 10)
        self.linear2 = torch.nn.Linear(10, 1)

    def forward(self, x):
        x = torch.relu(self.linear1(x))
        x = self.linear2(x)
        return x

    # this method is necessary for the model to be evaluated by poly-lithic
    def evaluate(self, x: dict) -> dict:
        # x will be a dicrt of keys and values
        # {"x": x, "y": y}
        input_tensor = torch.tensor([x['x'], x['y']], dtype=torch.float32)
        # you may want to do somethinf more complex here
        output_tensor = self.forward(input_tensor)
        # return a dictionary of keys and values
        return {'output': output_tensor.item()}
