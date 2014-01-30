import os, sys
import time
import errno
import logging
from datetime import datetime
from collections import namedtuple
from contextlib import contextmanager
from holland.core.util import replace_symlink
from holland.core.util import format_interval
from holland.core.config import Config
from holland.core.backup.exc import BackupError
from holland.core.backup import spool
from holland.core.backup import catalog
from holland.core.backup import models
from holland.core.backup import plugin
from holland.core.backup import util

LOG = logging.getLogger(__name__)

PurgeOptions = namedtuple('PurgeOptions', 'retention_count dry_run')

def check_config(config):
    if 'holland:backup' not in config:
        raise HollandError("No [holland:backup] section defined in config")

class BackupController:
    def __init__(self, spool, catalog):
        self.spool = spool
        self.catalog = catalog
        self.jobs = []

    @contextmanager
    def job(self, is_dryrun=False, external_id=None):
        job = models.Job(is_dryrun=is_dryrun, external_id=external_id)
        LOG.info("--- Starting backup job ---")
        start_time = time.time()
        self.jobs.append(job)
        with self.catalog.save(job) as job:
            LOG.info("Commandline: %s", job.cmdline)
            try:
                yield job
            finally:
                job.stop_time = datetime.now()
                job_count = len(job.backups)
                completed_count = sum(1 for backup in job.backups
                                        if backup.status == 'completed')
                LOG.info("Job executed with %d backups in %s",
                         job_count, format_interval(job.duration))
                LOG.info("--- Ending backup job (%d backups; %d successful) ---",
                         job_count, completed_count)
                self.jobs.pop()

    def current_job(self):
        return self.jobs[-1]

    def backup(self, config, name):
        LOG.info("--- Starting backup %s (%s) ---", config.path, name)
        plugin, config = util.validate(config)
        backup = models.Backup(name=name, job=self.current_job())
        start_time = time.time()
        try:
            with self.spool.lock(name):
                node = self.spool.add_node(namespace=name)
                backup.backup_directory = node.path
                context = util.BackupContext(backup=backup,
                                             config=config,
                                             node=node,
                                             plugin=plugin,
                                             controller=self)
                with self.catalog.save(context.backup):
                    util.execute_backup(context)
            return backup
        finally:
            LOG.info("Backup to %s took %s", backup.backup_directory,
                    format_interval(time.time() - start_time))
            LOG.info("--- Ending backup %s (%s) ---", config.path, name)

    def release(self, path):
        """Allow a backup plugin to cleanup after a previous backup"""
        path = os.path.realpath(path)
        try:
            config = Config.from_path(os.path.join(path, '.holland', 'config'))
        except IOError as exc:
            LOG.info("Unable to load backup config for %s. Skipping release",
                     path)
        else:
            plugin, config = util.validate(config)
            namespace = os.path.basename(os.path.dirname(path))
            name = os.path.basename(path)
            node = self.spool.load_node(namespace, name)
            # load from backup catalog db 
            # or generate a fake backup instance
            backup = self.catalog.load_backup_from_node(node)
            context = util.BackupContext(backup=backup,
                                         config=config,
                                         node=node,
                                         plugin=plugin,
                                         controller=self)
            plugin.bind(context)
            plugin.release()
        
    def purge_set(self, name, purge_options=None, exclude=()):
        if not purge_options:
            purge_options = PurgeOptions(retention_count=1, dry_run=True)

        # obtain a list of candidate backup paths
        # spool.backups will give us ordered backup
        # paths by st_mtime
        candidates = list(self.spool.iter_nodes(name))
        # maintain a list of the backups not to be purged
        kept_backups = []
        # keep the last ${retention_count} backups
        for node in reversed(candidates):
            backup = self.catalog.load_backup(backup_directory=node.path)
            if not backup:
                backup = self.catalog.load_backup_from_node(node)
            if node.path in exclude:
                kept_backups.append(node)
            if len(kept_backups) >= purge_options.retention_count:
                continue
            if backup.status == 'completed':
                kept_backups.append(node)
            
        # update spool symlinks
        if kept_backups:
            if purge_options.dry_run:
                LOG.info("Would point 'oldest' symlink to %s",
                         os.path.basename(kept_backups[0].path))
                LOG.info("Would point 'newest' symlink to %s",
                         os.path.basename(kept_backups[-1].path))
            else:
                replace_symlink(os.path.basename(kept_backups[0].path),
                                os.path.join(self.spool.path, name, 'oldest'))
                replace_symlink(os.path.basename(kept_backups[-1].path),
                                os.path.join(self.spool.path, name, 'newest'))
        else:
            if purge_options.dry_run:
                LOG.info("No backups kept. Would remove oldest/newest symlinks entirely")
            else:
                for link in ('oldest', 'newest'):
                    path = os.path.join(self.spool.path, name, link)
                    try:
                        os.unlink(path)
                    except OSError as exc:
                        if exc.errno != errno.ENOENT:
                            raise

        for node in candidates:
            if node.path in exclude:
                continue
            if node in kept_backups:
                continue

            if purge_options.dry_run:
                LOG.info("Would purge %s", node.path)
            else:
                try:
                    self.release(node.path)
                except:
                    LOG.info("Release failed", exc_info=True)
                LOG.info("Purging %s", node.path)
                node.purge()

        return kept_backups, candidates

    @classmethod
    def from_config(cls, config):
        return cls(spool.load_spool(config.backup_directory),
                   catalog.load_catalog(config.catalog_db))
