from poly_lithic.src.config import ConfigParser
from poly_lithic.src.interfaces import registered_interfaces
from poly_lithic.src.logging_utils import get_logger
from poly_lithic.src.transformers import registered_transformers
from poly_lithic.src.utils.messaging import (
    ModelObserver,
    InterfaceObserver,
    MessageBroker,
    TransformerObserver,
)

logger = get_logger()


class MockModel:
    def __init__(self):
        """placeholder for model"""

    def evaluate(self, value):
        """placeholder for model prediction"""
        return {'not_initialized': {'value': -99999999999}}


class Builder:
    def __init__(self, config_path):
        self.config = self.__initailise_config(config_path)
        self.logger = get_logger()

    def __initailise_config(self, config_path):
        """Initialise the configuration."""
        try:
            config_parser = ConfigParser(config_path)
            return config_parser.parse()
        except Exception as e:
            logger.error(f'Error initializing configuration: {e}')
            raise e

    def build(self) -> MessageBroker:
        """Build the model manager."""

        self.__build_observers()
        self.__build_broker()

        for name, observer in self.loaded_observers.items():
            self.broker.attach(observer, self.config.modules[name].sub)

        return self.broker

    def __build_observers(self):
        """Build the observers."""

        loaded_observers: dict[str, object] = {}
        for module in self.config.modules:
            try:
                module_type, module_subtype = self.config.modules[module].type.split(
                    '.'
                )
            except ValueError:
                raise ValueError(
                    f"Invalid module type: {self.config.modules[module].type} must be of the form 'type.subtype'"
                )

            if module_type == 'interface':
                if self.config.modules[module].module_args is not None:
                    args = self.config.modules[module].module_args
                else:
                    args = {}
                interface = InterfaceObserver(
                    registered_interfaces[module_subtype](
                        self.config.modules[module].config
                    ),
                    self.config.modules[module].pub,
                    *args,
                )
                loaded_observers[module] = interface
            elif module_type == 'transformer':
                if self.config.modules[module].module_args is not None:
                    args = self.config.modules[module].module_args
                else:
                    args = {}
                transformer = TransformerObserver(
                    registered_transformers[module_subtype](
                        self.config.modules[module].config
                    ),
                    self.config.modules[module].pub,
                    *args,
                )
                loaded_observers[module] = transformer
            elif module_type == 'model':
                if self.config.modules[module].module_args is not None:
                    args = self.config.modules[module].module_args
                else:
                    args = {}
                observer = ModelObserver(
                    config=self.config.modules[module].config,
                    topic=self.config.modules[module].pub,
                    *args,
                )
                loaded_observers[module] = observer
            else:
                raise ValueError(f'Invalid module type: {module_type}')
        logger.debug(f'Loaded observers: {loaded_observers}')

        # lets validate all of them are Observers
        for observer in loaded_observers:
            if not isinstance(
                loaded_observers[observer],
                (ModelObserver, InterfaceObserver, TransformerObserver),
            ):
                raise ValueError(
                    f'Invalid observer: {observer} must be of type ModelObserver, InterfaceObserver or TransformerObserver'
                )
        self.loaded_observers = loaded_observers
        return None

    def __build_broker(self):
        """Build the message broker."""
        self.broker = MessageBroker()
        logger.debug(f'Built broker: {self.broker}')
