"""
Transformers module.

Contains base transformer classes and built-in transformer implementations.
"""

from poly_lithic.src.transformers.BaseTransformer import BaseTransformer
from poly_lithic.src.transformers.CompoundTransformer import CompoundTransformer
from poly_lithic.src.transformers.BaseTransformers import SimpleTransformer

registered_transformers = {
    'simple': SimpleTransformer,
    'compound': CompoundTransformer,
}

__all__ = [
    'BaseTransformer',
    'SimpleTransformer',
    'CompoundTransformer',
    'registered_transformers',
]
