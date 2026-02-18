import os
import time
from typing import Any

# anyScalar
import numpy as np
from p4p import Value
from p4p.client.thread import Context
from p4p.nt import NTNDArray, NTScalar
from p4p.server import Server, StaticProvider
from p4p.server.raw import ServOpWrap
from p4p.server.thread import SharedPV
from poly_lithic.src.logging_utils import get_logger

from .BaseInterface import BaseInterface
from .p4p_alarm_helpers import compute_alarm, normalise_variable_settings

# multi pool


logger = get_logger()

# os.environ["EPICS_PVA_NAME_SERVERS"] = "localhost:5075"


class SimplePVAInterface(BaseInterface):
    def __init__(self, config):
        self.ctxt = Context('pva', nt=False)
        if 'EPICS_PVA_NAME_SERVERS' in os.environ:
            logger.warning(
                f'EPICS_PVA_NAME_SERVERS: {os.environ["EPICS_PVA_NAME_SERVERS"]}'
            )
        elif 'EPICS_PVA_NAME_SERVERS' in config:
            os.environ['EPICS_PVA_NAME_SERVERS'] = config['EPICS_PVA_NAME_SERVERS']
            logger.warning(
                f'EPICS_PVA_NAME_SERVERS: {os.environ["EPICS_PVA_NAME_SERVERS"]}'
            )
        else:
            logger.warning(
                'EPICS_PVA_NAME_SERVERS not set in config or environment, using localhost:5075'
            )
            os.environ['EPICS_PVA_NAME_SERVERS'] = 'localhost:5075'

        pv_dict = config['variables']
        self.in_list = []
        self.out_list = []
        self.variable_configs = {}
        self.variable_settings = {}
        for pv, pv_cfg in pv_dict.items():
            try:
                assert pv_cfg['proto'] == 'pva'
            except Exception:
                logger.error(f'Protocol for {pv} is not pva')
                raise AssertionError

            pv_name = pv_cfg['name']
            mode = pv_cfg['mode'] if 'mode' in pv_cfg else 'inout'
            if mode not in ['in', 'out', 'inout']:
                logger.error(f'Mode must be "in", "out" or "inout"')
                raise Exception(f'Mode must be "in", "out" or "inout"')

            if mode == 'inout' or mode == 'out':
                self.out_list.append(pv_name)
            if mode == 'inout' or mode == 'in':
                self.in_list.append(pv_name)

            settings = normalise_variable_settings(pv_name, pv_cfg)
            self.variable_settings[pv_name] = settings
            self.variable_configs[pv_name] = pv_cfg

        logger.debug(f'SimplePVAInterface initialized with out_list: {self.out_list} in_list: {self.in_list}')

    def __handler_wrapper(self, handler, name):
        # unwrap p4p.Value into name, value
        def wrapped_handler(value):
            # logger.debug(f"SimplePVAInterface handler for {name, value['value']}")

            handler(name, {'value': value['value']})

        return wrapped_handler

    def monitor(self, handler, **kwargs):
        for pv in self.in_list:
            try:
                new_handler = self.__handler_wrapper(handler, pv)
                self.ctxt.monitor(pv, new_handler)
            except Exception as e:
                logger.error(
                    f'Error monitoring in function monitor for SimplePVAInterface: {e}'
                )
                logger.error(f'pv: {pv}')
                raise e

    def get(self, name, **kwargs):
        value = self.ctxt.get(name)
        if isinstance(value['value'], np.ndarray):
            # if value has dimension
            if 'dimension' in value:
                y_size = value['dimension'][0]['size']
                x_size = value['dimension'][1]['size']
                value = value['value'].reshape((y_size, x_size))
            else:
                value = value['value']
        else:
            value = value['value']

        value = {'value': value}
        return name, value

    @staticmethod
    def _payload_has_explicit_alarm(payload: Any) -> bool:
        if isinstance(payload, Value):
            try:
                return bool(payload.changed('alarm'))
            except Exception:
                return 'alarm' in payload
        if isinstance(payload, dict):
            return 'alarm' in payload
        return False

    @staticmethod
    def _payload_extract_value(payload: Any) -> tuple[Any, bool]:
        if isinstance(payload, Value):
            try:
                return payload['value'], True
            except Exception:
                return None, False
        if isinstance(payload, dict):
            if 'value' in payload:
                return payload['value'], True
            return None, False
        return payload, True

    @staticmethod
    def _payload_set_alarm(payload: Any, alarm: dict[str, Any]) -> Any:
        if isinstance(payload, Value):
            payload['alarm'] = alarm
            return payload
        if isinstance(payload, dict):
            payload_with_alarm = dict(payload)
            payload_with_alarm['alarm'] = alarm
            return payload_with_alarm
        return {'value': payload, 'alarm': alarm}

    @staticmethod
    def _payload_apply_metadata(payload: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        if settings['display'] is not None:
            payload['display'] = settings['display']
        if settings['control'] is not None:
            payload['control'] = settings['control']
        if settings['valueAlarm'] is not None:
            payload['valueAlarm'] = settings['valueAlarm']
        return payload

    @staticmethod
    def _coerce_client_value(value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return NTNDArray().wrap(value)
        return value

    def _extract_fallback_value(self, payload: Any) -> Any:
        value, has_value = self._payload_extract_value(payload)
        if not has_value:
            raise ValueError('Cannot retry put without a value field')
        return value

    def _prepare_write_payload(self, name: str, payload: Any) -> tuple[Any, bool]:
        settings = self.variable_settings.get(name)
        if settings is None:
            return payload, False

        has_explicit_alarm = self._payload_has_explicit_alarm(payload)
        if has_explicit_alarm:
            return payload, True

        if not settings['compute_alarm']:
            return payload, False

        value, has_value = self._payload_extract_value(payload)
        if not has_value:
            raise ValueError(f'{name}: compute_alarm requires payload with value')

        alarm = compute_alarm(value, settings['alarm_policy'])
        payload_with_alarm = self._payload_set_alarm(payload, alarm)
        return payload_with_alarm, True

    def put(self, name, value, **kwargs):
        payload, has_alarm_payload = self._prepare_write_payload(name, value)
        payload = self._coerce_client_value(payload)
        try:
            return self.ctxt.put(name, payload)
        except Exception as exc:
            if has_alarm_payload:
                fallback_value = self._coerce_client_value(
                    self._extract_fallback_value(payload)
                )
                logger.warning(
                    f'Put with alarm payload failed for {name}, retrying with value-only put: {exc}'
                )
                return self.ctxt.put(name, fallback_value)
            raise

    def put_many(self, data, **kwargs):
        for key, value in data.items():
            self.put(key, value)

    def get_many(self, data, **kwargs):
        results = self.ctxt.get(data, throw=False)
        output = {}
        # print(f"results: {results}")
        for value, key in zip(results, data):
            if isinstance(value['value'], np.ndarray):
                # if value has dimension
                if 'dimension' in value:
                    y_size = value['dimension'][0]['size']
                    x_size = value['dimension'][1]['size']
                    value = value['value'].reshape((y_size, x_size))
                else:
                    value = value['value']
            else:
                value = value['value']

            output[key] = {'value': value}

        return output

    def close(self):
        logger.debug('Closing SimplePVAInterface')
        self.ctxt.close()

    def get_outputs(self):
        return self.out_list

    def get_inputs(self):
        return self.in_list

class SimplePVAInterfaceServer(SimplePVAInterface):
    """
    Simple PVA integfcae with a server rather than just a client, this will host the PVs provided in the config
    """

    def __init__(self, config):
        super().__init__(config)
        self.shared_pvs = {}
        self.kv_store = {}

        if 'port' in config:
            port = config['port']
        else:
            port = (
                5075  # this will fail if we have two servers running on the same port
            )

        # if "init" in config:
        #     if not config["init"]:
        #         self.init_pvs = False
        #     else:
        #         self.init_pvs = True
        # else:
        #     self.init_pvs = True

        # print(f"self.init_pvs: {self.init_pvs}")

        for pv in set(self.in_list + self.out_list):
            pv_cfg = self.variable_configs[pv]
            settings = self.variable_settings[pv]
            pv_type = settings['type']
            pv_type_nt = None
            pv_type_init = None

            if pv_type == 'image':
                y_size = pv_cfg['image_size']['y']
                x_size = pv_cfg['image_size']['x']
                intial_value = np.zeros((y_size, x_size))
                if 'default' in pv_cfg:
                    raise NotImplementedError('Default values for images not implemented')
                pv_type_nt = NTNDArray()
                pv_type_init = intial_value
            elif pv_type == 'waveform' or pv_type == 'array':
                length = pv_cfg['length'] if 'length' in pv_cfg else 10
                if 'default' in pv_cfg:
                    intial_value = np.array(pv_cfg['default'])
                else:
                    intial_value = np.zeros(length, dtype=np.float64)

                nt_kwargs = {
                    'display': settings['display'] is not None,
                    'control': settings['control'] is not None,
                    'valueAlarm': settings['valueAlarm'] is not None,
                }
                pv_type_nt = NTScalar('ad', **nt_kwargs)
                payload = {'value': intial_value}
                payload = self._payload_apply_metadata(payload, settings)
                pv_type_init = payload if len(payload) > 1 else intial_value
            else:
                nt_kwargs = {
                    'display': settings['display'] is not None,
                    'control': settings['control'] is not None,
                    'valueAlarm': settings['valueAlarm'] is not None,
                }
                pv_type_nt = NTScalar('d', **nt_kwargs)
                intial_value = float(pv_cfg['default']) if 'default' in pv_cfg else 0.0
                payload = {'value': intial_value}
                payload = self._payload_apply_metadata(payload, settings)
                payload, _ = self._prepare_write_payload(pv, payload)
                pv_type_init = payload

            class Handler:
                """Simple handler to reject writes to read-only outputs"""

                def __init__(self, owner, pv_name: str, read_only: bool = False):
                    self.owner = owner
                    self.pv_name = pv_name
                    self.read_only = read_only

                def put(self, pv: SharedPV, op: ServOpWrap):
                    if self.read_only:
                        op.done(error='Model outputs are read-only')
                        return
                    try:
                        payload, _ = self.owner._prepare_write_payload(
                            self.pv_name, op.value()
                        )
                    except Exception as exc:
                        op.done(error=str(exc))
                        return
                    pv.post(payload, timestamp=time.time())
                    op.done()

            # PVs that are exclusively outputs are considered read-only
            read_only = False
            if 'mode' in pv_cfg:
                read_only = pv_cfg['mode'] == 'out'

            pv_item = {
                pv: SharedPV(
                    initial=pv_type_init,
                    nt=pv_type_nt,
                    handler=Handler(self, pv, read_only),
                )
            }
            # print(f"pv_item: {pv_item}")
            # print(f"pv_type_init: {pv_type_init}")
            # print(f"pv_type_nt: {pv_type_nt}")

            self.shared_pvs[pv] = pv_item[pv]

        self.provider = StaticProvider('pva')
        for name, pv in self.shared_pvs.items():
            self.provider.add(name, pv)

        self.server = Server(
            providers=[self.provider], conf={'EPICS_PVA_SERVER_PORT': str(port)}
        )

        # for pv in self.pv_list:
        #     self.server.start()
        logger.info(
            f'SimplePVAInterfaceServer initialized with config: {self.server.conf()}'
        )

    def close(self):
        logger.debug('Closing SimplePVAInterfaceServer')
        self.server.stop()
        super().close()

    def put(self, name, value, **kwargs):
        payload, _ = self._prepare_write_payload(name, value)
        # if not open then open
        if not self.shared_pvs[name].isOpen():
            self.shared_pvs[name].open(payload)
        else:
            self.shared_pvs[name].post(payload, timestamp=time.time())

    def get(self, name, **kwargs):
        value_raw = self.shared_pvs[name].current().raw
        if isinstance(value_raw.value, np.ndarray):
            # if value has dimension
            if 'dimension' in value_raw:
                y_size = value_raw.dimension[0]['size']
                x_size = value_raw.dimension[1]['size']
                value = value_raw.value.reshape((y_size, x_size))
            else:
                value = value_raw.value

        elif (
            type(value_raw.value) == float
            or type(value_raw.value) == int
            or type(value_raw.value) == bool
        ):
            value = value_raw.value

        else:
            raise ValueError(f'Unknown type for value_raw: {type(value_raw.value)}')
        # print(f"value: {value}")
        return name, {'value': value}

    def put_many(self, data, **kwargs):
        # for key, value in data.items():
        #     self.put(key, value)
        for key, value in data.items():
            # result = self.ctxt.put(key, value)
            payload, _ = self._prepare_write_payload(key, value)
            self.shared_pvs[key].post(payload, timestamp=time.time())
        # result = self.ctxt.put(channel_names,values, throw=False)
        # with ThreadPool(processes=24) as pool:
        # for key, value in data.items():
        #     channel_names.append(key)
        #     values.append(value)
        # pool.starmap(self.put, zip(channel_names, values))

    def get_many(self, data, **kwargs):
        output_dict = {}
        for key in data:
            result = self.get(key)
            output_dict[result[0]] = result[1]
        # with ThreadPool(processes=24) as pool:
        #     results = pool.starmap(self.get, [(key,) for key in data])
        #     for result in results:
        #         output_dict[result[0]] = result[1]

        return output_dict
