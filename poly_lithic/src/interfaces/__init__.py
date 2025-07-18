from poly_lithic.src.utils.lazyInterfaceLoader import AbstractInterfaceLoader


class InterfaceLoader(AbstractInterfaceLoader):
    def __init__(self):
        super().__init__()

    def keys(self):
        return ['k2eg', 'p4p', 'p4p_server', 'h5df']

    def _load_interface(self, key):
        if key == 'k2eg':
            return self.import_module('.interfaces.k2eg_interface', 'K2EGInterface')
        elif key == 'p4p':
            return self.import_module('.interfaces.p4p_interface', 'SimplePVAInterface')
        elif key == 'p4p_server':
            return self.import_module(
                '.interfaces.p4p_interface', 'SimlePVAInterfaceServer'
            )
        elif key == 'h5df':
            return self.import_module('.interfaces.file_interface', 'h5dfInterface')
        else:
            raise KeyError(f"Interface '{key}' not registered.")


registered_interfaces = InterfaceLoader()
