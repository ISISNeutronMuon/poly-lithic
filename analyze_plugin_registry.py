"""
Analyze how the plugin registry discovers and loads plugins.
"""

import sys
import traceback

print("=" * 80)
print("ANALYZING PLUGIN REGISTRY")
print("=" * 80)

# First, check if we can import the registry modules
print("\n1️⃣  Importing plugin registry...")
try:
    from poly_lithic.src.utils.plugin_registry import (
        PluginRegistry,
        interface_plugin_registry,
        transformer_plugin_registry,
        model_getter_plugin_registry,
    )
    print("   ✅ Plugin registry imported")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    traceback.print_exc()
    sys.exit(1)

# Check the registries
print("\n2️⃣  Checking registry instances...")
print(f"   Interface registry: {interface_plugin_registry}")
print(f"   Transformer registry: {transformer_plugin_registry}")
print(f"   Model getter registry: {model_getter_plugin_registry}")

# Try to discover plugins
print("\n3️⃣  Discovering plugins...")
try:
    interface_plugin_registry.discover_plugins()
    print(f"   ✅ Interface plugins discovered: {interface_plugin_registry.list_plugins()}")
except Exception as e:
    print(f"   ❌ Interface discovery failed: {e}")
    traceback.print_exc()

try:
    transformer_plugin_registry.discover_plugins()
    print(f"   ✅ Transformer plugins discovered: {transformer_plugin_registry.list_plugins()}")
except Exception as e:
    print(f"   ❌ Transformer discovery failed: {e}")
    traceback.print_exc()

try:
    model_getter_plugin_registry.discover_plugins()
    print(f"   ✅ Model getter plugins discovered: {model_getter_plugin_registry.list_plugins()}")
except Exception as e:
    print(f"   ❌ Model getter discovery failed: {e}")
    traceback.print_exc()

# Try to load each test_plugin entry point
print("\n4️⃣  Attempting to load test_plugin entry points...")
from importlib.metadata import entry_points

for group_name in ['poly_lithic.interfaces', 'poly_lithic.transformers', 'poly_lithic.model_getters']:
    print(f"\n   Group: {group_name}")
    eps = entry_points(group=group_name)
    for ep in eps:
        if 'test_plugin' in ep.name:
            print(f"      Entry point: {ep.name}")
            print(f"         Value: {ep.value}")
            try:
                plugin_class = ep.load()
                print(f"         ✅ Loaded: {plugin_class}")
            except Exception as e:
                print(f"         ❌ Failed to load: {e}")
                traceback.print_exc()

print("\n" + "=" * 80)