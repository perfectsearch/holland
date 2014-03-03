import os
import pwd
import grp
import time
import tarfile
import logging
from holland.lib.archive import tar_archive

LOG = logging.getLogger(__name__)

def _make_sym_tarinfo(name, path):
    tarinfo = tarfile.TarInfo(name=name)
    tarinfo.mtime = time.time()
    tarinfo.type = tarfile.SYMTYPE
    tarinfo.linkname = path
    tarinfo.uid = os.geteuid()
    tarinfo.gid = os.getegid()
    tarinfo.uname = pwd.getpwuid(os.geteuid()).pw_name
    tarinfo.gname = grp.getgrgid(os.getegid()).gr_name
    return tarinfo

class DirTar(tar_archive.TarArchive):

    def __init__(self, stream, mode):
        """
        Initialize a tar_archive.TarArchive.

        Arguments:

        path -- Path to the archive file
        mode -- Archive mode.  Default: w:gz (write + gzip) (see tarfile)
        """
        self.mode = mode
        self.archive = tarfile.open(fileobj=stream, mode=mode)

    def add_file(self, path, name):
        """
        Add a file to the archive.

        Arguments:

        path -- Path to file for which to add to archive.
        name -- Name of file (for tarinfo)
        """
        if os.path.islink(path):
            tarinfo = _make_sym_tarinfo(name, os.readlink(path))
            self.archive.addfile(tarinfo)
        else:
            fileobj = open(path, 'r')
            size = os.fstat(fileobj.fileno()).st_size
            tarinfo = tar_archive._make_tarinfo(name, size)
            self.archive.addfile(tarinfo, fileobj)
            fileobj.close()

    def add_dir(self, path, name):
        """
        Add a directory to the archive

        Arguments:

        path -- Path to directory for which to add to archive.
        name -- Name of the directory, prefix for the files.
        """
        for root, dirs, files in os.walk(path, topdown=False):
            for f in files:
                relDir = os.path.relpath(root, path)
                src = os.path.join(root, f)
                dest = os.path.join(name, relDir, f)
                self.add_file(src, dest)


class TarArchiveAction(object):
    """docstring for TarArchiveAction"""

    def __init__(self, snap_datadir, archive_stream, config, archive_func,
        filelist):
        self.file_list = filelist
        self.snap_datadir = snap_datadir
        self.archive_func = archive_func
        self.archive = DirTar(archive_stream, 'w:gz')

    def __call__(self, event, snapshot_fsm, snapshot_vol):
        # LOG.info('We would archive here >_>')
        # LOG.info('%s' % self.file_list)
        for f in self.file_list:
            self.archive_func(f, self._archive_callback)
        # LOG.info('Done archiving? >_>')

    def _archive_callback(self, path, rpath):
        # LOG.info(repr(path))
        if os.path.isdir(path):
            LOG.debug('Archiving Dir %s' % path)
            self.archive.add_dir(path, rpath)
        else:
            LOG.debug('Archiving File %s' % path)
            self.archive.add_file(path, rpath)
