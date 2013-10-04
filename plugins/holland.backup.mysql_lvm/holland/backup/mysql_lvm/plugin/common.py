
"""Utility functions to help out the mysql-lvm plugin"""
import os
import errno
import shutil
import shlex
import tempfile
import logging
from holland.core.exceptions import BackupError
from holland.core.util.fmt import format_bytes
from holland.lib.mysql import PassiveMySQLClient, MySQLError, \
                              build_mysql_config, connect
from holland.lib.lvm import Snapshot, parse_bytes, \
                            LVMCommandError, LogicalVolume

LOG = logging.getLogger(__name__)

def connect_simple(config):
    """Create a MySQLClientConnection given a mysql:client config
    section from a holland mysql backupset
    """
    try:
        mysql_config = build_mysql_config(config)
        LOG.debug("mysql_config => %r", mysql_config)
        connection = connect(mysql_config['client'], PassiveMySQLClient)
        connection.connect()
        return connection
    except MySQLError, exc:
        raise BackupError("[%d] %s" % exc.args)

def cleanup_tempdir(path):
    LOG.info("Removing temporary mountpoint %s", path)
    shutil.rmtree(path)

def remove_stale_snapshot(snapshot_device):
    """Remove a stale LVM snapshot

    Unmount and remove a snapshot volume referenced by
    ``snapshot_device``.  If ``snapshot_device`` does
    not reference a snapshot volume, that volume does
    not exist or the volume is otherwise busy this
    method will fail with an LVMCommandError

    Otherwise, the volume is removed and the backup
    may proceed.

    :param snapshot_device: string path to the snapshot device
                            e.g. '/dev/vg/holland_snapshot'
    :raises: LVMCommandError

    """
    LOG.info("Checking for old active snapshot")
    try:
        snapshot = LogicalVolume.lookup(snapshot_device)
    except LookupError:
        LOG.info("No old snapshots found")
    else:
        snapshot_size = int(float(snapshot.lv_size) *
                            float(snapshot.snap_percent or snapshot.lv_size))
        LOG.info("Found '%s' (lv_attr=%s size=%s)",
                 snapshot.device_name(),
                 snapshot.lv_attr, format_bytes(snapshot_size))

        if snapshot.lv_attr[0] != 's':
            LOG.error("Volume '%s' does not appear to be a snapshot. Aborting.",
                      snapshot.device_name())
            raise BackupError("Volume '%s' does not appear to be a snapshot. Aborting." %
                              snapshot.device_name())
        # Best effort attempt to remove the snapshot
        # We do not jump through hoops if the snapshot volume is busy
        # and simply fail early
        if snapshot.is_mounted():
            LOG.info("Unmounting '%s'", snapshot.device_name())
            snapshot.unmount()
        else:
            LOG.info("Snapshot is not mounted")
        if snapshot.exists():
            LOG.info("Removing '%s'", snapshot.device_name())
            snapshot.remove()
        else:
            LOG.info("Snapshot appearss to be already gone - not removing.")


def build_snapshot(config, logical_volume, dryrun=False):
    """Create a snapshot process for running through the various steps
    of creating, mounting, unmounting and removing a snapshot
    """
    snapshot_name = config['snapshot-name'] or \
                    logical_volume.lv_name + '_snapshot'
    extent_size = int(logical_volume.vg_extent_size)
    snapshot_size = config['snapshot-size']

    # When not in a dryrun mode, attempt to remove the snapshot
    snapshot_device = os.path.join('/dev',
                                   logical_volume.vg_name,
                                   snapshot_name)

    if config['remove-stale-snapshot']:
        if not dryrun:
            remove_stale_snapshot(snapshot_device)
        else:
            # Warn about an existing snapshot name during dryrun
            if os.path.exists(snapshot_device):
                LOG.warn("LVM snapshot volume with name '%s' exists: %s",
                         snapshot_name, snapshot_device)
                LOG.warn("Holland will try to remove this during a normal backup")
    else:
        LOG.info("remove-stale-snapshot option is disabled. Not checking for conflicting snapshot")

    if not snapshot_size:
        snapshot_size = min(int(logical_volume.vg_free_count),
                            (int(logical_volume.lv_size)*0.2) / extent_size,
                            (15*1024**3) / extent_size,
                           )
        LOG.info("Auto-sizing snapshot-size to %s (%d extents)",
                 format_bytes(snapshot_size*extent_size),
                 snapshot_size)
        if snapshot_size < 1:
            raise BackupError("Insufficient free extents on %s "
                              "to create snapshot (free extents = %s)" %
                              (logical_volume.device_name(),
                              logical_volume.vg_free_count))
    else:
        try:
            _snapshot_size = snapshot_size
            snapshot_size = parse_bytes(snapshot_size) / extent_size
            LOG.info("Using requested snapshot-size %s "
                     "rounded by extent-size %s to %s.",
                     _snapshot_size,
                     format_bytes(extent_size),
                     format_bytes(snapshot_size*extent_size))
            if snapshot_size < 1:
                raise BackupError("Requested snapshot-size (%s) is "
                                  "less than 1 extent" % _snapshot_size)
            if snapshot_size > int(logical_volume.vg_free_count):
                LOG.info("Snapshot size requested %s, but only %s available.",
                         config['snapshot-size'],
                         format_bytes(int(logical_volume.vg_free_count)*extent_size, precision=4))
                LOG.info("Truncating snapshot-size to %d extents (%s)",
                         int(logical_volume.vg_free_count),
                         format_bytes(int(logical_volume.vg_free_count)*extent_size, precision=4))
                snapshot_size = int(logical_volume.vg_free_count)
        except ValueError, exc:
            raise BackupError("Problem parsing snapshot-size %s" % exc)

    try:
        snapshot_create_options = config['snapshot-create-options'].encode('utf8')
        snapshot_create_options = shlex.split(snapshot_create_options)
    except UnicodeEncodeError, exc:
        raise BackupError("Error encoding snapshot-create-options: %s" % exc)
    except ValueError, exc:
        LOG.error("Invalid snapshot-create-options '%s': %s",
                  config['snapshot-create-options'], exc)
        raise BackupError("Error parsing snapshot-create-options: %s" % exc)

    mountpoint = config['snapshot-mountpoint']
    tempdir = False
    if not mountpoint:
        tempdir = True
        if not dryrun:
            mountpoint = tempfile.mkdtemp()
    else:
        try:
            os.makedirs(mountpoint)
            LOG.info("Created mountpoint %s", mountpoint)
        except OSError, exc:
            # silently ignore if the mountpoint already exists
            if exc.errno != errno.EEXIST:
                raise BackupError("Failure creating snapshot mountpoint: %s" %
                                  str(exc))


    snapshot = Snapshot(snapshot_name,
                        int(snapshot_size), 
                        mountpoint,
                        snapshot_create_options)
    if tempdir:
        snapshot.register('finish',
                          lambda *args, **kwargs: cleanup_tempdir(mountpoint))
    return snapshot

def log_final_snapshot_size(event, snapshot):
    """Log the final size of the snapshot before it is removed"""
    snapshot.reload()
    snap_percent = float(snapshot.snap_percent)/100
    snap_size = float(snapshot.lv_size)
    LOG.info("Final LVM snapshot size for %s is %s",
        snapshot.device_name(), format_bytes(snap_size*snap_percent))
