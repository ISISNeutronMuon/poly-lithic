import os

import numpy as np


class ModelFactory:
    def __init__(self):
        os.environ['PYTHONPATH'] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        self.model = WaveformArrayModel()

    def get_model(self):
        return self.model


class WaveformArrayModel:
    def evaluate(self, x: dict) -> dict:
        waveform = np.asarray(x['waveform_in'], dtype=float)
        array = np.asarray(x['array_in'], dtype=float)
        x_val = float(x.get('x', 0.0))
        y_val = float(x.get('y', 0.0))

        scalar = float(waveform.mean() + array.sum() + x_val + y_val)
        waveform_out = waveform + array.mean()

        return {'output': scalar, 'waveform_out': waveform_out}
