"""
holland.lvm.volume
~~~~~~~~~~~~~~~~~~

API for manipulating logical volumes

"""
import collections
import contextlib
import logging
import subprocess
from holland.core.exc import HollandError

LOG = logging.getLogger()

class LVMError(HollandError):
    "Base exception when an error is encountered in an lvm operation"
    def __init__(self, message, context=None):
        self.message = message
        self.context = context

    def __str__(self):
        return self.message

class LVMSnapshotExistsError(LVMError):
    "Raised when LogicalVolume.snapshot hits a naming conflict"
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def __str__(self):
        return "LVM snapshot '%s' already exists" % snapshot_pathspec


def capture_stdout(argv):
    with open(os.devnull, 'rb') as stdin:
        try:
            process = Popen(argv,
                            stdin=stdin,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            close_fds=True)
            stdout, _ = process.communicate()
            return stdout
        except OSError, exc:
            # EPERM, ENOENT, etc.
            raise #XXX: raise something more useful here
        except subprocess.CalledProcessError, exc:
            # lvs exited with non-zero status
            # XXX: exc.output will probably have useful messages for
            # troubleshooting
            for line in exc.output.splitlines():
                LOG.error("! %s", line)
            raise # XXX: raise something more useful here


def lvsnapshot(device, name, extents, extra_options=(), lvcreate='lvcreate'):
    argv = [
        lvcreate,
        '--snapshot',
        '--name=' + name,
        '--extents=' + extents,
        device
    ] + list(extra_options)

    try:
        LOG.info("$ %s", subprocess.list2cmdline(argv))
        for line in capture_stdout(argv).splitlines():
            LOG.info("%s", line.strip())
    except subprocess.CalledProcessError, exc:
        raise LVMError("Snapshotting logical volume '%s' failed." % device,
                       context=exc.output)
    return device

def lvremove(device, lvremove='lvremove'):
    argv = [
        lvremove,
        '--force',
        device
    ]
    try:
        LOG.info("$ %s", subprocess.list2cmdline(argv))
        for line in capture_stdout(argv).splitlines():
            LOG.info("%s", line.strip())
    except subprocess.CalledProcessError, exc:
        raise LVMError("Removing logical volume '%s' failed." % device,
                       context=exc.output)

def mount(device, path, options=(), mount='mount'):
    argv = [
        mount,
        device,
        path,
    ]
    if options:
        argv.insert(1, '-o')
        argv[2:2] = options

    try:
        for line in capture_stdout(argv).splitlines():
            LOG.info("%s", line)
    except subprocess.CalledProcessError, exc:
        raise LVMError("Mounting device '%s' failed." % device,
                       context=exc.output)

def unmount(device, unmount='umount'):
    argv = [
        unmount,
        device
    ]
    try:
        for line in capture_stdout(argv).splitlines():
            LOG.info("%s", line)
    except subprocess.CalledProcessError, exc:
        raise LVMError("Unmounting device '%s' failed." % device,
                       context=exc.output)

def lvs(pathspec=None, extra_columns=(), lvs='lvs'):
    basecolumns = [
        'vg_name',
        'lv_name',
        'lv_attr',
        'lv_uuid',
        'lv_size',
        'vg_free_count',
        'vg_extent_size'
    ]
    # attributes we always lookup
    extra_columns = list(extra_columns)
    for name in basecolumns:
        if name in extra_columns:
            extra_columns.remove(name)

    columns = basecolumns + extra_columns
    fields = ','.join(columns)
    argv = [
        lvs,
        '--noheadings',
        '--separator=,',
        '--nosuffix',
        '--units=b',
        '--options=' + fields
    ]

    if pathspec:
        argv.append(pathspec)

    VolumeInfo = collections.namedtuple('VolumeInfo', ' '.join(columns))
    try:
        for line in capture_stdout(argv).splitlines():
            values = [value.strip() for value in line.split(',')]
            # both vg_free_count and vg_extent_size are integers
            # convert from the string
            # these will always be the 4th and 5th element based on
            # ``basecolumns`` above.
            for idx, name in enumerate(columns):
                if name.endswith('_size') or name.endswith('_count'):
                    values[idx] = int(values[idx])
                elif name.endswith('percent'):
                    values[idx] = float(values[idx]) / 100.0
            yield VolumeInfo(*values)
    except subprocess.CalledProcessError, exc:
        raise LVMError("LVM command: lvs '%s' failed." % pathspec,
                       context=exc.output)

class VolumeGroup(object):
    def __init__(self, volume_info):
        self.volume_info = volume_info

    @property
    def name(self):
        return self.volume_info.vg_name

    @property
    def extent_size(self):
        return self.volume_info.vg_extent_size

    def to_extents(self, size):
        """Convert a size in bytes to extents based on this VolumeGroup's
        extent size"""
        return int(size / self.extent_size)

    def __getattr__(self, name):
        return getattr(self.volume_info, name)

def path_to_device(path):
    """Return the filesystem path to the device that ``path``
    resides on.

    path_to_device('/var/lib/mysql') => '/dev/sda1'
    """
    mpath = getmount(path)
    with open('/etc/mtab', 'rb') as mtabf:
        for line in reversed(mtabf.readlines()):
            device, sysmount = line.split()[0:2]
            if sysmount == mpath:
                return device
        raise OSError(errno.ENOENT, "No mountpoint found for '%s'" % path)

def getmount(path):
    """Return the filesystem path that is the mountpoint
    for the filesystem that the provided ``path`` resides on

    mountpoint('/') => '/'
    mountpoint('/mnt/mysql/data/mysql/user.frm') => '/mnt/mysql'

    We walk up the directory hierarchy starting from ``path`` until
    os.path.ismount() returns true
    """
    path = os.path.realpath(os.path.abspath(path))
    while path and not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


class LogicalVolume(object):
    def __init__(self, volume_info):
        self.volume_info = volume_info

    def __getattr__(self, name):
        return getattr(self.volume_info, name)

    @property
    def name(self):
        return self.volume_info.lv_name

    @property
    def device(self):
        return os.path.join(os.sep, 'dev', self.vg_name, self.lv_name)

    @classmethod
    def from_path(cls, path, extra_options=()):
        device = path_to_device(path)
        return cls.from_device(device, extra_options)

    def mountpoint(self):
        """Find the most recent mountpoint associated with this volume"""
        for mountpoint in self.mountpoints():
            return mountpoint

    def mountpoints(self):
        """Find all mountpoints associated with this logical volume"""

        real_device_path = os.path.realpath(self.device)
        try:
            with open('/proc/mounts', 'rb') as proc_mounts:
                for line in reversed(proc_mounts.readlines()):
                    dev, mountpoint = line.split()[0:2]
                    if os.path.realpath(dev) == real_device_path:
                        yield mountpoint
        except IOError, exc:
            raise

    def is_mounted(self):
        """Check if this logical volume is currently mounted

        :returns: true if mounted and false otherwise
        :rtype: bool
        """
        return self.mountpoint() is not None

    def exists(self):
        return os.path.exists(self.device)

    def refresh(self):
        for lvinfo in lvs(self.device, self.volume_info._fields):
            self.volume_info = lvinfo
            break

    @classmethod
    def from_device(cls, device, extra_options=()):
        for lvinfo in lvs(device, extra_options):
            return cls(lvinfo)
        else:
            return None

    def snapshot(self, name, extents, extra_options=()):
        """Snapshot the logical volume instance

        :param name: snapshot name
        :param extents: number of extents to allocate to snapshot
        :param extra_options: additional options to pass to lvcreate
        :returns: LogicalVolume instance representing snapshot
        """
        device = self.device
        snapshot_device = os.path.join('/dev', self.vg_name, name)
        try:
            lvsnapshot(device,
                       name=name,
                       extents=extents,
                       extra_options=extra_options)
        except LVMError, exc:
            snapshot_volume = LogicalVolume.from_device(snapshot_device)
            if snapshot_volume:
                raise LVMSnapshotExistsError(snapshot_volume)
            else:
                raise LVMError("Failed to create snapshot")
        else:
            return LogicalVolume.from_device(snapshot_device,
                                             extra_options=('snap_percent','origin'))

    def parse_snapshot_size(self, value):
        """Convert a string to a valid argument for lvcreate --extents

        :param value: value to parse. This may be either a valid
                      extents described as <value>%(FREE|VG|PV) or
                      a size string with a units such as:
                      <value>(T|G|M|K)
                      For compatibility, a bare integer is interpreted
                      as megabytes
        :returns: string argument suitable for passing to --extents
        """
        extents_cre = re.compile(r'^[0-9]+%(FREE|VG|PV)', re.I)
        if extents_cre.match(value):
            return value
        # otherwise treat it as a value
        # treat a bare number as a value in megabytes
        if re.match('^[0-9]+$', value):
            value += 'M'
        # parse value via holland.core.util.bytes_from_human_size
        try:
            nbytes = bytes_from_human_size(value)
        except ValueError:
            raise LVMError("Invalid snapshot size '%s'" % value)
        if nbytes < 0:
            raise LVMError("Negative snapshot size '%s'" % value)
        # round up to a valid number of extents
        extent_size = self.vg_extent_size
        # this is essentially ceil(nbytes / extent_size)
        nextents = (nbytes + extent_size - 1) // extent_size
        LOG.info("Converted snapshot-size = '%s' to %s extents", nextents)
        # cap extents to the number we currently see as available
        free_extents = self.vg_free_count
        capped_extents = min(free_extents, nextents)
        if not capped_extents:
            if not nextents:
                raise LVMError("snapshot-size '%s' specified zero extents. Please specify 1 or more extents")
            else:
                raise LVMError("No free extents available in volume-group '%s'" % self.vg_name)
        if capped_etents < nextents:
            LOG.info("Volume group '%s' only has %d free extents. Capping snapshot-size",
                     self.vg_name, free_extents)
        return str(capped_extents)

    @contextlib.contextmanager
    def snapshotted(self, name, extents, lvcreate_options=()):
        snapshot = self.snapshot(name, extents, lvcreate_options)
        try:
            yield snapshot
        finally:
            snapshot.remove()

    @contextlib.contextmanager
    def mounted(self, at, mount_options=()):
        self.mount(at, mount_options)
        try:
            yield at
        finally:
            self.unmount()

    def mount(self, path, extra_options=()):
        """Mount this logical volume

        :param path: path where the logical volume should be mounted
        :param extra_options: additional optionsthat should be passed to mount
        """
        mount(self.device, path, extra_options)

    def unmount(self):
        """Unmount this snapshot

        This currently unmounts the snapshot from every mountpoint found in
        /proc/mounts
        """
        while self.is_mounted():
            unmount(self.device)

    def remove(self):
        lvremove(self.device)

    def __repr__(self):
        return '{name}({attributes})'.format(
            name=self.__class__.__name__,
            attributes=self.volume_info
        )

