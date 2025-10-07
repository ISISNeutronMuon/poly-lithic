"""
Interfaces module.
"""

from poly_lithic.src.interfaces.BaseInterface import BaseInterface, BaseDataInterface
from poly_lithic.src.interfaces.file_interface import h5dfInterface
from poly_lithic.src.interfaces.p4p_interface import SimplePVAInterface
from poly_lithic.src.interfaces.k2eg_interface import K2EGInterface

registered_interfaces = {
    'file': h5dfInterface,
    'p4p': SimplePVAInterface,
    'k2eg': K2EGInterface,
}

__all__ = [
    'BaseInterface',
    'BaseDataInterface',
    'h5dfInterface',
    'SimplePVAInterface',
    'K2EGInterface',
    'registered_interfaces',
]