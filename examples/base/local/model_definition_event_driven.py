import torch
import os
import time
import logging

logger = logging.getLogger(__name__)


class ModelFactory:
    def __init__(self):
        os.environ['PYTHONPATH'] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        self.model = SimpleModel()
        model_path = 'examples/base/local/model.pth'
        if os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path))
            logger.info('Model loaded successfully.')
        else:
            logger.warning(
                f"Model file '{model_path}' not found. Using untrained model."
            )
        logger.info('ModelFactory initialized (event-driven mode)')

    def get_model(self):
        return self.model


class SimpleModel(torch.nn.Module):
    def __init__(self):
        super(SimpleModel, self).__init__()
        self.linear1 = torch.nn.Linear(2, 10)
        self.linear2 = torch.nn.Linear(10, 1)
        self._eval_count = 0

    def forward(self, x):
        x = torch.relu(self.linear1(x))
        x = self.linear2(x)
        return x

    def evaluate(self, x: dict) -> dict:
        self._eval_count += 1
        logger.info(
            f'[event-driven] evaluate #{self._eval_count} triggered at '
            f'{time.strftime("%H:%M:%S")} | inputs: x={x.get("x")}, y={x.get("y")}'
        )
        input_tensor = torch.tensor([x['x'], x['y']], dtype=torch.float32)
        output_tensor = self.forward(input_tensor)
        result = output_tensor.item()
        logger.info(f'[event-driven] output: {result}')
        return {'output': result}
