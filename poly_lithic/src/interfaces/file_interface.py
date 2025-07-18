import h5py

from .BaseInterface import BaseDataInterface

# This is a simple interface that reads and writes to a h5df file
# the structure should be dataset per variable so that we can read one at a time


class h5dfInterface(BaseDataInterface):
    def __init__(self, config):
        self.path = config['path']
        # check if file exists
        try:
            with open(self.path):
                pass
        except FileNotFoundError:
            raise FileNotFoundError(f'File {self.path} not found')

    # we want to be able to read one or write one at a time, yield one at a time, in a generator fashion, this is for backtesting
    def load(self, **kwargs):
        with h5py.File(self.path, 'r') as f:
            for key in f.keys():
                yield key, f[key][()]

    def save(self, data, **kwargs):
        with h5py.File(self.path, 'w') as f:
            for key, value in data:
                f.create_dataset(key, data=value)

    def monitor(self, handler, **kwargs):
        # this is a faux monitor, it will just read the file and call the handler with each key value pair
        pass
