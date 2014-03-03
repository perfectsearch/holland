import logging
import subprocess
import os
from holland.core.util.path import directory_size, format_bytes
from holland.backup.mysql_lvm.plugin.common import build_snapshot
from holland.core.exceptions import BackupError
from holland.backup.file.common import setup_actions
from holland.lib.lvm import LogicalVolume, CallbackFailuresError, \
                            LVMCommandError, relpath, getmount

LOG = logging.getLogger(__name__)

# Specification for this plugin
# See: http://www.voidspace.org.uk/python/validate.html
CONFIGSPEC = """
[lvm]
# default: no
disabled = boolean(default=no)

# default: lvm lv + _snapshot
snapshot-name = string(default=None)

# default: minimum of 20% of lvm lv or lvm vg free size
snapshot-size = string(default=None)

# default: temporary directory
snapshot-mountpoint = string(default=None)

# A script used to flush data and quiesce
quiesce-script = string(default=None)

[FileBackup]

directories = string(default=None)
files = string(default=None)

[tar]
# Mode for opening the archive
# See: http://docs.python.org/2/library/tarfile.html#tarfile.open
# Default: w:gz
mode = option('w', 'w:', 'w:gz', 'w:bz2', default='w:gz')

method = option('none', 'gzip', 'gzip-rsyncable', 'pigz', 'bzip2', 'pbzip2', 'lzop', default='gzip')
options = string(default="")
level = integer(min=0, max=9, default=1)
""".splitlines()

class FileBackup(object):
    """An example backup plugin for holland"""

    def __init__(self, name, config, target_directory, dry_run=False):
        """Create a new ExamplePlugin instance

        :param name: unique name of this backup
        :param config: dictionary config for this plugin
        :param target_directory: str path, under which backup data should be
                                 stored
        :param dry_run: boolean flag indicating whether this should be a real
                        backup run or whether this backup should only go
                        through the motions
        """
        self.name = name
        self.config = config
        self.target_directory = target_directory
        self.dry_run = dry_run
        LOG.info("Validating config")
        self.config.validate_config(CONFIGSPEC)
        LOG.info("Validated config: %r", self.config)
        # LOG.info("config_dir: %s" % self.config['FileBackup']['directories'])

    def estimate_backup_size(self):
        """Estimate the size (in bytes) of the backup this plugin would
        produce, if run.

        :returns: int. size in bytes
        """
        size = 0
        if self.config['FileBackup']['directories'] is not None:
            for i in self.config['FileBackup']['directories'].split(","):
                if os.path.exists(i):
                    size += directory_size(i)
                else:
                    LOG.warn('Not backing up %s because it doesn\'t exist!' % i)
        if self.config['FileBackup']['files'] is not None:
            for i in self.config['FileBackup']['files'].split(","):
                if os.path.exists(i):
                    size += os.path.getsize(i)
                else:
                    LOG.warn('Not backing up %s because it doesn\'t exist!' % i)
        # LOG.info('Fileszieade: %r', size)
        return size

    def loop_through_dirs(self, success, failure=None):

        if not hasattr(success, '__call__'):
            raise Exception('loop_through_dirs(): Success is not a function!')

        if self.config['FileBackup']['directories'] is not None:
            for i in self.config['FileBackup']['directories'].split(","):
                if os.path.exists(i):
                    success(i)
                else:
                    failure(i)
        if self.config['FileBackup']['files'] is not None:
            for i in self.config['FileBackup']['files'].split(","):
                if os.path.exists(i):
                    success(i)
                elif failure is not None and hasattr(failure, '__call__'):
                    failure(i)

    def backup(self):
        """
        Do what is necessary to perform and validate a successful backup.
        """
        if self.dry_run:
            LOG.info("[Dry run] %s - test backup run" % self.info())
        else:
            LOG.info("%s - real backup run" % self.info())

        mounts = {}
        cliout = subprocess.Popen(['mount', '-l'], stdout=subprocess.PIPE).communicate()[0].decode('ascii')

        for line in cliout.split('\n'):

            parts = line.split(' ')
            if len(parts) > 2:
                mounts[parts[2]] = parts[0]

        nmounts = mounts.items()
        mounts = sorted(mounts.items(), key=lambda s: len(s[0]), reverse=True)

        lvmvolumes = {}
        filelist = {}

        def success(filename):
            for i in mounts:
                if filename.startswith(i[0]):
                    if i[0] not in lvmvolumes.keys():
                        try:
                            lvmvolumes[i[0]] = LogicalVolume.lookup_from_fspath(os.path.dirname(filename))
                        except LookupError, exc:
                            raise BackupError("Failed to lookup logical volume for %s: %s" %
                                              (os.path.dirname(filename), str(exc)))
                    if i[0] not in filelist.keys():
                        filelist[i[0]] = []
                    filelist[i[0]].append(filename)
                    return LOG.debug("File %s is located in %s" % (filename,i))
            LOG.error("File %s is not located in any local mount point")

        def error(filename):
            LOG.warn("Not backing up %s. Does it exist?" % filename)

        self.loop_through_dirs(success, error)

        LOG.debug('Backup LVM volumes:')
        for volume_pair in lvmvolumes.items():
            LOG.debug('==>%r' % repr(volume_pair))
            LOG.debug('  >%r' % repr(filelist[volume_pair[0]]))
            # for j in filelist[volume_pair[0]]:
            #     LOG.debug('%s' % relpath(j, volume_pair[0]))
            if not self.config['lvm']['disabled']:
                snapshot = build_snapshot(self.config['lvm'], volume_pair[1],
                                          suppress_tmpdir=self.dry_run)
                # for f in filelist[volume_pair[0]]:
                # rpath = relpath(f, volume_pair[0])
                # snap_datadir = os.path.abspath(
                #     os.path.join(snapshot.mountpoint, rpath))

                def archive_callback(my_file, callback):
                    rpath = relpath(my_file, volume_pair[0])
                    snap_datadir = os.path.abspath(
                        os.path.join(snapshot.mountpoint, rpath))
                    return callback(snap_datadir, rpath)
                # new_folders = os.path.abspath(
                #     os.path.join(self.target_directory, rpath))
                # try:
                #     os.makedirs(new_folders)
                # except OSError, e:
                #     if (e.errno == errno.EEXIST and
                #         os.path.exists(new_folders)):
                #         pass
                #     else:
                #         raise e
                setup_actions(snapshot=snapshot,
                              config=self.config,
                              # snap_datadir=snap_datadir,
                              archive_func=archive_callback,
                              filelist=filelist[volume_pair[0]],
                              spooldir=self.target_directory,
                              archive_name=volume_pair[1].lv_name)
                try:
                    snapshot.start(volume_pair[1])
                except CallbackFailuresError, exc:
                    # XXX: one of our actions failed.  Log this better
                    for callback, error in exc.errors:
                        LOG.error("%s", error)
                    raise BackupError("Error occurred during snapshot process. Aborting.")
                except LVMCommandError, exc:
                    # Something failed in the snapshot process
                    raise BackupError(str(exc))

    def info(self):
        """Provide extra information about the backup this plugin produced

        :returns: str. A textual string description the backup referenced by
                       `self.config`
        """
        return "Perfect Search Backup Plugin"
