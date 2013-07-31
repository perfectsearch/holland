"""
holland.core.backup.plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~

Backup plugin interface

"""
import pkgutil
import logging
from holland.core.plugin import (ConfigurablePlugin, plugin_registry,
                                 load_plugin)
from holland.core.backup.exc import BackupError
LOG = logging.getLogger(__name__)

def load_backup_strategy(name):
    """Load a backup strategy plugin"""
    return load_plugin('holland.backup', name)
load_backup_plugin = load_backup_strategy

def backup_plugin_from_config(config):
    """Load a backup plugin from a config instance"""
    name = config['holland:backup']['backup-plugin']
    return load_backup_plugin(name)

class BackupStrategy(ConfigurablePlugin):
    """Interface that all holland backup plugins should implement

    This base class provides a useful set of default behaviors.  In many cases
    a real backup plugin implementation only needs to override backup() and
    configspec() (if the plugin accepts additional configuration parameters)

    """

    namespace = 'holland.backup'
    name = ''

    #: BackupPlugin has a reference to the base BackupError class to aid in
    #: error handling
    BackupError = BackupError

    #: attribute defined by bind() - a string path pointing to the root
    #: directory where this plugin stores its backups
    backup_directory = None

    #: `BackupContext` instance used for this plugin.  set by bind()
    context = None

    def bind(self, context):
        """Bind the given BackupContext to this plugin instance

        The BackupContext provides access to the `Backup` model,
        the session database and the `Store` instance.
        """
        self.context = context
        self.config = context.config
        self.backup_directory = context.backup.backup_directory

    def setup(self):
        """Perform any setup this plugin requires"""

    def estimate(self):
        """Estimate the size of the final backup this plugin will produce"""
        return 0

    def backup(self):
        """Perform the backup operation this plugin implements.

        Backup files should be stored under ``self.backup_directory``

        If a backup fails, a ``BackupError`` instance should be raised

        :raises: BackupError
        """

    def dryrun(self):
        """Perform a dryrun of the backup process performing as many checks
        as are feasible without actually running the backup routine
        """

    def cleanup(self):
        """Perform any cleanup this plugin requires"""

    def release(self):
        """Release any temporary resources used by a previous run of this
        backup plugin
        """
        LOG.info("Releasing plugin resources held by %s", self.backup_directory)

    def fail(self, reason, orig_exc=None):
        """Fail this backup by raising a BackupError"""
        raise BackupError(reason, orig_exc)

    @classmethod
    def base_configspec(cls):
        """Configspec for the [holland:backup] section"""
        pkg = BackupPlugin.__module__.rpartition('.')[0]
        configspec = pkgutil.get_data(pkg, 'holland-backup.configspec')
        return cls.str_to_configspec(configspec.decode('utf8'))

    def configspec(self):
        """Provide a `Configspec` detailing the valid configuration options
        this plugin supports
        """
        plugin_pkg = self.__class__.__module__.rpartition('.')[0]
        data = pkgutil.get_data(plugin_pkg, self.name + '.configspec')
        data = data.decode('utf8')
        configspec = self.str_to_configspec(data)
        configspec.meld(self.base_configspec())
        return configspec

BackupPlugin = BackupStrategy


@plugin_registry.register
class NoopBackupPlugin(BackupPlugin):
    """Backup method that does nothing at all.

    This is a useful stub to disable backups or for testing hooks without
    needing a heavyweight backup method implemented.
    """
    name = 'noop'
    summary = 'a dummy backup method that does not backup any data'
    description = summary

    def configspec(self):
        """Provides the noop configspec"""
        return self.base_configspec()
