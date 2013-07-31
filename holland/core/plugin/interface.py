"""
holland.core.plugin.interface
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base plugin classes for Holland

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

class BasePlugin(object):
    """The base Plugin class that all Holland plugins
    derive from.

    Plugins are always instantiated with a name of the
    plugin they were registered under. This will be a
    name like 'mysqldump' or 'mysql-lvm'.

    Plugins should override the plugin_info() method
    and provide a dict with the following attributes:

      * name          - canonical name of this plugin
      * aliases       - iterable of alternative names for this plugin
      * namespace     - plugin namespace this plugin is for (e.g. holland.backup)
      * author        - plugin author's name
      * summary       - one-line (<80 char) short description of this plugin
      * description   - multi-line text blurb describing this plugin
      * version       - the version of this plugin (e.g. '0.1a1')
      * api_version   - the version of the holland api this plugin is
                        designed to work with (e.g. '1.1')
    """
    #: name of this plugin
    name = None

    #: namespace this plugin is registered under - a simple string
    namespace = None

    #: aliases for this plugin
    aliases = ()

    #: author of this plugin
    author = None

    #: single-line summary description of this plugin
    summary = None
    
    #: multi-line description of this plugin
    description = None

    #: version of this plugin
    version = '0.0.0'

    #: holland version this plugin is targetted for
    # This is used for api compatibility checking
    api_version = '1.1.0'

    def __init__(self, name):
        self.name = name

    def plugin_info(self):
        """Provide information about this plugin

        :returns: dict of plugin metadata attributes
        """
        return dict(
            name=self.name,
            author=self.author,
            summary=self.summary,
            description=self.description,
            version=self.version,
            api_version=self.api_version
        )

class ConfigurablePlugin(BasePlugin):
    """Base plugin class used by plugins that accept a config

    ConfigurablePlugins should provide two methods:
        * ``configspec()`` - Returns an instance of
          ``holland.core.config.Configspec`` describing the config that
          this plugin accepts
        * ``configure(config)`` - called by holland to configure this
          plugin with a config

    All configs are a subclass of ``holland.core.config.Config`` and behave as
    normal python dicts with additional methods documented in the config
    subpackage
    """
    config = None

    def configspec(self):
        """Provide a configspec that this plugin expects

        :returns: instance of holland.core.config.Configspec
        """
        return self.str_to_configspec("")

    @staticmethod
    def str_to_configspec(value):
        """Convert a string value to a Configspec object"""
        from holland.core.config import Configspec
        return Configspec.from_string(value)

    def configure(self, config):
        """Configure this plugin with the given dict-like object

        The default behavior just sets the ``config`` attribute on
        this plugin instance.
        """
        self.config = config
