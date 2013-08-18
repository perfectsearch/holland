import os
from os.path import join
import time
import logging
from holland.core.backup.exc import BackupError
from holland.core.config import Config
from holland.core.util import relpath, format_interval
from holland.core.util.pycompat import total_ordering
from holland.core.plugin.interface import BasePlugin
from holland.core.plugin.loader import RegistryPluginLoader

LOG = logging.getLogger(__name__)
hook_registry = RegistryPluginLoader()

class HookExecutor(object):
    def __init__(self, context):
        self.context = context
        self.hooks = []

    def event(self, name):
        # at the very least we should ensure this always returns a HollandError
        # subclass
        LOG.debug("Dispatching hook event '%s'", name)
        for obj in self.hooks:
            try:
                obj(name)
            except:
                LOG.debug("Hook %r failed on event %s", obj, name)
                raise

    def __enter__(self):
        hooks = hook_registry.iterate('holland.backup.hooks')
        self.hooks = sorted(list(hooks))
        for obj in self.hooks:
            obj.bind(self.context)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del self.hooks[:]


@total_ordering
class HookPlugin(BasePlugin):

    namespace = 'holland.backup.hooks'
    priority = 0
    context = None

    def bind(self, context):
        self.context = context
        self.config = context.config['holland:backup']

    def __call__(self, event):
        event = event.replace('-', '_')
        callee = getattr(self, event, None)
        if callee:
            callee()
        #else:
        #    LOG.debug("No method %s defined on hook %s", event, self)

    def __eq__(self, other):
        return (self.priority == other.priority and
                self.__class__ == other.__class__)

    def __lt__(self, other):
        return self.priority < other.priority

@hook_registry.register
class EstimationHook(HookPlugin):
    """Predict the size of the current backup"""
    name = 'estimation'
    priority = 50
    def before_backup(self):
        estimation_method = self.config['estimation-method']
        LOG.info("Using estimation method '%s'", estimation_method.name)
        from . import estimation
        plugin = estimation.load_estimation_plugin(estimation_method.name)
        plugin.bind(self.context)
        LOG.debug("Loaded estimation plugin: %r", plugin)
        start_time = time.time()
        estimated_bytes = plugin.estimate(estimation_method.arg)
        self.context.backup.estimated_size = estimated_bytes
        from holland.core.util import format_bytes, disk_usage
        LOG.info("Estimated backup size: %s", format_bytes(estimated_bytes))
        LOG.info("Estimation took %s",
                 format_interval(time.time() - start_time))

        adjust_by_percent = self.config.estimated_size_adjust_by_percent
        adj_estimated_bytes = estimated_bytes*adjust_by_percent

        if adj_estimated_bytes != estimated_bytes:
            LOG.info("Adjusted estimated size by %.2f%% to %s",
                      adjust_by_percent*100, 
                     format_bytes(adj_estimated_bytes))

        available_bytes = disk_usage(self.context.backup.backup_directory).free
        LOG.info("Available space on '%s': %s", 
                 self.context.backup.backup_directory,
                 format_bytes(available_bytes))

        if available_bytes < adj_estimated_bytes:
            LOG.info("Available space is less than estimated space for a backup. Aborting.")
            raise BackupError("Insufficient space for backup.  Required: %s Available: %s" %
                              (format_bytes(estimated_bytes),
                               format_bytes(available_bytes)))

    # update this on either failed backup or on a completed backup
    # but not both
    def update_backup_size(self):
        backup = self.context.backup
        from holland.core.util import format_bytes, directory_size
        if backup.real_size is None:
            from holland.core.util import directory_size
            try:
                backup.real_size = directory_size(backup.backup_directory)
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise # XXX: convert to holland error
                # backup-directory no longer exists
                backup.real_size = 0
            LOG.info("Final backup size: %s", format_bytes(backup.real_size))
        if backup.estimated_size:
            LOG.info("This backup was %.4f%% of estimated-size (%s)",
                     (float(backup.real_size) / backup.estimated_size)*100.0,
                     format_bytes(backup.estimated_size))
    failed_backup = update_backup_size
    completed_backup = update_backup_size

@hook_registry.register
class ChecksumHook(HookPlugin):
    """Checksum backup directory"""
    name = 'checksum'
    priority = 100
    def after_backup(self):
        if self.context.backup.job.is_dryrun:
            return
        import hashlib
        backup_directory = self.context.backup.backup_directory
        if self.config.checksum_algorithm == 'none':
            LOG.info("Checksums are disabled.")
            return
        if not os.path.exists(backup_directory):
            LOG.debug("Skipping checksums - '%s' no longer exists.", backup_directory)
            return
        checksum = hashlib.new(self.config['checksum-algorithm'])
        LOG.info("Generating checksums for '%s'", backup_directory)
        checksum_path = join(backup_directory, '.holland', 'checksums')
        anchor_time = time.time()
        with open(checksum_path, 'wb') as checksumf:
            print >>checksumf, "# %ssum" % self.config.checksum_algorithm
            for dirpath, dirnames, filenames in os.walk(backup_directory):
                for name in filenames:
                    hash = checksum.copy()
                    path = join(dirpath, name)
                    rpath = relpath(path, backup_directory)
                    # don't checksum symlinks
                    if os.path.islink(path):
                        continue
                    if not os.path.isfile(path):
                        continue
                    # don't checksum the checksum file
                    if path == checksum_path:
                        continue
                    LOG.debug("Checksumming '%s'",
                              relpath(path, backup_directory))
                    with open(path, 'rb') as srcf:
                        data = srcf.read(32768)
                        while data:
                            hash.update(data)
                            data = srcf.read(32768)
                    print >>checksumf, "%s  %s" % (hash.hexdigest(), rpath)
        LOG.info("All %s checksums calculated in %s",
                 self.config.checksum_algorithm,
                 format_interval(time.time() - anchor_time))

@hook_registry.register
class WriteStatusHook(HookPlugin):

    name = 'update-status'
    config = None

    def before_backup(self):
        backup = self.context.backup
        node = self.context.node
        self.config = Config()
        self.config['status'] = backup.status
        self.config['start-time'] = backup.start_time.isoformat()
        self.config['job-id'] = str(backup.job.id)
        self.config['backup-id'] = str(backup.id)
        with node.open(os.path.join('.holland', 'status'), 'wb') as fp:
            fp.write(str(self.config))

    def after_backup(self):
        backup = self.context.backup
        node = self.context.node
        # don't write out a status file if the backup driectory no longer
        # exists
        if not os.path.exists(node.path):
            return
        if backup.stop_time:
            self.config['stop-time'] = backup.stop_time.isoformat()
        self.config['status'] = backup.status
        with node.open(os.path.join('.holland', 'status'), 'wb') as fp:
            fp.write(str(self.config))

@hook_registry.register
class SaveConfigHook(HookPlugin):
    """Write out the active config to backup directory"""

    name = 'save-config'
    priority = 0

    saved_config = None

    def update_config(self):
        self.context.backup.config = self.context.config.text
        from tempfile import NamedTemporaryFile
        config = self.context.config
        backup_directory = self.context.backup.backup_directory
        if not os.path.exists(backup_directory):
            return
        backup_conf = join(backup_directory, '.holland', 'config')
        with NamedTemporaryFile(dir=join(backup_directory, '.holland'), delete=False) as f:
            config.write(f.name)
            LOG.debug(" Wrote config out to temporary file: %s", f.name)
            os.rename(f.name, backup_conf)
            LOG.debug(" Renamed %s to %s", f.name, backup_conf)
            LOG.info("Saved config %s", backup_conf)

    def before_backup(self):
        backup_directory = self.context.backup.backup_directory
        backup_conf = join(backup_directory, '.holland', 'config')
        os.symlink('.holland/config', join(backup_directory, 'backup.conf'))
        config = self.context.config
        self.saved_config = config.copy()
        self.update_config()

    def after_backup(self):
        config = str(self.context.config)
        saved_config = str(self.saved_config)
        if config != saved_config:
            self.update_config()


@hook_registry.register
class RemoveFailureHook(HookPlugin):
    """Remove a failed backup"""
    name = 'remove-failed-backup'
    priority = 100
    def failed_backup(self):
        backup_directory = self.context.backup.backup_directory
        LOG.info("Removing failed backup '%s'", backup_directory)
        import shutil
        shutil.rmtree(backup_directory)

    def after_backup(self):
        if self.context.backup.job.is_dryrun:
            LOG.info("Removing dry-run temporary files in '%s'", self.context.node.path)
            self.context.node.purge()

@hook_registry.register
class RotateBackupsHook(HookPlugin):
    """Rotate backups in a backupset"""

    name = 'rotate-backups'
    priority = 0

    def _purge(self, exclude=()):
        backup = self.context.backup
        name = backup.name
        spool_directory = self.context.controller.spool.path
        backupset_path = join(spool_directory, name)
        LOG.info("Rotating backups in '%s'", backupset_path)
        retention_count = self.config.retention_count
        from holland.core.backup.controller import PurgeOptions
        purge_options = PurgeOptions(retention_count, dry_run=False)
        self.context.controller.purge_set(name, purge_options, exclude)

    def before_backup(self):
        if self.context.backup.job.is_dryrun:
            return
        if self.config['purge-policy'] == 'before-backup':
            backup = self.context.backup
            self._purge(exclude=[backup.backup_directory])

    def completed_backup(self):
        if self.context.backup.job.is_dryrun:
            return
        if self.config['purge-policy'] == 'after-backup':
            self._purge(exclude=[self.context.backup.backup_directory])


@hook_registry.register
class UserCommandHook(HookPlugin):
    """Execute a user command"""

    name = 'user-commands'
    priority = 100

    def before_backup(self):
        if self.config.before_backup_command:
            LOG.info("Running before-backup-command")

    def completed_backup(self):
        if self.config.completed_backup_command:
            LOG.info("Running completed-backup-command")

    def failed_backup(self):
        if self.config.failed_backup_command:
            LOG.info("Running failed-backup-command")

    def after_backup(self):
        if self.config.after_backup_command:
            LOG.info("Running after-backup-command")

