"""
Transformers module.

Contains base transformer classes and built-in transformer implementations.
"""

from poly_lithic.src.transformers.BaseTransformer import BaseTransformer
from poly_lithic.src.transformers.CompoundTransformer import CompoundTransformer
from poly_lithic.src.transformers.BaseTransformers import SimpleTransformer
from poly_lithic.src.transformers.BaseTransformers import PassThroughTransformer
from poly_lithic.src.transformers.BaseTransformers import CAImageTransfomer

registered_transformers = {
    'SimpleTransformer': SimpleTransformer,
    'CompoundTransformer': CompoundTransformer,
    'PassThroughTransformer': PassThroughTransformer,
    'CAImageTransfomer': CAImageTransfomer,
}

__all__ = [
    'BaseTransformer',
    'SimpleTransformer',
    'CompoundTransformer',
    'PassThroughTransformer',
    'CAImageTransfomer',
    'registered_transformers',
]