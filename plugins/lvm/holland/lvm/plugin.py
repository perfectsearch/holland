"""
holland.lvm.plugin
~~~~~~~~~~~~~~~~~~

Base LVM plugin for backing up data via a snapshot

"""
import collections
import contextlib
import errno
import logging
import os
import tempfile
import time


from holland.core.archive import load_archiver
from holland.core.config.config import Config
from holland.core.backup.plugin import BackupPlugin
from holland.core.util.path import TemporaryDirectory, relpath, getmount
from holland.core.util.fmt import format_interval, format_bytes

from holland.lvm.volume import LogicalVolume, LVMSnapshotExistsError, LVMError, getmount

LOG = logging.getLogger()

class LVMSnapshot(BackupPlugin):
    max_create_attempts = 3

    summary = "Backup via an LVM snapshot volume"

    def load_volume(self):
        """Load the logical volume referenced by this plugin configuration

        :returns: LogicalVolume instance
        :raises: BackupError if neither target-path nor source-volume is set
        """
        # XXX: add support for dm-crypt volumes
        volume = None
        cfg = self.lvm_config
        if cfg.source_volume:
            volume = LogicalVolume.from_device(cfg.source_volume)
        if cfg.target_path:
            if not volume:
                volume = LogicalVolume.from_path(cfg.target_path)
                LOG.info("Loaded volume %s for target-path '%s'",
                         volume.device, cfg.target_path)
            else:
                assert mountpoint(target_path) in volume.mountpoints()

        if not volume:
            self.fail("No logical volume found. "
                      "Specify either target-path or source-volume")
        return volume

    @property
    def lvm_config(self):
        return self.config['lvm']

    # this is broken
    # what happens if we have exceeded the maximum number of attempts?
    @contextlib.contextmanager
    def create_snapshot(self, volume):
        name = self.lvm_config.snapshot_name
        extents = self.lvm_config.snapshot_size
        options = self.lvm_config.snapshot_create_options
        for attempt in xrange(self.max_create_attempts):
            try:
                start_time = time.time()
                with volume.snapshotted(name, 
                                        extents,
                                        options) as snapshot:
                    LOG.info("Snapshot creation took %s",
                             format_interval(time.time() - start_time,
                                 precision=5))
                    yield snapshot
                    LOG.info("Refreshing snapshot info")
                    snapshot.refresh()
                LOG.info("Snapshot was active for %s",
                         format_interval(time.time() - start_time, precision=5))
                snap_used = format_bytes(snapshot.lv_size*snapshot.snap_percent)
                snap_total = format_bytes(snapshot.lv_size)
                LOG.info("Snapshot used %s of %s allocated",
                         snap_used, snap_total)
            except LVMSnapshotExistsError, exc:
                # This is only raised on lvcreate, if we detect another
                # snapshot exists
                # XXX: this can fail and will raise another exception
                self.release_snapshot(exc.snapshot)
            else:
                break
        else:
            self.fail("Failed to create snapshot after %d attempts", attempt)

    @contextlib.contextmanager
    def create_mountpoint(self):
        """Create a mountpoint"""
        snapshot_mountpoint = self.lvm_config.snapshot_mountpoint
        if not snapshot_mountpoint:
            snapshot_mountpoint = tempfile.gettempdir()
        else:
            try:
                os.makedirs(snapshot_mountpoint)
            except OSError, exc:
                if exc.errno != errno.EEXIST:
                    raise
            os.chmod(snapshot_mountpoint, 0755)

        with TemporaryDirectory(dirname=snapshot_mountpoint) as tmpdir:
            LOG.info("Created snapshot mountpoint: %s", tmpdir)
            yield tmpdir

    def release_snapshot(self, snapshot):
        """Release a snapshot volume"""
        logging.warn(" ! Found existing snapshot '%s'", snapshot.device)
        snapshot.unmount()
        logging.warn(" ! unmounted existing snapshot")
        if snapshot.exists():
            snapshot.remove()
            logging.warn(" ! removed existing snapshot")


    def archive(self, mountpoint):
        cfg = self.lvm_config
        relative_paths = set(self.lvm_config.relative_paths)
        if not relative_paths:
            if cfg.target_path:
                rpath = relpath(cfg.target_path, getmount(cfg.target_path))
                relative_paths.add(rpath)
            else:
                relative_paths.add('.')

        LOG.info("Examining paths '%s' relative to mountpoint '%s'",
                 ','.join(relative_paths), mountpoint)
        archiver = load_archiver(cfg.archive_method)
        archiver.bind(self.context)
        for rpath in relative_paths:
            logging.info("Archiving %s relative to %s", rpath, mountpoint)
            archiver.add_path(rpath, mountpoint)
        backup_directory = os.path.join(self.backup_directory, 'data')
        os.mkdir(backup_directory)
        archiver.archive(backup_directory)

    def dryrun(self):
        volume = self.load_volume()
        LOG.info("Source volume: %s", volume.device)
        snapshot_size = self.lvm_config.snapshot_size
        volume.parse_snapshot_size(snapshot_size)
        if not self.lvm_config.snapshot_name:
            self.lvm_config.snapshot_name = volume.lv_name + '_snapshot'
            LOG.info("snapshot-name is empty, using '%s'", self.lvm_config.snapshot_name)
        snapshot_mountpoint = self.lvm_config.snapshot_mountpoint
        if not snapshot_mountpoint:
            snapshot_mountpoint = tempfile.gettempdir()
        LOG.info("Mountpoint under %s", snapshot_mountpoint)
        LOG.info("Archive method '%s'", self.lvm_config.archive_method)
        target_path = self.lvm_config.target_path
        archive_paths = [os.path.join(target_path, rpath) for rpath in self.lvm_config.relative_paths]
        LOG.info("Archive paths: %s", ','.join(archive_paths))

    def backup(self):
        volume = self.load_volume()
        self.lvm_config.snapshot_size = volume.parse_snapshot_size(self.lvm_config.snapshot_size)
        if not self.lvm_config.snapshot_name:
            self.lvm_config.snapshot_name = volume.lv_name + '_snapshot'
            LOG.info("snapshot-name is empty, using '%s'", self.lvm_config.snapshot_name)
        with self.create_mountpoint() as mountpoint:
            with self.create_snapshot(volume) as snapshot:
                plugin_metadata = os.path.join(self.backup_directory, '.holland', 'lvm')
                with open(plugin_metadata, 'ab') as fileobj:
                    print >>fileobj, "snapshot-device = %s" % snapshot.device
                    print >>fileobj, "snapshot-device-uuid = %s" % snapshot.lv_uuid
                    fileobj.flush()
                    os.fsync(fileobj.fileno())

                snapshot_mount_options = self.lvm_config.snapshot_mount_options
                if snapshot_mount_options:
                    logging.info("Mounting '%s' with options -o %s",
                                 snapshot.device, ','.join(snapshot_mount_options))
                with snapshot.mounted(at=mountpoint,
                                      mount_options=snapshot_mount_options):
                    logging.info("Mounted '%s' at '%s'",
                                 snapshot.device,
                                 snapshot.mountpoint())
                    logging.info("Archiving snapshot data")
                    self.archive(mountpoint)

    def release(self):
        pass
