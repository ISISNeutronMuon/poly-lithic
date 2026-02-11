"""
Interfaces module.
"""

from poly_lithic.src.interfaces.BaseInterface import BaseInterface, BaseDataInterface
from poly_lithic.src.interfaces.file_interface import h5dfInterface
from poly_lithic.src.interfaces.p4p_interface import SimplePVAInterface, SimplePVAInterfaceServer
from poly_lithic.src.interfaces.fastapi_interface import SimpleFastAPIInterfaceServer

try:
    from poly_lithic.src.interfaces.k2eg_interface import K2EGInterface
except ImportError:
    K2EGInterface = None

registered_interfaces = {
    'file': h5dfInterface,
    'p4p': SimplePVAInterface,
    'p4p_server': SimplePVAInterfaceServer,
    'fastapi_server': SimpleFastAPIInterfaceServer,
}

if K2EGInterface is not None:
    registered_interfaces['k2eg'] = K2EGInterface

__all__ = [
    'BaseInterface',
    'BaseDataInterface',
    'h5dfInterface',
    'SimplePVAInterface',
    'SimplePVAInterfaceServer',
    'K2EGInterface',
    'SimpleFastAPIInterfaceServer',
    'registered_interfaces',
]