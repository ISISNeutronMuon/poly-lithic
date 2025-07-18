import yaml
from .config_object import ConfigObject


class ConfigParser:
    def __init__(self, config_path):
        self.config_path = config_path

    def parse(self):
        with open(self.config_path) as stream:
            try:
                data = yaml.safe_load(stream)
                # logging.debug(data)
                config_object = ConfigObject(**data)
                _ = (
                    config_object.graph
                )  # Access the graph property to trigger validation
                return config_object
            except yaml.YAMLError as exc:
                print(exc)
                return None
