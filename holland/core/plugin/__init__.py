"""
holland.core.plugin
~~~~~~~~~~~~~~~~~~~

Holland Plugin API

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

from holland.core.plugin.interface import BasePlugin, ConfigurablePlugin
from holland.core.plugin.error import PluginError
from . import loader

#: global plugin registyr - used by various builtin plugin
#: classes in holland.core
plugin_registry = loader.RegistryPluginLoader()

#: The default PluginLoader.  This defaults to an instance of
#: ``ChainedPluginLoader`` which looks up plugins from the
#: global holland.core plugin registry and then tries to lookup
#: from setuptools' entrypoints
default_plugin_loader = loader.ChainedPluginLoader(
        plugin_registry,
        loader.EntrypointPluginLoader()
)

#: Convenience method to iterate over a plugin group on the default
#: plugin loader
iterate_plugins = default_plugin_loader.iterate

#: Convenience method to load a plugin via the default plugin loader 
load_plugin = default_plugin_loader.load

__all__ = [
    'BasePlugin',
    'ConfigurablePlugin',
    'PluginError',
    'plugin_registry',
    'iterate_plugins',
    'load_plugin',
]
