"""
holland.core.plugin
~~~~~~~~~~~~~~~~~~~

Holland Plugin API

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

from holland.core.plugin.interface import BasePlugin, ConfigurablePlugin
from holland.core.plugin.loader import AbstractPluginLoader, \
                                        EntrypointPluginLoader
from holland.core.plugin.error import PluginError

#: The default PluginLoader.  This defaults to an instance of
#: ``EntrypointPluginLoader`` which looks up plugins based on
#: setuptools entrypoints
default_pluginmgr = EntrypointPluginLoader()

#: Convenience method to iterate over a plugin group on the default
#: plugin manager
iterate_plugins = default_pluginmgr.iterate

#: Convenience method to load a plugin via the default plugin manager
load_plugin = default_pluginmgr.load

__all__ = [
    'BasePlugin',
    'ConfigurablePlugin',
    'AbstractPluginLoader',
    'EntrypointPluginLoader',
    'PluginError',
    'default_pluginmgr',
    'iterate_plugins',
    'load_plugin',
]
