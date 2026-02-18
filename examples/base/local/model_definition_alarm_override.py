import torch
import os


OUTPUT_PV = 'ML:LOCAL:TEST_S'


class ModelFactory:
    def __init__(self):
        os.environ['PYTHONPATH'] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        self.model = SimpleModel()
        model_path = 'examples/base/local/model.pth'
        if os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path))

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

    @staticmethod
    def _model_alarm_for_output(value: float) -> dict:
        # Example override policy from model side.
        if value >= 50.0:
            return {'severity': 2, 'status': 3, 'message': 'HIHI (model override)'}
        if value >= 20.0:
            return {'severity': 1, 'status': 4, 'message': 'HIGH (model override)'}
        if value <= -50.0:
            return {'severity': 2, 'status': 5, 'message': 'LOLO (model override)'}
        if value <= -20.0:
            return {'severity': 1, 'status': 6, 'message': 'LOW (model override)'}
        return {'severity': 0, 'status': 0, 'message': ''}

    def evaluate(self, x: dict) -> dict:
        input_tensor = torch.tensor([x['x'], x['y']], dtype=torch.float32)
        output_tensor = self.forward(input_tensor)
        output_value = float(output_tensor.item())

        return {
            OUTPUT_PV: {
                'value': output_value,
                # Explicit alarm from model should override interface-computed alarm.
                'alarm': self._model_alarm_for_output(output_value),
            }
        }
