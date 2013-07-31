import logging
from holland.core.plugin import BasePlugin
from holland.core.plugin.loader import RegistryPluginLoader

LOG = logging.getLogger(__name__)

estimation_registry = RegistryPluginLoader()

def load_estimation_plugin(name):
    return estimation_registry.load('holland.backup.estimation', name)

class EstimationMethod(BasePlugin):
    """Estimation plugin interface"""

    namespace = 'holland.backup.estimation'
    name = ''

    #: BackupContext this plugin runs in
    #: set by the bind() method
    context = None

    def bind(self, context):
        self.context = context

    def estimate(self, args=None):
        """Estimate the size of a backup for the provided context"""
        raise NotImplementedError()


@estimation_registry.register
class PluginEstimationMethod(EstimationMethod):
    """Estimate backup size by asking the backup plugin"""

    name = 'plugin'

    def estimate(self, _):
        backup_plugin = self.context.plugin
        return backup_plugin.estimate()


@estimation_registry.register
class DirectoryEstimationMethod(EstimationMethod):
    """Estimate backup size by the size of a directory"""

    name = 'directory'

    def estimate(self, path):
        from holland.core.util import directory_size
        return directory_size(path)


@estimation_registry.register
class ConstantEstimationMethod(EstimationMethod):
    """Estimate a backup size by always returning a constant"""

    name = 'const'

    def estimate(self, value):
        from holland.core.util import parse_bytes
        return parse_bytes(value)


@estimation_registry.register
class LastBackupEstimationMethod(EstimationMethod):
    """Estimate backup size by assuming it was the same as the last backup size"""

    name = 'last-backup'

    def estimate(self, unused):
        controller = self.context.controller
        last_backup = controller.catalog.previous_backup(self.context.backup)
        if not last_backup:
            method = PluginEstimationMethod('last-backup')
            method.bind(self.context)
            return method.estimate(None)
            raise EstimationError("No previous backup to assume")
        LOG.info("last backup (%s) appeared to have size: %r",
                last_backup.backup_directory,
                last_backup.real_size)
        return last_backup.real_size
