import os
import pwd
import grp
import stat
import time
import tarfile
import logging
from selinux import getfilecon
from holland.lib.archive import tar_archive

LOG = logging.getLogger(__name__)


def _make_sym_tarinfo(oldfile, name, path):
    stat = os.stat(oldfile)
    selinux = getfilecon(oldfile.encode('ascii'))
    tarinfo = tarfile.TarInfo(name=name)
    tarinfo.mtime = time.time()
    tarinfo.mode = stat.st_mode
    tarinfo.type = tarfile.SYMTYPE
    tarinfo.linkname = path
    tarinfo.uid = stat.st_uid
    tarinfo.gid = stat.st_gid
    tarinfo.uname = pwd.getpwuid(stat.st_uid).pw_name
    tarinfo.gname = grp.getgrgid(stat.st_gid).gr_name
    tarinfo.pax_headers['RHT.security.selinux'] = selinux[1]
    return tarinfo


def _make_tarinfo(oldfile, name, size):
    stat = os.stat(oldfile)
    selinux = getfilecon(oldfile.encode('ascii'))
    tarinfo = tarfile.TarInfo(name=name)
    tarinfo.size = size
    tarinfo.mtime = time.time()
    tarinfo.mode = stat.st_mode
    tarinfo.type = tarfile.REGTYPE
    tarinfo.uid = stat.st_uid
    tarinfo.gid = stat.st_gid
    tarinfo.uname = pwd.getpwuid(stat.st_uid).pw_name
    tarinfo.gname = grp.getgrgid(stat.st_gid).gr_name
    tarinfo.pax_headers['RHT.security.selinux'] = selinux[1]
    return tarinfo


class DirTar(tar_archive.TarArchive):

    def __init__(self, stream, mode, follow_symlinks):
        """
        Initialize a tar_archive.TarArchive.

        Arguments:

        path -- Path to the archive file
        mode -- Archive mode.  Default: w:gz (write + gzip) (see tarfile)
        """
        self.mode = mode
        self.archive = tarfile.open(fileobj=stream, mode=mode)
        self.archive.format = tarfile.PAX_FORMAT
        self.symlinks = follow_symlinks

    def add_file(self, path, name):
        """
        Add a file to the archive.

        Arguments:

        path -- Path to file for which to add to archive.
        name -- Name of file (for tarinfo)
        """
        if stat.S_ISSOCK(os.stat(os.path.join(path, name))):
            return
        if os.path.islink(path) and self.symlinks:
            tarinfo = _make_sym_tarinfo(path, name, os.readlink(path))
            self.archive.addfile(tarinfo)
        else:
            fileobj = open(path, 'r')
            size = os.fstat(fileobj.fileno()).st_size
            tarinfo = _make_tarinfo(path, name, size)
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
            relDir = os.path.relpath(root, path)
            for d in dirs:
                src = os.path.join(root, d)
                dir_name = os.path.join(name, relDir, d)
                stat = os.stat(src)
                selinux = getfilecon(src.encode('ascii'))

                tinfo = tarfile.TarInfo(dir_name)
                tinfo.type = tarfile.DIRTYPE
                tinfo.mtime = time.time()
                tinfo.mode = stat.st_mode
                tinfo.uid = stat.st_uid
                tinfo.gid = stat.st_gid
                tinfo.uname = pwd.getpwuid(stat.st_uid).pw_name
                tinfo.gname = grp.getgrgid(stat.st_gid).gr_name
                # oldheaders = self.archive.pax_headers
                tinfo.pax_headers['RHT.security.selinux'] = selinux[1]

                self.archive.addfile(tinfo)
                # self.archive.pax_headers = oldheaders
            for f in files:
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
        self.archive = DirTar(archive_stream, config['tar']['mode'],
                              config['FileBackup']['follow-symlinks'])

    def __call__(self, event, snapshot_fsm, snapshot_vol):
        # LOG.info('We would archive here >_>')
        # LOG.info('%s' % self.file_list)
        for f in self.file_list:
            self.archive_func(f, self._archive_callback)
        # LOG.info('Done archiving? >_>')

    def _archive_callback(self, path, rpath):
        # LOG.info(repr(path))
        if os.path.isdir(path):
            LOG.debug('Archiving Dir %s => %s' % (path, rpath))
            self.archive.add_dir(path, rpath)
        else:
            LOG.debug('Archiving File %s => %s' % (path, rpath))
            self.archive.add_file(path, rpath)
