# SPDX-FileCopyrightText: Copyright 2025 UK Research and Innovation, Science and Technology Facilities Council, ISIS
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Unit tests for plugin_registry module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from poly_lithic.src.utils.plugin_registry import PluginRegistry


class TestPluginRegistryHasPlugin:
    """Test suite for the has_plugin method."""
    
    @pytest.fixture
    def registry(self):
        """Create a fresh registry instance for each test."""
        return PluginRegistry("test.group")
    
    def test_has_plugin_not_discovered_triggers_discovery(self, registry):
        """Test that has_plugin triggers discovery if not yet discovered."""
        with patch.object(registry, 'discover_plugins') as mock_discover:
            registry.has_plugin('test_plugin')
            mock_discover.assert_called_once()
    
    def test_has_plugin_already_discovered_no_rediscovery(self, registry):
        """Test that has_plugin doesn't trigger discovery if already discovered."""
        registry._discovered = True
        
        with patch.object(registry, 'discover_plugins') as mock_discover:
            registry.has_plugin('test_plugin')
            mock_discover.assert_not_called()
    
    def test_has_plugin_in_plugins_dict(self, registry):
        """Test has_plugin returns True when plugin is in _plugins dict."""
        registry._discovered = True
        
        mock_class = Mock()
        registry._plugins['test_plugin'] = mock_class
        
        assert registry.has_plugin('test_plugin') is True
    
    def test_has_plugin_in_entry_points(self, registry):
        """Test has_plugin returns True when plugin is in _entry_points."""
        registry._discovered = True
        
        mock_entry_point = Mock()
        registry._entry_points['test_plugin'] = mock_entry_point
        
        assert registry.has_plugin('test_plugin') is True
    
    def test_has_plugin_in_both_locations(self, registry):
        """Test has_plugin returns True when plugin is in both _plugins and _entry_points."""
        registry._discovered = True
        
        mock_class = Mock()
        mock_entry_point = Mock()
        registry._plugins['test_plugin'] = mock_class
        registry._entry_points['test_plugin'] = mock_entry_point
        
        assert registry.has_plugin('test_plugin') is True
    
    def test_has_plugin_not_found(self, registry):
        """Test has_plugin returns False when plugin is not found."""
        registry._discovered = True
        
        assert registry.has_plugin('nonexistent_plugin') is False
    
    def test_has_plugin_empty_registry(self, registry):
        """Test has_plugin returns False when registry is empty."""
        registry._discovered = True
        
        assert registry.has_plugin('any_plugin') is False
    
    def test_has_plugin_case_sensitive(self, registry):
        """Test has_plugin is case-sensitive."""
        registry._discovered = True
        
        mock_class = Mock()
        registry._plugins['TestPlugin'] = mock_class
        
        assert registry.has_plugin('TestPlugin') is True
        assert registry.has_plugin('testplugin') is False
        assert registry.has_plugin('TESTPLUGIN') is False
    
    def test_has_plugin_with_special_characters(self, registry):
        """Test has_plugin works with plugin names containing special characters."""
        registry._discovered = True
        
        mock_class = Mock()
        registry._plugins['test-plugin_v2.0'] = mock_class
        
        assert registry.has_plugin('test-plugin_v2.0') is True
    
    def test_has_plugin_empty_string(self, registry):
        """Test has_plugin with empty string."""
        registry._discovered = True
        
        assert registry.has_plugin('') is False
    
    def test_has_plugin_multiple_plugins(self, registry):
        """Test has_plugin with multiple plugins in registry."""
        registry._discovered = True
        
        registry._plugins['plugin1'] = Mock()
        registry._plugins['plugin2'] = Mock()
        registry._entry_points['plugin3'] = Mock()
        
        assert registry.has_plugin('plugin1') is True
        assert registry.has_plugin('plugin2') is True
        assert registry.has_plugin('plugin3') is True
        assert registry.has_plugin('plugin4') is False
    
    @patch('poly_lithic.src.utils.plugin_registry.entry_points')
    def test_has_plugin_with_real_discovery(self, mock_entry_points):
        """Test has_plugin with actual discovery process."""
        mock_ep = Mock()
        mock_ep.name = 'discovered_plugin'
        mock_entry_points.return_value = [mock_ep]
        
        registry = PluginRegistry("test.group")
        
        assert registry.has_plugin('discovered_plugin') is True
        assert registry._discovered is True
        mock_entry_points.assert_called_once_with(group="test.group")
    
    def test_has_plugin_after_register(self, registry):
        """Test has_plugin returns True after registering a plugin."""
        registry._discovered = True
        
        mock_class = Mock()
        registry.register('new_plugin', mock_class)
        
        assert registry.has_plugin('new_plugin') is True
    
    def test_has_plugin_after_unregister(self, registry):
        """Test has_plugin returns False after unregistering a plugin."""
        registry._discovered = True
        
        mock_class = Mock()
        registry._plugins['temp_plugin'] = mock_class
        
        assert registry.has_plugin('temp_plugin') is True
        
        registry.unregister('temp_plugin')
        
        assert registry.has_plugin('temp_plugin') is False
    
    def test_has_plugin_idempotent(self, registry):
        """Test has_plugin can be called multiple times with same result."""
        registry._discovered = True
        
        mock_class = Mock()
        registry._plugins['test_plugin'] = mock_class
        
        assert registry.has_plugin('test_plugin') is True
        assert registry.has_plugin('test_plugin') is True
        assert registry.has_plugin('test_plugin') is True