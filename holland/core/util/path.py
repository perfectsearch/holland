"""
    holland.core.util.path
    ~~~~~~~~~~~~~~~~~~~~~~

    Path manipulation utlity methods

    :copyright: 2008-2010 Rackspace US, Inc.
    :license: BSD, see LICENSE.rst for details
"""

# Functions added here should really be as portable as possible

import os
import errno

# Taken from posixpath in Python2.6
def relpath(path, start=os.curdir):
    """Return a relative version of a path"""

    if not path:
        raise ValueError("no path specified")

    start_list = [x for x in os.path.abspath(start).split(os.sep) if x]
    path_list = [x for x in os.path.abspath(path).split(os.sep) if x]

    # Work out how much of the filepath is shared by start and path.
    i = len(os.path.commonprefix([start_list, path_list]))

    rel_list = [os.pardir] * (len(start_list)-i) + path_list[i:]
    if not rel_list:
        return os.curdir
    return os.path.join(*rel_list)

def getmount(path):
    """Return the mount point of a path

    :param path: path to find the mountpoint for

    :returns: str mounpoint path
    """

    path = os.path.realpath(path)

    while path != os.path.sep:
        if os.path.ismount(path):
            return path
        path = os.path.abspath(os.path.join(path, os.pardir))
    return path

def disk_free(target_path):
    """
    Find the amount of space free on a given path
    Path must exist.
    This method does not take into account quotas

    returns the size in bytes potentially available
    to a non privileged user
    """
    path = getmount(target_path)
    info = os.statvfs(path)
    return info.f_frsize*info.f_bavail

def directory_size(path):
    """
    Find the size of all files in a directory, recursively

    Returns the size in bytes on success
    """
    total_size = os.path.getsize(path)
    for root, dirs, files in os.walk(path):
        for name in dirs:
            path = os.path.join(root, name)
            try:
                total_size += os.lstat(path).st_size
            except OSError:
                pass
        for name in files:
            path = os.path.join(root, name)
            try:
                nbytes = os.lstat(path).st_size
                total_size += nbytes
            except OSError:
                pass
    return total_size

def ensure_directory(path):
    """Ensure a directory path exists

    :raises: OSError if an error is encountered.  If the path already exists,
             we silently swallow the EEXIST notification
    :returns: True if a directory was created, false otherwise
    """
    try:
        os.makedirs(path)
        return True
    except OSError, exc:
        if exc.errno != errno.EEXIST:
            raise
    return False

def which(cmd, path=None):
    """Resolve a command to it's full path

    >>> which('lvs')
    '/sbin/lvs'
    >>> which('foo')
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "path.py", line 59, in which
        raise OSError(errno.ENOENT, '%r: command not found' % cmd)
    OSError: [Errno 2] 'foo': command not found

    :param cmd: command name to resolve
    :param path: list of directories to resolve ``cmd`` against
    :returns: absolute path name ``cmd`` resolves to
    :raises: OSError if no command found in ``path``
    """
    if path is None:
        path = os.environ.get('PATH', '').split(os.pathsep)
    for dirname in path:
        binpath = os.path.abspath(os.path.normpath(os.path.join(dirname, cmd)))
        if os.path.isfile(binpath) and os.access(binpath, os.X_OK):
            return binpath
    raise OSError(errno.ENOENT, '%r: command not found' % cmd)
