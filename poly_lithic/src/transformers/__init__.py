from poly_lithic.src.utils.lazyInterfaceLoader import AbstractInterfaceLoader


class TransformerLoader(AbstractInterfaceLoader):
    def __init__(self):
        super().__init__()

    def keys(self):
        return [
            'SimpleTransformer',
            'CAImageTransfomer',
            'CompoundTransformer',
            'PassThroughTransformer',
        ]

    def _load_interface(self, key):
        if key == 'SimpleTransformer':
            return self.import_module(
                '.transformers.BaseTransformers', 'SimpleTransformer'
            )
        elif key == 'CAImageTransfomer':
            return self.import_module(
                '.transformers.BaseTransformers', 'CAImageTransfomer'
            )
        elif key == 'CompoundTransformer':
            return self.import_module(
                '.transformers.CompoundTransformer', 'CompoundTransformer'
            )
        elif key == 'PassThroughTransformer':
            return self.import_module(
                '.transformers.BaseTransformers', 'PassThroughTransformer'
            )
        else:
            raise KeyError(f"Interface '{key}' not registered.")


registered_transformers = TransformerLoader()
