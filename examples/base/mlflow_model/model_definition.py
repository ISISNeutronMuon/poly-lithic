import torch


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
