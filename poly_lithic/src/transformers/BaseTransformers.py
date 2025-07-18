import time
import numpy as np
import sympy as sp
from poly_lithic.src.logging_utils.make_logger import get_logger
from poly_lithic.src.transformers.BaseTransformer import BaseTransformer

logger = get_logger()


class SimpleTransformer(BaseTransformer):
    def __init__(self, config):
        """
        config: dict
            dictionary containing the following keys:
            - variables: dict
                dictionary containing the following keys:
                - formula: str
                    formula to be used for transformation
            - symbols: list
                list of symbols to be used in the formula
        """

        pv_mapping = config['variables']
        self.input_list = config['symbols']

        logger.debug('Initializing SimpleTransformer')
        logger.debug(f'PV Mapping: {pv_mapping}')
        logger.debug(f'Symbol List: {self.input_list}')
        self.pv_mapping = pv_mapping

        for key, value in self.pv_mapping.items():
            self.__validate_formulas(value['formula'])
        self.latest_input = {symbol: None for symbol in self.input_list}
        self.latest_transformed = {key: 0 for key in self.pv_mapping.keys()}
        self.updated = False
        self.handler_time = None
        self.formulas = {}
        self.lambdified_formulas = {}
        for key, value in self.pv_mapping.items():
            self.formulas[key] = sp.sympify(value['formula'].replace(':', '_'))
            input_list_renamed = [
                symbol.replace(':', '_') for symbol in self.input_list
            ]
            self.lambdified_formulas[key] = sp.lambdify(
                input_list_renamed, self.formulas[key], modules='numpy'
            )

        self.handler_time = []

    def __validate_formulas(self, formula: str):
        try:
            sp.sympify(formula.replace(':', '_'))
        except Exception as e:
            raise Exception(f'Invalid formula: {formula}: {e}')

    def handler(self, pv_name, value):
        # logger.debug(f"SimpleTransformer handler for {pv_name} with value {value}")

        # chek if pv_name is in sel.input_list
        if pv_name in self.input_list:
            # assert value is float
            try:
                if isinstance(value['value'], (float, int, np.float32)):
                    value = float(value['value'])
                elif isinstance(value['value'], (np.ndarray, list)):
                    value = np.array(value['value']).astype(float)
                else:
                    raise Exception(
                        f'Invalid type for value: {value}, type: {type(value["value"])}'
                    )
            except Exception as e:
                logger.error(f'Error converting value to float: {e}')
                raise e

            self.latest_input[pv_name] = value

            try:
                if all([value is not None for value in self.latest_input.values()]):
                    time_start = time.time()
                    self.transform()
                    self.handler_time = time.time() - time_start
                    # logger.info(f'Handler time for {pv_name} is {self.handler_time}')
                    # if self.handler_time > 0.5:
                    #     logger.warning(f'Handler time for {pv_name} is {self.handler_time}')
                    #     print(f'self.latest_input: {self.latest_input}')
                    #     print(f'self.latest_transformed: {self.latest_transformed}')
            except Exception as e:
                logger.error(f'Error transforming: {e}')
                raise e
        else:
            logger.debug(f'PV name {pv_name} not in input list')

    # def transform(self):
    #     # logger.debug("Transforming")
    #     transformed = {}
    #     pvs_renamed = {
    #         key.replace(':', '_'): value for key, value in self.latest_input.items()
    #     }
    #     pv_shapes = {}

    #     # convert to sympy symbols

    #     for key, value in pvs_renamed.items():
    #         if isinstance(value, (np.ndarray, list)):
    #             pv_shapes[key] = value.shape
    #             pvs_renamed[key] = sp.Matrix(value)
    #         elif isinstance(value, (float, int)):
    #             pvs_renamed[key] = value
    #         else:
    #             raise Exception(f'Invalid type for value: {value}')

    #     for key, value in self.pv_mapping.items():
    #         try:
    #             # formula = value['formula'].replace(':', '_')

    #             # formula = sp.sympify(formula)
    #             formula = self.formulas[key]
    #             transformed[key] = formula.subs(pvs_renamed)
    #             # print(transformed[key])
    #             # converted to float
    #             if isinstance(transformed[key], sp.Matrix | sp.ImmutableDenseMatrix):
    #                 # bit hacky but casuse sympy is meant to be symbolic only and not numerical
    #                 s = sp.symbols('s')
    #                 numpy_value = sp.lambdify(s, transformed[key], modules='numpy')
    #                 numpy_value = numpy_value(0)
    #                 transformed[key] = numpy_value
    #                 # drop last dim if it is 1
    #                 if transformed[key].shape[-1] == 1:
    #                     transformed[key] = transformed[key].squeeze()
    #             else:
    #                 transformed[key] = float(transformed[key])

    #         except Exception as e:
    #             logger.error(f'Error transforming: {e}')
    #             raise e

    #     for key, value in transformed.items():
    #         self.latest_transformed[key] = value
    #     self.updated = True
    def transform(self):
        transformed = {}
        pvs_renamed = {
            key.replace(':', '_'): value for key, value in self.latest_input.items()
        }

        for key, value in self.pv_mapping.items():
            try:
                lambdified_formula = self.lambdified_formulas[key]
                transformed[key] = lambdified_formula(*[
                    pvs_renamed[symbol.replace(':', '_')] for symbol in self.input_list
                ])

                if isinstance(transformed[key], np.ndarray):
                    if transformed[key].shape[-1] == 1:
                        transformed[key] = transformed[key].squeeze()
                else:
                    transformed[key] = float(transformed[key])

            except Exception as e:
                logger.error(f'Error transforming: {e}')
                raise e

        for key, value in transformed.items():
            self.latest_transformed[key] = value
        self.updated = True


class CAImageTransfomer(BaseTransformer):
    """Input only image transformation"""

    def __init__(self, config) -> None:
        self.img = config['variables']
        self.img_list = list(self.img.keys())

        self.variables = {}
        self.input_list = []
        for key, value in self.img.items():
            self.variables[key] = value['img_ch']
            self.variables[key + '_x'] = value['img_x_ch']
            self.variables[key + '_y'] = value['img_y_ch']
            if 'unfold' in value.keys():
                self.variables[key + '_unfolding'] = value['unfold']
            else:
                self.variables[key + '_unfolding'] = 'row_major'
            self.input_list.append(value['img_ch'])
            self.input_list.append(value['img_x_ch'])
            self.input_list.append(value['img_y_ch'])

        self.latest_input = {symbol: None for symbol in self.input_list}
        self.latest_transformed = {key: 0 for key in self.variables.keys()}

        self.handler_time = None
        self.updated = False

    def handler(self, variable_name: str, value: dict):
        logger.debug(f'CAImageTransfomer handler for {variable_name}')
        try:
            self.latest_input[variable_name] = value['value']
            if all([value is not None for value in self.latest_input.values()]):
                time_start = time.time()
                self.transform()
                self.handler_time = time.time() - time_start
            else:
                logger.debug('Not all values are present')
        except Exception as e:
            logger.error(f'Error transforming: {e}')
            raise e

    def transform(self):
        logger.debug('Transforming')
        transformed = {}
        for key in self.img_list:
            value = self.latest_input[self.variables[key]]
            # print x and y
            try:
                transformed[key] = np.array(value).reshape(
                    (
                        int(
                            self.latest_input[self.variables[key + '_y']]
                        ),  # note the order, we are going from x,y to y,x (rows, columns) in numpy
                        int(self.latest_input[self.variables[key + '_x']]),
                    ),
                    order='F'
                    if self.variables[key + '_unfolding'] == 'column_major'
                    else 'C',
                )

                if self.variables[key + '_unfolding'] == 'column_major':
                    transformed[key] = transformed[key].T
            except Exception as e:
                logger.error(f'Error transforming: {e}')
        for key, value in transformed.items():
            self.latest_transformed[key] = value
        self.updated = True


class PassThroughTransformer(BaseTransformer):
    def __init__(self, config):
        # config is a dictionary of output:intput pairs
        pv_mapping = config['variables']
        self.latest_input = {}
        self.latest_transformed = {}
        self.updated = False
        self.input_list = list(pv_mapping.values())

        for key, value in pv_mapping.items():
            self.latest_input[value] = None
            self.latest_transformed[key] = None
        self.pv_mapping = pv_mapping

        self.handler_time = 0

    def handler(self, pv_name, value):
        time_start = time.time()
        logger.debug(f'PassThroughTransformer handler for {pv_name}')
        self.latest_input[pv_name] = value['value']
        if all([value is not None for value in self.latest_input.values()]):
            self.transform()
        self.updated = True
        time_end = time.time()
        self.handler_time = time_end - time_start

    def transform(self):
        logger.debug('Transforming')
        for key, value in self.pv_mapping.items():
            self.latest_transformed[key] = self.latest_input[value]

            if isinstance(self.latest_input[value], np.ndarray):
                if self.latest_input[value].shape != self.latest_transformed[key].shape:
                    logger.error(f'Shape mismatch between input and output for {key}')
        self.updated = True

        # for key, value in self.latest_input.items():
        #     logger.debug(f"{key}: {value.shape}")
        # for key, value in self.latest_transformed.items():
        #     logger.debug(f"{key}: {value.shape}")
