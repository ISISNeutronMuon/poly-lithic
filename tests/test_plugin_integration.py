"""
Integration tests for the plugin system.
Tests real-world scenarios of plugin discovery, loading, and usage.
"""

import pytest
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import importlib.metadata

from poly_lithic.src.utils.plugin_registry import (
    PluginRegistry,
    interface_plugin_registry,
    transformer_plugin_registry,
    model_getter_plugin_registry,
)
from poly_lithic.src.interfaces.BaseInterface import BaseInterface as Interface
from poly_lithic.src.transformers.BaseTransformers import BaseTransformer as Transformer
from poly_lithic.src.model_utils.ModelGetterBase import ModelGetterBase


# ============================================================================
# Mock Plugin Classes
# ============================================================================

class MockCustomInterface(Interface):
    """A mock custom interface plugin"""
    
    def __init__(self, config):
        super().__init__(config)
        self.config = config 
        self.connected = False
    
    def put(self, variable, value):
        return {variable: value}
    
    def get(self, variable):
        return variable, {"value": 42, "timestamp": 0}
    
    def get_many(self, variables):
        """Get multiple variables at once"""
        return {var: {"value": 42, "timestamp": 0} for var in variables}
    
    def put_many(self, variable_values):
        """Put multiple variables at once"""
        return variable_values
    
    def monitor(self, variables, callback):
        """Monitor variables for changes"""
        pass
    
    def connect(self):
        self.connected = True
    
    def close(self):
        self.connected = False


class MockCustomTransformer(Transformer):
    """A mock custom transformer plugin"""
    
    def __init__(self, config):
        super().__init__(config)
        self.transform_called = False
    
    def transform(self, input_data):
        self.transform_called = True
        return {k: v * 2 for k, v in input_data.items()}


class MockCustomModelGetter:
    """A mock custom model getter plugin"""
    
    def __init__(self, config):
        self.config = config
        self.model_loaded = False
    
    def load_model(self):
        self.model_loaded = True
        return MagicMock()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def clean_registries():
    """Clean up registries before and after tests"""
    # Store original state
    original_interfaces = dict(interface_plugin_registry._plugins)
    original_transformers = dict(transformer_plugin_registry._plugins)
    original_getters = dict(model_getter_plugin_registry._plugins)
    
    # Clear registries
    interface_plugin_registry._plugins.clear()
    transformer_plugin_registry._plugins.clear()
    model_getter_plugin_registry._plugins.clear()
    interface_plugin_registry._loaded = False
    transformer_plugin_registry._loaded = False
    model_getter_plugin_registry._loaded = False
    
    yield
    
    # Restore original state
    interface_plugin_registry._plugins = original_interfaces
    transformer_plugin_registry._plugins = original_transformers
    model_getter_plugin_registry._plugins = original_getters
    interface_plugin_registry._loaded = False
    transformer_plugin_registry._loaded = False
    model_getter_plugin_registry._loaded = False


@pytest.fixture
def mock_entry_points():
    """Mock entry points for testing plugin discovery"""
    
    class MockEntryPoint:
        def __init__(self, name, value, group):
            self.name = name
            self.value = value
            self.group = group
        
        def load(self):
            module_path, class_name = self.value.split(':')
            if class_name == 'MockCustomInterface':
                return MockCustomInterface
            elif class_name == 'MockCustomTransformer':
                return MockCustomTransformer
            elif class_name == 'MockCustomModelGetter':
                return MockCustomModelGetter
            raise ImportError(f"Cannot load {self.value}")
    
    # Create a dictionary that mimics the SelectableGroups object
    class MockSelectableGroups(dict):
        def select(self, **kwargs):
            group = kwargs.get('group')
            if group:
                return self.get(group, [])
            # Return all entry points
            all_eps = []
            for eps in self.values():
                all_eps.extend(eps)
            return all_eps
    
    mock_eps = MockSelectableGroups({
        'poly_lithic.interfaces': [
            MockEntryPoint('mock_interface', 'test.plugins:MockCustomInterface', 'poly_lithic.interfaces'),
        ],
        'poly_lithic.transformers': [
            MockEntryPoint('mock_transformer', 'test.plugins:MockCustomTransformer', 'poly_lithic.transformers'),
        ],
        'poly_lithic.model_getters': [
            MockEntryPoint('mock_getter', 'test.plugins:MockCustomModelGetter', 'poly_lithic.model_getters'),
        ],
    })
    
    def mock_entry_points_func(group=None):
        if group:
            return mock_eps.get(group, [])
        return mock_eps
    
    with patch('importlib.metadata.entry_points', side_effect=mock_entry_points_func):
        yield mock_eps


# ============================================================================
# Integration Tests
# ============================================================================

class TestPluginDiscoveryIntegration:
    """Test plugin discovery and loading"""
    
    def test_discover_interface_plugins(self, clean_registries, mock_entry_points):
        """Test discovering interface plugins via entry points"""
        registry = PluginRegistry("poly_lithic.interfaces")
        registry.discover_plugins()
        
        assert registry.has_plugin("mock_interface")
        assert registry.get("mock_interface") == MockCustomInterface
    
    def test_discover_transformer_plugins(self, clean_registries, mock_entry_points):
        """Test discovering transformer plugins via entry points"""
        registry = PluginRegistry("poly_lithic.transformers")
        registry.discover_plugins()
        
        assert registry.has_plugin("mock_transformer")
        assert registry.get("mock_transformer") == MockCustomTransformer
    
    def test_discover_model_getter_plugins(self, clean_registries, mock_entry_points):
        """Test discovering model getter plugins via entry points"""
        registry = PluginRegistry("poly_lithic.model_getters")
        registry.discover_plugins()
        
        assert registry.has_plugin("mock_getter")
        assert registry.get("mock_getter") == MockCustomModelGetter
    
    def test_discover_all_plugin_types(self, clean_registries, mock_entry_points):
        """Test discovering all plugin types"""
        interface_plugin_registry.discover_plugins()
        transformer_plugin_registry.discover_plugins()
        model_getter_plugin_registry.discover_plugins()
        
        assert "mock_interface" in interface_plugin_registry
        assert "mock_transformer" in transformer_plugin_registry
        assert "mock_getter" in model_getter_plugin_registry


class TestPluginInstantiationIntegration:
    """Test instantiating and using plugins"""
    
    def test_instantiate_interface_plugin(self, clean_registries):
        """Test creating an instance of an interface plugin"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        config = {
            "variables": {
                "test:pv": {"name": "test:pv", "proto": "mock"}
            }
        }
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        interface = InterfaceClass(config)
        
        assert isinstance(interface, MockCustomInterface)
        assert not interface.connected
        
        interface.connect()
        assert interface.connected
        
        # Test interface methods
        name, value = interface.get("test:pv")
        assert value["value"] == 42
        
        result = interface.put("test:pv", 100)
        assert result["test:pv"] == 100
        
        # Test get_many
        results = interface.get_many(["test:pv", "test:pv2"])
        assert len(results) == 2
        assert all(v["value"] == 42 for v in results.values())
        
        # Test put_many
        put_results = interface.put_many({"test:pv": 100, "test:pv2": 200})
        assert put_results["test:pv"] == 100
        assert put_results["test:pv2"] == 200
    
    def test_instantiate_transformer_plugin(self, clean_registries):
        """Test creating an instance of a transformer plugin"""
        transformer_plugin_registry.register("mock_transformer", MockCustomTransformer)
        
        config = {"multiplier": 2}
        
        TransformerClass = transformer_plugin_registry.get("mock_transformer")
        transformer = TransformerClass(config)
        
        assert isinstance(transformer, MockCustomTransformer)
        assert not transformer.transform_called
        
        # Test transformer
        input_data = {"a": 1, "b": 2, "c": 3}
        output = transformer.transform(input_data)
        
        assert transformer.transform_called
        assert output == {"a": 2, "b": 4, "c": 6}
    
    def test_instantiate_model_getter_plugin(self, clean_registries):
        """Test creating an instance of a model getter plugin"""
        model_getter_plugin_registry.register("mock_getter", MockCustomModelGetter)
        
        config = {"model_path": "/path/to/model"}
        
        GetterClass = model_getter_plugin_registry.get("mock_getter")
        getter = GetterClass(config)
        
        assert isinstance(getter, MockCustomModelGetter)
        assert not getter.model_loaded
        
        model = getter.load_model()
        assert getter.model_loaded
        assert model is not None


class TestPluginRegistryIntegration:
    """Test registry integration with the main system"""
    
    def test_manual_registration_before_discovery(self, clean_registries, mock_entry_points):
        """Test that manual registration takes precedence over discovery"""
        
        class CustomMockInterface(Interface):
            def __init__(self, config):
                super().__init__(config)
                self.is_custom = True
            
            def put(self, variable, value):
                return {variable: value}
            
            def get(self, variable):
                return variable, {"value": 999}
            
            def get_many(self, variables):
                return {var: {"value": 999} for var in variables}
            
            def put_many(self, variable_values):
                return variable_values
            
            def monitor(self, variables, callback):
                pass
            
            def connect(self):
                pass
            
            def close(self):
                pass
        
        # Register manually first
        interface_plugin_registry.register("mock_interface", CustomMockInterface)
        
        # Then discover (should not override)
        interface_plugin_registry.discover_plugins()
        
        # Should still have the manually registered version
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        instance = InterfaceClass({})
        assert hasattr(instance, 'is_custom')
        assert instance.is_custom
    
    def test_registry_iteration(self, clean_registries):
        """Test iterating over registered plugins"""
        interface_plugin_registry.register("plugin1", MockCustomInterface)
        interface_plugin_registry.register("plugin2", MockCustomInterface)
        
        names = list(interface_plugin_registry)
        assert "plugin1" in names
        assert "plugin2" in names
        
        for name, plugin_class in interface_plugin_registry.items():
            assert name in ["plugin1", "plugin2"]
            assert plugin_class == MockCustomInterface
    
    def test_plugin_listing(self, clean_registries, mock_entry_points):
        """Test listing all available plugins"""
        interface_plugin_registry.discover_plugins()
        transformer_plugin_registry.discover_plugins()
        model_getter_plugin_registry.discover_plugins()
        
        interfaces = interface_plugin_registry.list_plugins()
        transformers = transformer_plugin_registry.list_plugins()
        getters = model_getter_plugin_registry.list_plugins()
        
        assert "mock_interface" in interfaces
        assert "mock_transformer" in transformers
        assert "mock_getter" in getters


class TestPluginErrorHandling:
    """Test error handling in plugin system"""
    
    def test_load_nonexistent_plugin(self, clean_registries):
        """Test error when loading non-existent plugin"""
        with pytest.raises(KeyError):
            interface_plugin_registry.get("nonexistent_plugin")
    
    def test_malformed_entry_point(self, clean_registries):
        """Test handling of malformed entry points"""
        
        class BadEntryPoint:
            def __init__(self):
                self.name = "bad_plugin"
            
            def load(self):
                raise ImportError("Cannot import bad plugin")
        
        with patch('importlib.metadata.entry_points') as mock_eps:
            mock_eps.return_value = [BadEntryPoint()]
            
            registry = PluginRegistry("poly_lithic.interfaces")
            # Should not crash, just skip bad plugins
            registry.discover_plugins()
            
            assert not registry.has_plugin("bad_plugin")
    
    def test_plugin_instantiation_error(self, clean_registries):
        """Test error when plugin instantiation fails"""
        
        class FailingPlugin:
            def __init__(self, config):
                raise ValueError("Invalid configuration")
        
        interface_plugin_registry.register("failing", FailingPlugin)
        
        PluginClass = interface_plugin_registry.get("failing")
        with pytest.raises(ValueError, match="Invalid configuration"):
            PluginClass({})


class TestPluginWorkflow:
    """Test complete workflows using plugins"""
    
    def test_interface_workflow(self, clean_registries):
        """Test a complete interface workflow with plugins"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        # Simulate workflow
        config = {
            "variables": {
                "input:pv": {"name": "input:pv", "proto": "mock"},
                "output:pv": {"name": "output:pv", "proto": "mock"}
            }
        }
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        interface = InterfaceClass(config)
        
        # Connect
        interface.connect()
        
        # Read input
        name, input_value = interface.get("input:pv")
        assert input_value["value"] == 42
        
        # Process (double the value)
        processed_value = input_value["value"] * 2
        
        # Write output
        result = interface.put("output:pv", processed_value)
        assert result["output:pv"] == 84
        
        # Disconnect
        interface.close()
        assert not interface.connected
    
    def test_transformer_workflow(self, clean_registries):
        """Test a complete transformer workflow with plugins"""
        transformer_plugin_registry.register("mock_transformer", MockCustomTransformer)
        
        # Simulate workflow
        config = {"operation": "double"}
        
        TransformerClass = transformer_plugin_registry.get("mock_transformer")
        transformer = TransformerClass(config)
        
        # Transform data
        input_data = {"x": 10, "y": 20, "z": 30}
        output_data = transformer.transform(input_data)
        
        assert output_data == {"x": 20, "y": 40, "z": 60}
        assert transformer.transform_called
    
    def test_model_getter_workflow(self, clean_registries):
        """Test a complete model getter workflow with plugins"""
        model_getter_plugin_registry.register("mock_getter", MockCustomModelGetter)
        
        # Simulate workflow
        config = {
            "model_path": "/models/my_model",
            "version": "v1.0"
        }
        
        GetterClass = model_getter_plugin_registry.get("mock_getter")
        getter = GetterClass(config)
        
        # Load model
        model = getter.load_model()
        
        assert getter.model_loaded
        assert model is not None
    
    def test_combined_workflow(self, clean_registries):
        """Test a workflow combining interface, transformer, and model"""
        # Register all plugins
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        transformer_plugin_registry.register("mock_transformer", MockCustomTransformer)
        model_getter_plugin_registry.register("mock_getter", MockCustomModelGetter)
        
        # Setup components
        interface = interface_plugin_registry.get("mock_interface")({
            "variables": {"input:pv": {"name": "input:pv", "proto": "mock"}}
        })
        transformer = transformer_plugin_registry.get("mock_transformer")({})
        model_getter = model_getter_plugin_registry.get("mock_getter")({"model_path": "/model"})
        
        # Workflow: Read -> Transform -> Process with Model -> Write
        interface.connect()
        
        # 1. Read from interface
        name, raw_data = interface.get("input:pv")
        input_dict = {"value": raw_data["value"]}
        
        # 2. Transform
        transformed = transformer.transform(input_dict)
        
        # 3. Load model (in real scenario, would use model for prediction)
        model = model_getter.load_model()
        
        # 4. Write result
        result = interface.put("output:pv", transformed["value"])
        
        assert result["output:pv"] == 84  # 42 * 2
        interface.close()


class TestPluginCompatibility:
    """Test plugin compatibility and versioning"""
    
    def test_plugin_with_base_class(self, clean_registries):
        """Test that plugins properly inherit from base classes"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        instance = InterfaceClass({})
        
        # Check inheritance
        assert isinstance(instance, Interface)
        assert isinstance(instance, MockCustomInterface)
        
        # Check base class methods are available
        assert hasattr(instance, 'put')
        assert hasattr(instance, 'get')
        assert hasattr(instance, 'get_many')
        assert hasattr(instance, 'put_many')
        assert hasattr(instance, 'monitor')
        assert hasattr(instance, 'connect')
        assert hasattr(instance, 'close')
    
    def test_plugin_config_compatibility(self, clean_registries):
        """Test that plugins handle various config formats"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        configs = [
            {"variables": {"pv1": {"name": "pv1"}}},  # Minimal config
            {"variables": {}, "other_field": "value"},  # Extra fields
            {"variables": {"pv1": {"name": "pv1", "proto": "mock", "extra": True}}},  # Extra nested
        ]
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        
        for config in configs:
            instance = InterfaceClass(config)
            assert instance is not None
            assert hasattr(instance, 'config')


class TestPluginDocumentation:
    """Test that plugins provide proper documentation"""
    
    def test_plugin_has_docstring(self, clean_registries):
        """Test that plugin classes have docstrings"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        assert InterfaceClass.__doc__ is not None
        assert "mock custom interface" in InterfaceClass.__doc__.lower()
    
    def test_plugin_inspection(self, clean_registries):
        """Test that plugins can be inspected programmatically"""
        interface_plugin_registry.register("mock_interface", MockCustomInterface)
        
        InterfaceClass = interface_plugin_registry.get("mock_interface")
        
        # Check required methods exist
        assert callable(getattr(InterfaceClass, 'put', None))
        assert callable(getattr(InterfaceClass, 'get', None))
        assert callable(getattr(InterfaceClass, 'get_many', None))
        assert callable(getattr(InterfaceClass, 'put_many', None))
        assert callable(getattr(InterfaceClass, 'monitor', None))
        assert callable(getattr(InterfaceClass, 'connect', None))
        assert callable(getattr(InterfaceClass, 'close', None))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])