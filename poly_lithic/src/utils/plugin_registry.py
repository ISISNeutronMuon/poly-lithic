"""
Plugin Registry System for Poly-Lithic

This module provides a plugin registration system that allows external packages
to register their own interfaces, transformers, and model getters through entry points.

External packages can register plugins by adding entry points in their pyproject.toml:

[project.entry-points."poly_lithic.interfaces"]
my_custom_interface = "my_package.interfaces:MyCustomInterface"

[project.entry-points."poly_lithic.transformers"]
my_transformer = "my_package.transformers:MyTransformer"

[project.entry-points."poly_lithic.model_getters"]
my_model_getter = "my_package.models:MyModelGetter"
"""

import importlib
import importlib.metadata
from typing import Dict, Any, Callable
from poly_lithic.src.logging_utils import get_logger

logger = get_logger()


class PluginRegistry:
    """Registry for dynamically discovered plugins via entry points."""

    def __init__(self, entry_point_group: str):
        """
        Initialize the plugin registry for a specific entry point group.

        Args:
            entry_point_group: The entry point group name (e.g., 'poly_lithic.interfaces')
        """
        self.entry_point_group = entry_point_group
        self._plugins: Dict[str, Any] = {}
        self._loaded = False

    def discover_plugins(self):
        """
        Discover and load all plugins registered via entry points.
        """
        if self._loaded:
            return

        try:
            # Use importlib.metadata to discover entry points (Python 3.10+)
            entry_points = importlib.metadata.entry_points()
            
            # Handle both new and old entry point API
            if hasattr(entry_points, 'select'):
                # Python 3.10+
                group_entries = entry_points.select(group=self.entry_point_group)
            else:
                # Python 3.9 fallback
                group_entries = entry_points.get(self.entry_point_group, [])

            for entry_point in group_entries:
                try:
                    plugin_class = entry_point.load()
                    # Only register if not already manually registered
                    if entry_point.name not in self._plugins:
                        self._plugins[entry_point.name] = plugin_class
                        logger.info(
                            f"Loaded plugin '{entry_point.name}' from {entry_point.value} "
                            f"for group '{self.entry_point_group}'"
                        )
                    else:
                        logger.info(
                            f"Skipping plugin '{entry_point.name}' from {entry_point.value} "
                            f"- already manually registered in '{self.entry_point_group}'"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to load plugin '{entry_point.name}' "
                        f"from group '{self.entry_point_group}': {e}"
                    )

        except Exception as e:
            logger.error(f"Error discovering plugins for '{self.entry_point_group}': {e}")

        self._loaded = True

    def register(self, name: str, plugin_class: Any):
        """
        Manually register a plugin.

        Args:
            name: The name/key for the plugin
            plugin_class: The plugin class to register
        """
        if name in self._plugins:
            logger.warning(
                f"Plugin '{name}' already registered in '{self.entry_point_group}'. "
                f"Overwriting."
            )
        self._plugins[name] = plugin_class
        logger.info(f"Manually registered plugin '{name}' in '{self.entry_point_group}'")

    def unregister(self, name: str):
        """
        Unregister a plugin.

        Args:
            name: The name/key of the plugin to unregister
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.info(f"Unregistered plugin '{name}' from '{self.entry_point_group}'")
        else:
            logger.warning(
                f"Cannot unregister '{name}': not found in '{self.entry_point_group}'"
            )

    def get(self, name: str) -> Any:
        """
        Get a plugin by name.

        Args:
            name: The name/key of the plugin

        Returns:
            The plugin class

        Raises:
            KeyError: If the plugin is not found
        """
        if not self._loaded:
            self.discover_plugins()

        if name not in self._plugins:
            raise KeyError(
                f"Plugin '{name}' not found in '{self.entry_point_group}'. "
                f"Available plugins: {list(self._plugins.keys())}"
            )
        return self._plugins[name]

    def list_plugins(self) -> list[str]:
        """
        List all registered plugin names.

        Returns:
            List of plugin names
        """
        if not self._loaded:
            self.discover_plugins()
        return list(self._plugins.keys())

    def has_plugin(self, name: str) -> bool:
        """
        Check if a plugin is registered.

        Args:
            name: The name/key of the plugin

        Returns:
            True if the plugin exists, False otherwise
        """
        if not self._loaded:
            self.discover_plugins()
        return name in self._plugins

    def __contains__(self, name: str) -> bool:
        """Support 'in' operator."""
        return self.has_plugin(name)

    def __getitem__(self, name: str) -> Any:
        """Support dictionary-like access."""
        return self.get(name)

    def __iter__(self):
        """Support iteration over plugin names."""
        if not self._loaded:
            self.discover_plugins()
        return iter(self._plugins)

    def items(self):
        """Support dictionary-like items() method."""
        if not self._loaded:
            self.discover_plugins()
        return self._plugins.items()

    def keys(self):
        """Support dictionary-like keys() method."""
        return self.list_plugins()

    def values(self):
        """Support dictionary-like values() method."""
        if not self._loaded:
            self.discover_plugins()
        return self._plugins.values()


# Global plugin registries
interface_plugin_registry = PluginRegistry("poly_lithic.interfaces")
transformer_plugin_registry = PluginRegistry("poly_lithic.transformers")
model_getter_plugin_registry = PluginRegistry("poly_lithic.model_getters")


# Convenience functions for manual registration
def register_interface(name: str, interface_class: Any):
    """
    Manually register an interface plugin.

    Args:
        name: The name/key for the interface
        interface_class: The interface class to register
    """
    interface_plugin_registry.register(name, interface_class)


def register_transformer(name: str, transformer_class: Any):
    """
    Manually register a transformer plugin.

    Args:
        name: The name/key for the transformer
        transformer_class: The transformer class to register
    """
    transformer_plugin_registry.register(name, transformer_class)


def register_model_getter(name: str, model_getter_class: Any):
    """
    Manually register a model getter plugin.

    Args:
        name: The name/key for the model getter
        model_getter_class: The model getter class to register
    """
    model_getter_plugin_registry.register(name, model_getter_class)
