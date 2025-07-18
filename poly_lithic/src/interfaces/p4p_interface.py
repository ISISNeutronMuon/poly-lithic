import os
import time

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
        pv_list = []
        # print(f"pv_dict: {pv_dict}")
        for pv in pv_dict:
            try:
                assert pv_dict[pv]['proto'] == 'pva'
            except Exception:
                logger.error(f'Protocol for {pv} is not pva')
                raise AssertionError
            pv_list.append(pv_dict[pv]['name'])
        self.pv_list = pv_list
        self.variable_list = list(pv_dict.keys())
        logger.debug(f'SimplePVAInterface initialized with pv_url_list: {self.pv_list}')

    def __handler_wrapper(self, handler, name):
        # unwrap p4p.Value into name, value
        def wrapped_handler(value):
            # logger.debug(f"SimplePVAInterface handler for {name, value['value']}")

            handler(name, {'value': value['value']})

        return wrapped_handler

    def monitor(self, handler, **kwargs):
        for pv in self.pv_list:
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

    def put(self, name, value, **kwargs):
        if isinstance(value, np.ndarray):
            value = NTNDArray().wrap(value)
        else:
            value = value
        return self.ctxt.put(name, value)

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


class SimlePVAInterfaceServer(SimplePVAInterface):
    """
    Simple PVA integfcae with a server rather than just a client, this will host the PVs provided in the config
    """

    def __init__(self, config):
        super().__init__(config)
        self.shared_pvs = {}
        pv_type_init = None
        pv_type_nt = None
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

        for pv in self.pv_list:
            if 'type' in config['variables'][pv]:
                pv_type = config['variables'][pv]['type']
                if pv_type == 'image':
                    # note the y and x are flipped when reshaping (rows, columns) -> (y, x)
                    y_size = config['variables'][pv]['image_size']['y']
                    x_size = config['variables'][pv]['image_size']['x']
                    intial_value = np.zeros((y_size, x_size))
                    pv_type_nt = NTNDArray()
                    pv_type_init = intial_value
                    self.value_build_fn = None
                    if 'default' in config['variables'][pv]:
                        raise NotImplementedError(
                            'Default values for images not implemented'
                        )

                # waveform or array
                elif pv_type == 'waveform' or pv_type == 'array':
                    # print(f'pv: {pv}')
                    if 'length' in config['variables'][pv]:
                        length = config['variables'][pv]['length']
                    else:
                        length = 10
                    if 'default' in config['variables'][pv]:
                        intial_value = np.array(config['variables'][pv]['default'])
                    else:
                        intial_value = np.zeros(length, dtype=np.float64)

                    pv_type_nt = NTScalar('ad')
                    pv_type_nt_bd = NTScalar.buildType('ad')
                    self.value_build_fn = Value(pv_type_nt_bd, {'value': intial_value})
                    pv_type_init = intial_value

                elif pv_type == 'scalar':
                    pv_type_nt = NTScalar('d')
                    if 'default' in config['variables'][pv]:
                        pv_type_init = float(config['variables'][pv]['default'])
                    else:
                        pv_type_init = 0.0

                else:
                    raise TypeError(f'Unknown PV type for {pv}: {pv_type}')
            else:
                pv_type_nt = NTScalar('d')
                if 'default' in config['variables'][pv]:
                    pv_type_init = float(config['variables'][pv]['default'])
                else:
                    pv_type_init = 0.0
                self.value_build_fn = None

            pv_item = {pv: SharedPV(initial=pv_type_init, nt=pv_type_nt)}
            # print(f"pv_item: {pv_item}")
            # print(f"pv_type_init: {pv_type_init}")
            # print(f"pv_type_nt: {pv_type_nt}")

            @pv_item[pv].put
            def put(pv: SharedPV, op: ServOpWrap):
                pv.post(op.value(), timestamp=time.time())
                op.done()

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
        # if not open then open
        if not self.shared_pvs[name].isOpen():
            self.shared_pvs[name].open(value)
        else:
            self.shared_pvs[name].post(value, timestamp=time.time())

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
            self.shared_pvs[key].post(value, timestamp=time.time())
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
