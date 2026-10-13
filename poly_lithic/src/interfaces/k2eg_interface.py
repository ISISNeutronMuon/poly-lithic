import uuid
from concurrent.futures import ThreadPoolExecutor

import k2eg
from poly_lithic.src.logging_utils import get_logger

from k2eg.serialization import Scalar
from .BaseInterface import BaseInterface

executor = ThreadPoolExecutor(20)

logger = get_logger()

# _dir = os.path.dirname(os.path.abspath(__file__))
# os.environ["K2EG_PYTHON_CONFIGURATION_PATH_FOLDER"] = _dir
# print(f"K2EG_PYTHON_CONFIGURATION_PATH_FOLDER: {_dir}")


class K2EGInterface(BaseInterface):
    supports_monitor = True

    def __init__(self, config):
        self.client = None
        try:
            self.client = k2eg.dml(
                config.get('environment_id', 'env'),
                config.get('app_name', 'app-three'),
                group_name=config.get('group_name'),
            )
        except Exception as e:
            logger.error(f'Error initializing K2EGInterface: {e}')
            raise

        pv_dict = config['variables']
        pv_url_list = []
        for pv in pv_dict:
            pv_url_list.append(pv_dict[pv]['proto'] + '://' + pv_dict[pv]['name'])
        self.pv_url_list = pv_url_list
        self.symbol_list = list(pv_dict.keys())
        self.variable_list = list(pv_dict.keys())
        self.url_lookup = {
            pv_dict[pv]['proto'] + '://' + pv_dict[pv]['name']: pv for pv in pv_dict
        }
        self.reverse_url_lookup = {
            pv: pv_dict[pv]['proto'] + '://' + pv_dict[pv]['name'] for pv in pv_dict
        }

        logger.debug(f'K2EGInterface initialized with pv_url_list: {self.pv_url_list}')
        logger.debug(f'K2EGInterface initialized with symbol_list: {self.symbol_list}')
        logger.debug(f'K2EGInterface initialized with url_lookup: {self.url_lookup}')
        logger.debug(
            f'K2EGInterface initialized with reverse_url_lookup: {self.reverse_url_lookup}'
        )

    def monitor(self, handler, pv_name=None, **kwargs):
        """Monitor PVs.

        With *pv_name* (event-driven mode) only that variable is monitored and
        *handler* receives the bare value.  Without it all PVs are monitored
        and *handler* receives k2eg's ``(pv_name, data)`` callback arguments.
        """
        if pv_name is not None:
            url = self.reverse_url_lookup[pv_name]
            logger.debug(f'Monitoring {url}')

            def wrapped(_name, data):
                handler(
                    data['value']
                    if isinstance(data, dict) and 'value' in data
                    else data
                )

            try:
                return self.client.monitor(url, wrapped, timeout=1000)
            except Exception as e:
                logger.error(f'Error monitoring {url}: {e}')
                raise

        logger.debug(f'Monitoring {self.pv_url_list}')
        try:
            self.client.monitor_many(self.pv_url_list, handler, timeout=1000)
        except Exception as e:
            logger.error(f'Error monitoring: {e}')
            raise

    def get(self, name, **kwargs):
        url = self.reverse_url_lookup[name]
        value = self.client.get(url)
        return name, value

    def put(self, name, value, **kwargs):
        # print(f"putting {name} with value {value}")
        try:
            self.client.put(
                self.reverse_url_lookup[name], Scalar('value', value['value'])
            )
        except Exception as e:
            print(f'Error putting: {e}')
            raise e

    def put_many(self, data, **kwargs):
        results = []
        for name, value in data.items():
            res = executor.submit(self.put, name, value)
            results.append(res)
        for res in results:
            res.result()

    def get_many(self, data, **kwargs):
        pass

    def close(self):
        if self.client is not None:
            self.client.close()
        logger.debug('K2EGInterface closed')
        return True

    def get_inputs(self):
        return self.variable_list

    def get_outputs(self):
        return self.variable_list
