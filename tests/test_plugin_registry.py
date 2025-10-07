"""
Test the plugin registry system (AI generated so it s a bit exhaustive)
"""

import pytest
from poly_lithic.src.utils.plugin_registry import (
    PluginRegistry,
    interface_plugin_registry,
    transformer_plugin_registry,
    model_getter_plugin_registry,
    register_interface,
    register_transformer,
    register_model_getter,
)


class DummyPlugin:
    """A dummy plugin class for testing"""
    def __init__(self, config):
        self.config = config


class AnotherPlugin:
    """Another dummy plugin class for testing"""
    def __init__(self, config):
        self.config = config


class TestPluginRegistry:
    """Test the PluginRegistry class"""
    
    def test_init(self):
        """Test registry initialization"""
        registry = PluginRegistry("test.group")
        assert registry.entry_point_group == "test.group"
        assert registry._plugins == {}
        assert registry._loaded is False
    
    def test_manual_registration(self):
        """Test manual plugin registration"""
        registry = PluginRegistry("test.group")
        registry.register("dummy", DummyPlugin)
        
        assert registry.has_plugin("dummy")
        assert registry.get("dummy") == DummyPlugin
    
    def test_register_override(self):
        """Test that manual registration can override"""
        registry = PluginRegistry("test.group")
        registry.register("plugin", DummyPlugin)
        registry.register("plugin", AnotherPlugin)
        
        assert registry.get("plugin") == AnotherPlugin
    
    def test_unregister(self):
        """Test plugin unregistration"""
        registry = PluginRegistry("test.group")
        registry.register("dummy", DummyPlugin)
        
        assert registry.has_plugin("dummy")
        
        registry.unregister("dummy")
        assert not registry.has_plugin("dummy")
    
    def test_get_nonexistent(self):
        """Test getting a non-existent plugin"""
        registry = PluginRegistry("test.group")
        
        with pytest.raises(KeyError):
            registry.get("nonexistent")
    
    def test_list_plugins(self):
        """Test listing plugins"""
        registry = PluginRegistry("test.group")
        registry.register("plugin1", DummyPlugin)
        registry.register("plugin2", AnotherPlugin)
        
        plugins = registry.list_plugins()
        assert "plugin1" in plugins
        assert "plugin2" in plugins
        assert len(plugins) == 2
    
    def test_contains(self):
        """Test __contains__ operator"""
        registry = PluginRegistry("test.group")
        registry.register("dummy", DummyPlugin)
        
        assert "dummy" in registry
        assert "nonexistent" not in registry
    
    def test_getitem(self):
        """Test __getitem__ operator"""
        registry = PluginRegistry("test.group")
        registry.register("dummy", DummyPlugin)
        
        assert registry["dummy"] == DummyPlugin
    
    def test_iteration(self):
        """Test iteration over plugin names"""
        registry = PluginRegistry("test.group")
        registry.register("plugin1", DummyPlugin)
        registry.register("plugin2", AnotherPlugin)
        
        names = list(registry)
        assert "plugin1" in names
        assert "plugin2" in names
    
    def test_items(self):
        """Test items() method"""
        registry = PluginRegistry("test.group")
        registry.register("plugin1", DummyPlugin)
        registry.register("plugin2", AnotherPlugin)
        
        items = dict(registry.items())
        assert items["plugin1"] == DummyPlugin
        assert items["plugin2"] == AnotherPlugin
    
    def test_keys(self):
        """Test keys() method"""
        registry = PluginRegistry("test.group")
        registry.register("plugin1", DummyPlugin)
        registry.register("plugin2", AnotherPlugin)
        
        keys = registry.keys()
        assert "plugin1" in keys
        assert "plugin2" in keys
    
    def test_values(self):
        """Test values() method"""
        registry = PluginRegistry("test.group")
        registry.register("plugin1", DummyPlugin)
        registry.register("plugin2", AnotherPlugin)
        
        values = list(registry.values())
        assert DummyPlugin in values
        assert AnotherPlugin in values


class TestConvenienceFunctions:
    """Test the convenience registration functions"""
    
    def test_register_interface(self):
        """Test register_interface function"""
        register_interface("test_interface", DummyPlugin)
        
        assert interface_plugin_registry.has_plugin("test_interface")
        assert interface_plugin_registry.get("test_interface") == DummyPlugin
        
        # Cleanup
        interface_plugin_registry.unregister("test_interface")
    
    def test_register_transformer(self):
        """Test register_transformer function"""
        register_transformer("test_transformer", DummyPlugin)
        
        assert transformer_plugin_registry.has_plugin("test_transformer")
        assert transformer_plugin_registry.get("test_transformer") == DummyPlugin
        
        # Cleanup
        transformer_plugin_registry.unregister("test_transformer")
    
    def test_register_model_getter(self):
        """Test register_model_getter function"""
        register_model_getter("test_getter", DummyPlugin)
        
        assert model_getter_plugin_registry.has_plugin("test_getter")
        assert model_getter_plugin_registry.get("test_getter") == DummyPlugin
        
        # Cleanup
        model_getter_plugin_registry.unregister("test_getter")


class TestPluginDiscovery:
    """Test plugin discovery via entry points"""
    
    def test_discover_plugins(self):
        """Test that discover_plugins can be called without errors"""
        registry = PluginRegistry("poly_lithic.interfaces")
        
        # Should not raise any errors
        registry.discover_plugins()
        
        # Multiple calls should be safe (idempotent)
        registry.discover_plugins()
        assert registry._loaded is True
    
    def test_global_registries(self):
        """Test that global registries exist"""
        # These should be instantiated
        assert interface_plugin_registry is not None
        assert transformer_plugin_registry is not None
        assert model_getter_plugin_registry is not None
        
        # They should have correct entry point groups
        assert interface_plugin_registry.entry_point_group == "poly_lithic.interfaces"
        assert transformer_plugin_registry.entry_point_group == "poly_lithic.transformers"
        assert model_getter_plugin_registry.entry_point_group == "poly_lithic.model_getters"
        

