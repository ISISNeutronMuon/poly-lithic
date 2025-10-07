"""
Model utilities module.
"""

from poly_lithic.src.model_utils.ModelGetterBase import ModelGetterBase
from poly_lithic.src.model_utils.MlflowModelGetter import MLflowModelGetter
from poly_lithic.src.model_utils.LocalModelGetter import LocalModelGetter

registered_model_getters = {
    'mlflow': MLflowModelGetter,
    'local': LocalModelGetter,
}

__all__ = [
    'ModelGetterBase',
    'MLflowModelGetter',
    'LocalModelGetter',
    'registered_model_getters',
]
