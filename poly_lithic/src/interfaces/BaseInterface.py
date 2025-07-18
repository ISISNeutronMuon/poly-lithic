# Abstract class for all interfaces

from abc import ABC, abstractmethod


class BaseDataInterface(ABC):
    @abstractmethod
    def __init__(self, config, **kwargs):
        pass

    @abstractmethod
    def load(self, **kwargs):
        pass

    @abstractmethod
    def save(self, data, **kwargs):
        pass


class BaseInterface(ABC):
    @abstractmethod
    def __init__(self, config):
        pass

    @abstractmethod
    def monitor(self, name, handler, **kwargs):
        pass

    @abstractmethod
    def get(self, name, **kwargs):
        pass

    @abstractmethod
    def put(self, name, value, **kwargs):
        pass

    @abstractmethod
    def put_many(self, data, **kwargs):
        pass

    @abstractmethod
    def get_many(self, data, **kwargs):
        pass
