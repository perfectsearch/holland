"""
holland.core.plugin.loader
~~~~~~~~~~~~~~~~~~~~~~~~~~

Plugin manager API responsible for loading plugins

:copyright: 2008-2011 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import pkgutil
import logging
import pkg_resources
from functools import wraps
from holland.core.util.datastructures import OrderedDict
from holland.core.plugin.util import import_module
from holland.core.plugin.error import PluginError, PluginLoadError, \
                                      PluginNotFoundError
from holland.core.plugin.interface import BasePlugin

LOG = logging.getLogger(__name__)

class AbstractPluginLoader(object):
    """PluginLoader interface

    All plugin managers should implement two methods:
        * load(namespace, name) - load a plugin given a namespace and a plugin name
        * iterate(namespace) - iterate over all plugins in a given namespace

    Plugin managers are free to interpret ``namespace`` and ``name`` according to
    their own implementations.  ``EntrypointPluginLoader`` loads these per the
    pkg_resources.iter_entry_points API but other managers may be added in the
    future that will work off simpler __import__ system and treat ``namespace`` as
    a package name and ``name`` as an attribute defined in the package.
    """

    def load(self, namespace, name):
        """Load a plugin for the given name

        The default behaviors raises ``PluginNotFoundError`` exception and
        should be overriden by real implementation in a subclass
        """
        raise NotImplementedError()

    def iterate(self, namespace):
        """Iterate over plugins for the given name

        The default behavior returns an empty list.
        """
        raise NotImplementedError()

class RegistryPluginLoader(AbstractPluginLoader):
    """Plugin manager that loads plugins from an internal registry

    :attr registry: dict of dicts mapping (namespace, name) tuples to
                    plugin classes
    """
    def __init__(self):
        self.registry = OrderedDict()

    def register(self, plugincls):
        """Class decorator to register a class with a DictPluginLoader instance

        @registry.register
        class MyPlugin:
            name = 'myplugin'
            namespace = 'awesome-plugins'
            aliases = ['other_name']
            ...


        >>> register.load_plugin(namespace='awesome-plugins'', 'myplugin')
        MyPlugin()

        ``plugincls`` must have three attributes:
        name - string name for the plugin
        namespace - plugin namespace this plugin works under
        aliases - iterable of string names ``plugincls`` is also loadable by

        :attr plugincls:  Plugin class to register with this registry

        """
        name = getattr(plugincls, 'name')
        namespace = getattr(plugincls, 'namespace')
        aliases = getattr(plugincls, 'aliases', ())
        namespace_dict = self.registry.setdefault(namespace, OrderedDict())
        for name in (name,) + tuple(aliases):
            if name in namespace_dict:
                LOG.debug("Class %r already registered under %r.%r",
                          plugincls, namespace, name)
            namespace_dict[name] = plugincls
        return plugincls

    def load(self, namespace, name):
        """Load a plugin from this loader's registry

        :param namespace: namespace to load from
        :param name: name of a plugin to load
        :returns: BasePlugin instance
        :raises: PluginError if a plugin could not be loaded
        """

        try:
            plugin_namespace = self.registry[namespace]
        except KeyError:
            raise PluginNotFoundError(namespace, name=None)
        try:
            return plugin_namespace[name]
        except KeyError:
            raise PluginNotFoundError(namespace, name)

    def iterate(self, namespace):
        """Iterate over plugins in this registry's namespace

        :param namespace: namespace to iterate over
        :yields: BasePlugin instances
        """
        namespace_dict = self.registry.get(namespace, OrderedDict())
        for name, plugin_cls in namespace_dict.iteritems():
            yield plugin_cls(name)

class ImportPluginLoader(AbstractPluginLoader):
    """Plugin manager that uses __import__ to load a plugin

    This is an example of a PluginLoader that loads modules through a simple
    __import__() protocol and iterates over available plugins in a package via
    python's ``pkgutil`` module
    """

    def load(self, namespace, name):
        """Load a plugin from a module named by ``namespace``.``name`` looks for an
        attribute on that module called ``name``.

        For example mysqldump might be a module holland.backup.mysqldump which
        defines a ``mysqldump`` attribute pointing to a ``BasePlugin``
        subclass::
            holland/backup/mysqldump.py:
                mysqldump = MyMySQLDumpPlugin

        This is designed after the pattern used by sqlalchemy's dialect plugin
        system.

        :raises: ``PluginNotFoundError`` if no plugin is found on the
                 module defined by namespace.name
        :returns: instance of BasePlugin if found
        """
        module = import_module('.'.join(namespace, name))
        try:
            return module.getattr(name, module)
        except AttributeError:
            raise PluginNotFoundError("No such plugin %s.%s" % (namespace, name))

    def iterate(self, namespace):
        """Iterate over plugins in the package named by ``namespace``

        This implementation uses pkgutil to walk the packages under the pkg
        namespace named by the ``namespace`` argument and yields any subclasses of
        ``BasePlugin`` found in that package.
        """
        module = import_module(namespace)
        for _, name in pkgutil.walk_packages(module.__path__):
            submodule = import_module(namespace + '.' + name)
            plugin = getattr(submodule, name)
            if isinstance(plugin, BasePlugin):
                yield plugin(name)

class EntrypointPluginLoader(AbstractPluginLoader):
    """Plugin manager that uses setuptools entrypoints"""

    def load(self, namespace, name):
        """Load a plugin via a setuptools entrypoint for the given name

        Name must be in the format namespace.name
        """
        # These typically give no information about what was going on froma
        # str(exc) alone:
        # DistributionNotFoundError - A requested distribution was not found
        # VersionConflict - An already-installed version conflicts with the
        #                   requested version
        # These are raised when an entrypoint has declared dependencies
        for plugin in pkg_resources.iter_entry_points(namespace, name):
            try:
                return plugin.load()(plugin.name)
            except (SystemExit, KeyboardInterrupt):
                raise
            except pkg_resources.DistributionNotFound, exc:
                raise EntrypointDependencyError(namespace, name,
                                                entrypoint=plugin,
                                                req=exc.args[0])
            except pkg_resources.VersionConflict, exc:
                raise EntrypointVersionConflictError(namespace, name,
                                                     entrypoint=plugin,
                                                     req=exc.args[1])
            except Exception, exc:
                LOG.exception("Exception when loading plugin")
                raise PluginLoadError(namespace, name, exc)
        raise PluginNotFoundError(namespace, name)

    def iterate(self, namespace):
        """Iterate over an entrypoint namespace and yield the loaded entrypoint
        object
        """
        LOG.debug("Iterating over namespace=%r", namespace)
        for plugin in pkg_resources.iter_entry_points(namespace):
            try:
                yield plugin.load()(plugin.name)
            except (SystemExit, KeyboardInterrupt):
                raise
            except:
                # skip broken plugins during iterate
                LOG.debug("Skipping broken plugin '%s'",
                          plugin.name, exc_info=True)

# specific to entrypoint plugins
class EntrypointDependencyError(PluginLoadError):
    """An entrypoint or its python egg distribution requires some dependency
    that could not be found by setuptools/pkg_resources

    :attr entrypoint:  entrypoint that causes this error
    :attr req: requirement that could not be found
    """

    def __init__(self, namespace, name, entrypoint, req):
        PluginError.__init__(self, namespace, name, None)
        self.entrypoint = entrypoint
        self.req = req

    def __str__(self):
        return "Could not find dependency '%s' for plugin %s in namespace %s" % \
               (self.req, self.name, self.namespace)

class EntrypointVersionConflictError(PluginLoadError):
    """Raises when multiple egg distributions provide the same requirement but
    have different versions.
    """

    def __init__(self, namespace, name, entrypoint, req):
        PluginError.__init__(self, namespace, name, None)
        self.entrypoint = entrypoint
        self.dist = entrypoint.dist
        self.req = req

    def __str__(self):
        return ("Version Conflict while loading plugin package. "
                "Requested %s Found %s" % (self.req, self.dist))

class ChainedPluginLoader(AbstractPluginLoader):
    """Chain multiple plugin loaders together

    This plugin loader is composed of one or more other concrete loaders
    and will delegate methods to each registered loader in order.

    :attr loaders: list of loader instances
    """

    def __init__(self, *loaders):
        self.loaders = loaders

    def load(self, namespace, name):
        for loader in self.loaders:
            try:
                return loader.load(namespace, name)
            except PluginLoadError, exc:
                continue
        raise PluginNotFoundError(namespace, name)

    def iterate(self, namespace):
        for loader in self.loaders:
            LOG.debug("Loading from loader=%r", loader)
            try:
                for plugin in loader.iterate(namespace):
                    LOG.debug("yielding plugin=%r", plugin)
                    yield plugin
            except PluginLoadError:
                continue
