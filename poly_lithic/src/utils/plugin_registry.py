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
from typing import Any
from importlib.metadata import entry_points
import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for dynamically discovered plugins via entry points."""

    def __init__(self, group_name: str):
        self.group_name = group_name
        self.entry_point_group = group_name
        self._plugins = {}
        self._entry_points = {}
        self._discovered = False
        self._loaded = {}

    def discover_plugins(self):
        if self._discovered:
            return

        discovered = entry_points(group=self.group_name)
        for ep in discovered:
            self._entry_points[ep.name] = ep
            self._loaded[ep.name] = False
            logger.debug(f"Discovered plugin: {ep.name}")
        
        self._discovered = True

    def register(self, name: str, plugin_class):
        self._plugins[name] = plugin_class
        logger.info(f"Registered plugin: {name}")

    def has_plugin(self, name: str) -> bool:
        if not self._discovered:
            self.discover_plugins()
        # print(self._loaded)
        # print(self._plugins)
        # print(self._entry_points)
        return name in self._plugins or name in self._entry_points

    def list_plugins(self):
        if not self._discovered:
            self.discover_plugins()
        return list(set(self._plugins.keys()) | set(self._entry_points.keys()))

    def unregister(self, name: str):
        if name in self._plugins:
            del self._plugins[name]
        if name in self._entry_points:
            del self._entry_points[name]
        if name in self._loaded:
            del self._loaded[name]
        logger.info(f"Unregistered plugin: {name}")

    def get(self, name: str):
        if name in self._plugins:
            return self._plugins[name]
        
        if not self._discovered:
            self.discover_plugins()
        
        if name in self._entry_points:
            try:
                plugin_class = self._entry_points[name].load()
                self._plugins[name] = plugin_class
                self._loaded[name] = True
                logger.debug(f"Loaded plugin: {name}")
                return plugin_class
            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}")
                raise
        
        raise KeyError(f"Plugin '{name}' not found")

    def __getitem__(self, name: str):
        return self.get(name)

    def __contains__(self, name: str) -> bool:
        return self.has_plugin(name)

    def __iter__(self):
        if not self._discovered:
            self.discover_plugins()
        return iter(set(self._plugins.keys()) | set(self._entry_points.keys()))

    def __len__(self) -> int:
        if not self._discovered:
            self.discover_plugins()
        return len(set(self._plugins.keys()) | set(self._entry_points.keys()))

    def keys(self):
        if not self._discovered:
            self.discover_plugins()
        return set(self._plugins.keys()) | set(self._entry_points.keys())

    def values(self):
        if not self._discovered:
            self.discover_plugins()
        for name in list(self._entry_points.keys()):
            if name not in self._plugins:
                try:
                    self.get(name)
                except Exception as e:
                    logger.warning(f"Could not load plugin {name}: {e}")
        return self._plugins.values()

    def items(self):
        if not self._discovered:
            self.discover_plugins()
        
        for name in self:
            try:
                yield name, self.get(name)
            except Exception as e:
                logger.warning(f"Could not load plugin {name}: {e}")

    def get_registered_plugins(self):
        if not self._discovered:
            self.discover_plugins()
        
        for name in list(self._entry_points.keys()):
            if name not in self._plugins:
                try:
                    self.get(name)
                except Exception as e:
                    logger.warning(f"Could not load plugin {name}: {e}")
        
        return dict(self._plugins)

    def clear(self):
        self._plugins.clear()
        self._entry_points.clear()
        self._loaded.clear()
        self._discovered = False


interface_plugin_registry = PluginRegistry("poly_lithic.interfaces")
transformer_plugin_registry = PluginRegistry("poly_lithic.transformers")
model_getter_plugin_registry = PluginRegistry("poly_lithic.model_getters")


def register_interface(name: str, interface_class: Any):
    interface_plugin_registry.register(name, interface_class)


def register_transformer(name: str, transformer_class: Any):
    transformer_plugin_registry.register(name, transformer_class)


def register_model_getter(name: str, model_getter_class: Any):
    model_getter_plugin_registry.register(name, model_getter_class)
