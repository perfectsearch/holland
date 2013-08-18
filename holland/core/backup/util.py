## util.py
import logging
from datetime import datetime
from collections import namedtuple
from ..config import Config
from .plugin import BackupPlugin, load_backup_plugin
from .hooks import HookExecutor
from .exc import BackupError

LOG = logging.getLogger(__name__)

def validate(config):
    """Validate a backup config and return the configured backup plugin instance"""
    basecfg = config.get('holland:backup')
    if not basecfg:
        raise BackupError("Missing [holland:backup] section in %s" % config.path)
    BackupPlugin.base_configspec()['holland:backup'].validate(basecfg)

    if not basecfg.backup_plugin:
        raise BackupError("No backup-plugin specified in [holland:backup] in %s" % config.path)

    plugin = load_backup_plugin(basecfg.backup_plugin)
    plugin.configspec().validate(config)
    return plugin, config

BackupContext = namedtuple('BackupContext',
                           'backup config plugin controller node')

def execute_backup(context):
    """Execute a backup lifecycle

    :param context: ``BackupContext`` instance to execute
    """
    backup = context.backup
    job = backup.job
    plugin = context.plugin
    plugin.bind(context)
    with HookExecutor(context) as executor:
        executor.event('initialize')
        plugin.setup()
        try:
            executor.event('before-backup')
            try:
                if job.is_dryrun:
                    plugin.dryrun()
                else:
                    plugin.backup()
            finally:
                backup.stop_time = datetime.now()
        except BaseException as exc:
            LOG.debug("Failed backup.  Stacktrace:", exc_info=True)
            backup.status = 'failed'
            backup.message = unicode(exc)
            executor.event('failed-backup')
            raise
        else:
            backup.status = 'completed'
            executor.event('completed-backup')
        finally:
            executor.event('after-backup')
            plugin.cleanup()
