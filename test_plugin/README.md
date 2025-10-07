# test_plugin

A poly_lithic plugin package

## Installation

```bash
pip install -e .
```

## Usage

This package provides three types of plugins. Comment out the ones you don't need:

### Interface Plugin
```python
from poly_lithic.src.utils.plugin_registry import interface_plugin_registry

interface = interface_plugin_registry.get("test_plugin_interface")
instance = interface(config)
```

### Transformer Plugin
```python
from poly_lithic.src.utils.plugin_registry import transformer_plugin_registry

transformer = transformer_plugin_registry.get("test_plugin_transformer")
instance = transformer(config)
```

### Model Getter Plugin
```python
from poly_lithic.src.utils.plugin_registry import model_getter_plugin_registry

getter = model_getter_plugin_registry.get("test_plugin_model_getter")
model = getter.load_model()
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Customization

1. Edit `test_plugin/plugins.py` to implement your plugin logic
2. Comment out plugin types you don't need in `test_plugin/__init__.py`
3. Update `pyproject.toml` entry points to match your needs

## License

test_plugin is released under the MIT License.