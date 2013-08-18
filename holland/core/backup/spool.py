"""
holland.core.backup.spool
~~~~~~~~~~~~~~~~~~~~~~~~

Backup spool support
"""
import os
import errno
import fcntl
import shutil
from itertools import tee
from datetime import datetime
from contextlib import contextmanager
try:
    from functools import total_ordering
except ImportError:
    from holland.core.util.pycompat import total_ordering
from holland.core.util import directory_size
from holland.core.exc import HollandError

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    item_a, item_b = tee(iterable)
    next(item_b, None)
    return zip(item_a, item_b)

class SpoolError(HollandError):
    """Raised if an exception occurs during a spool operation"""


class SpoolLockError(SpoolError):
    """Raised if the spool has already been locked by some other process"""
    def __init__(self, namespace, pid):
        self.namespace = namespace
        self.pid = pid

    def __str__(self):
        return "'%s' already locked by process %s" % (self.namespace, self.pid)

class BackupSpool(object):
    """Manage a spool of backups

    :attr path: root path for the backup spool
    """

    #: root path for the backup spool
    path = None

    def __init__(self, path):
        self.path = path
        self.locked = {}

    def capacity(self):
        """Determine the capacity of the spool in bytes"""
        try:
            info = os.statvfs(self.path)
            return info.f_bavail*info.f_frsize
        except OSError as exc:
            raise SpoolError("Unable to stat spool (%d) %s" %
                             (exc.errno, exc.strerror))

    def add_node(self, namespace, name=None):
        """Add a new node to this spool

        :attr namespace: namespace to add this node
        :attr node_name: name for the new node

        If node_node is not specified, it will be set
        to the current timestamp

        :returns: ``BackupNode`` instance
        """
        join = os.path.join
        makedirs = os.makedirs
        namespace_path = join(self.path, namespace)
        try:
            makedirs(join(namespace_path, '.holland'))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise SpoolError("Failed to initialize '%s'" % namespace_path)

        ts = '{0:%Y%m%d_%H%M%S}'.format(datetime.now())
        if name is None:
            name = ts

        node_path = join(self.path, namespace, name)
        makedirs(join(node_path, '.holland'))
        node = BackupNode(node_path, namespace, self)
        with node.open(join('.holland', 'timestamp'), 'wb') as fileobj:
            fileobj.write(ts)
        return node

    def load_node(self, namespace, name):
        """Load a node from the given namespace"""
        join = os.path.join
        node_path = join(self.path, namespace, name)
        if not os.path.exists(node_path):
            raise SpoolError("No node '%s'" % node_path)
        return BackupNode(node_path, namespace, self)

    @contextmanager
    def lock(self, namespace):
        """Lock the namespace of this spool"""
        if self.locked.get(namespace):
            yield
        else:
            lock_path = os.path.join(self.path, namespace, '.holland', 'lock')
            try:
                os.makedirs(os.path.dirname(lock_path))
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    raise
            with open(lock_path, 'a+b') as lockf:
                try:
                    fcntl.flock(lockf.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)
                except IOError:
                    pid = lockf.read()
                    if not pid:
                        pid = 'unknown'
                    raise SpoolLockError(os.path.join(self.path, namespace), pid)
                self.locked[namespace] = True
                try:
                    lockf.truncate()
                    lockf.write(str(os.getpid()))
                    lockf.flush()
                    yield
                finally:
                    del self.locked[namespace]

    def iter_namespaces(self):
        """Iterate over the namespace names in this spool

        :yields: namespace name as string
        """
        join = os.path.join
        for name in sorted(os.listdir(self.path)):
            # ignore ext3's lost+found dir
            if os.path.ismount(self.path) and name == 'lost+found':
                # LOG.debug('Ignore backup namespace "%s"', name)
                continue
            # ignore symlinks
            if os.path.islink(join(self.path, name)):
                # LOG.debug('Ignoring symlink "%s"', name)
                continue
            yield name

    def iter_nodes(self, namespace):
        """Iterate over nodes within a namespace

        :yields: ``BackupNode`` instances
        """
        join = os.path.join
        namespace_path = join(self.path, namespace)
        def key_by_timestamp(name):
            ts_path = join(namespace_path, name, '.holland', 'timestamp')
            try:
                with open(ts_path, 'rb') as fileobj:
                    return datetime.strptime(fileobj.read(),
                                             '%Y%m%d_%H%M%S.%f')
            except (IOError, ValueError):
                return datetime.fromtimestamp(0)

        try:
            entries = os.listdir(namespace_path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise
        else:
            for name in sorted(entries, key=key_by_timestamp):
                if name == '.holland':
                    continue
                node_path = join(self.path, namespace, name)
                if os.path.islink(node_path):
                    continue
                yield BackupNode(node_path, namespace, self)

    __iter__ = iter_namespaces

    def first(self, namespace):
        """Return the first node in a namespace"""
        for node in self.iter_nodes(namespace):
            return node
        return None

    def last(self, namespace):
        """Return the last node in a namespace"""
        node = None
        for node in self.iter_nodes(namespace):
            pass
        return node

    def next(self, node):
        """Return the node immediately following the requested node"""
        for current, next in pairwise(self.iter_nodes(node.namespace)):
            if current == node:
                return next
        return None

    def previous(self, node):
        """Return the node just prior to the given node"""
        for current, next in pairwise(self.iter_nodes(node.namespace)):
            if next == node:
                return current
        return None

    def __repr__(self):
        return '{0}(path={1!r})'.format(self.__class__.__name__, self.path)


class BackupNode(object):
    """An entry in a backup spool namespace

    :attr path: path of this node
    :attr namespace: namespace where this node is located
    :attr spool: spool this node is attached to
    """
    #: path of this backup node
    path = None
    #: namespace this backupnode resides in
    namespace = None
    #: spool this backupnode is attached to
    spool = None

    def __init__(self, path, namespace, spool):
        self.path = path
        self.namespace = namespace
        self.spool = spool

    def timestamp(self):
        try:
            with self.open(os.path.join('.holland', 'timestamp'), 'rb') as fp:
                data = fp.read()
                return datetime.strptime(data, '%Y%m%d_%H%M%S.%f')
        except (IOError, ValueError):
            return datetime.fromtimestamp(0)

    def size(self):
        """Summarize the size of this backup node"""
        try:
            return directory_size(self.path)
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise SpoolError(
                    "Unable to determine size of '{path}': ({errno}) {msg}".format(
                        path=self.path,
                        errno=exc.errno,
                        msg=exc.strerror)
                    )
            else:
                return 0

    def purge(self):
        """Purge the data in this node's path"""
        try:
            shutil.rmtree(self.path)
        except OSError as exc:
            raise SpoolError("Failed to purge node: (%s) %s" %
                             (exc.errno, exc.strerror))

    def open(self, name, mode):
        """Open a stream relative to this node's path"""
        join = os.path.join
        return open(join(self.path, name), mode)

    def __eq__(self, other):
        return other.path == self.path

    def __lt__(self, other):
        return self.timestamp() < other.timestamp()
    def __repr__(self):
        return '{0}(path={1!r}, namespace={2!r}, spool={3!r})'.format(
                    self.__class__.__name__,
                    self.path,
                    self.namespace,
                    self.spool
                )

def load_spool(path):
    return BackupSpool(path)

