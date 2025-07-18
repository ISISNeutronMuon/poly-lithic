# abstract class ModelGetterBase
from abc import ABC, abstractmethod


class ModelGetterBase(ABC):
    @abstractmethod
    def get_model(self):
        pass

    # @abstractmethod
    # def get_config(self):
    #     pass

    @abstractmethod
    def get_requirements(self):
        pass

    # @abstractmethod
    # def get_tags(self):
    #     pass
