import importlib
from abc import ABC, abstractmethod


class AbstractInterfaceLoader(ABC):
    """Abstract base class to manage lazy loading of interfaces."""

    def __init__(self):
        self._interfaces = {}

    def __getitem__(self, key):
        if key not in self._interfaces:
            self._interfaces[key] = self._load_interface(key)
        return self._interfaces[key]

    @abstractmethod
    def keys(self):
        """Abstract method to return a list of keys for all available interfaces."""

    @abstractmethod
    def _load_interface(self, key):
        """Abstract method to load an interface dynamically.
        Subclasses must override this method to provide custom loading logic.
        """

    def import_module(self, module_name, class_name):
        """Utility function to dynamically import a module and class."""
        try:
            # Assuming 'src.interfaces' is the parent package for all your modules
            module = importlib.import_module(module_name, package='poly_lithic.src')
            return getattr(module, class_name)
        except ImportError as e:
            print(f'Error importing {module_name}: {e}')
            raise e
