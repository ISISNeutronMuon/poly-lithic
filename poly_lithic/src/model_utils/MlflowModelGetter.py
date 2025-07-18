import mlflow
from mlflow import MlflowClient
from mlflow.models.model import get_model_info
from poly_lithic.src.logging_utils import get_logger
from poly_lithic.src.model_utils import ModelGetterBase
import warnings

# not implemented error
import sys

logger = get_logger()

try:
    from lume_model.models import TorchModel, TorchModule

    LUME_MODEL_AVAILABLE = True
except ImportError:
    logger.warning(
        'lume_model is not installed. TorchModel and TorchModule functionality will not be available.'
    )
    LUME_MODEL_AVAILABLE = False


class MLflowModelGetterLegacy(ModelGetterBase):
    def __init__(self, config):
        # raise a futture warning if legacy model getter is used
        if self.__class__ == MLflowModelGetterLegacy:
            warnings.warn(
                'MLflowModelGetterLegacy is unmaintained. Use MLflowModelGetter instead.',
                FutureWarning,
            )

        model_name = config['model_name']
        # either supply version or URI
        if 'model_version' in config.keys():
            model_version = config['model_version']
            model_uri = None
        elif 'model_uri' in config.keys():
            model_uri = config['model_uri']
            model_version = None
        else:
            raise Exception('Either model_version or model_uri must be supplied')

        logger.debug(f'MLflowModelGetter: {model_name}, {model_version}')
        self.model_name = model_name

        self.model_version = model_version
        self.model_uri = model_uri
        self.client = MlflowClient()
        self.model_type = None
        self.tags = None

    def get_requirements(self):
        # Get dependencies

        if int(self.model_version) >= 0:
            version = self.client.get_model_version(self.model_name, self.model_version)
        elif self.model_version == 'champion':  # this is stupid I need to change it
            version_no = self.client.get_model_version_by_alias(
                self.model_name, self.model_version
            )
            version = self.client.get_model_version(self.model_name, version_no.version)
        else :
            raise ValueError(
                f'Invalid model version: {self.model_version}. Must be a non-negative integer or "champion".'
            )
        if not version:
            raise ValueError(
                f'Model version {self.model_version} not found for model {self.model_name}.'
            )
        deps = mlflow.artifacts.download_artifacts(f'{version.source}/requirements.txt')
        return deps

    def get_model(self):
        if self.model_uri is not None:
            model_uri = self.model_uri
        elif self.model_version is not None:
            version = self.client.get_model_version(self.model_name, self.model_version)
            model_uri = version.source
        else:
            raise Exception(
                'Either model_version and model name or model_uri must be supplied'
            )

        # flavor
        flavor = get_model_info(model_uri=model_uri).flavors
        loader_module = flavor['python_function']['loader_module']
        logger.debug(f'Loader module: {loader_module}')

        if loader_module == 'mlflow.pyfunc.model':
            logger.debug('Loading pyfunc model')
            model_pyfunc = mlflow.pyfunc.load_model(model_uri=model_uri)

            # check if model has.get_lume_model() method
            if not hasattr(model_pyfunc.unwrap_python_model(), 'get_lume_model'):
                # check if it has get__model() method
                if not hasattr(model_pyfunc.unwrap_python_model(), 'get_model'):
                    raise Exception(
                        'Model does not have get_lume_model() or get_model() method'
                    )
                else:
                    logger.debug('Model has get_model() method')
                    logger.warning(
                        'get_model() suggests a non-LUME model, please check if model has an evaluate method'
                    )
                    model = model_pyfunc.unwrap_python_model().get_model()
            else:
                logger.debug('Model has get_lume_model() method')
                model = model_pyfunc.unwrap_python_model().get_lume_model()

            logger.debug(f'Model: {model}, Model type: {type(model)}')
            self.model_type = 'pyfunc'
            return model

        elif loader_module == 'mlflow.pytorch':
            print('Loading torch model')
            model_torch_module = mlflow.pytorch.load_model(model_uri=model_uri)
            assert isinstance(model_torch_module, TorchModule)
            model = model_torch_module.model
            assert isinstance(model, TorchModel)
            logger.debug(f'Model: {model}, Model type: {type(model)}')
            self.model_type = 'torch'
            return model
        else:
            raise Exception(f'Flavor {flavor} not supported')


class MLflowModelGetter(MLflowModelGetterLegacy):
    def __init__(self, config):
        # Call parent class initialization first
        super().__init__(config)

    def get_model(self):
        
        # we onlu need to verify the model is a pyfunc model
        if self.model_uri is not None:
            model_uri = self.model_uri
        elif self.model_version is not None:
            version = self.client.get_model_version(self.model_name, self.model_version)
            model_uri = version.source
        else:
            raise Exception(
                'Either model_version and model name or model_uri must be supplied'
            )

        # flavor
        flavor = get_model_info(model_uri=model_uri).flavors
        loader_module = flavor['python_function']['loader_module']
        logger.debug(f'Loader module: {loader_module}')
        
        if loader_module == 'mlflow.pyfunc.model':
            # load the model
            mlflow_model = mlflow.pyfunc.load_model(
                model_uri=model_uri
            )

            # access the wrapped Python Pyfunc model
            model = mlflow_model.unwrap_python_model()
            # res = model.evaluate({"x": 0, "y": 0})  # test if the model has an evaluate method
            # print(f'Model evaluation result: {res}') # cant test becuse of mlflow wierdness
        else:
            raise TypeError(
                f'Expected a pyfunc model, but got {loader_module}.'
            )
            
        # validate that the model has an evaluate method
        logger.debug(f'Model: {model}, Model type: {type(model)}')
        
        return model