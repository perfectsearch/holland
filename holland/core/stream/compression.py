"""
holland.core.stream.compression
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement compression command support

:copyright: 2010-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import errno
import logging
from tempfile import TemporaryFile
from subprocess import Popen, PIPE, STDOUT, list2cmdline
from holland.core.exc import HollandError
from holland.core.plugin import plugin_registry
from holland.core.util.path import which
from holland.core.stream.plugin import StreamPlugin, FileDescriptorStream

LOG = logging.getLogger(__name__)

def simple_command(args):
    """Run a simple command"""
    def wrapper():
        """Dispatch to a compression command"""
        process = Popen(args,
                        stdin=PIPE,
                        stdout=PIPE,
                        stderr=STDOUT,
                        close_fds=True)
        stdout, _ = process.communicate()
        if process.returncode != 0:
            raise IOError("Failed to run %s on ${path}" % list2cmdline(args))
    return wrapper

# XXX: Handle stderr correctly
class CompressionInputStream(FileDescriptorStream):
    """Open a compressed file in read-only mode"""
    def __init__(self, path, mode='r', args=()):
        super(CompressionInputStream, self).__init__(path, mode, args)
        self._process = Popen(args,
                              stdin=open(path, mode),
                              stdout=PIPE,
                              stderr=PIPE,
                              close_fds=True)

    def fileno(self):
        return self._process.stdout.fileno()

    def close(self):
        if self.closed:
            return
        self._process.stdout.close()
        self._process.wait()
        self.closed = True


class CompressionOutputStream(object):
    """Write to a compressed file"""
    def __init__(self, path, mode, args):
        self.name = path
        self.mode = mode
        self.args = args
        self.closed = False
        self._stderr = TemporaryFile()
        self._process = Popen(args,
                              stdin=PIPE,
                              stdout=open(path, 'w'),
                              stderr=self._stderr,
                              close_fds=True)

    def fileno(self):
        return self._process.stdin.fileno()

    def close(self):
        if self.closed:
            return
        self._process.stdin.close()
        self._process.wait()
        self.closed = True
        self._stderr.seek(0)
        for line in self._stderr:
            LOG.info("%s: %s", self.args[0], line.rstrip())
        self._stderr.close()
        if self._process.returncode != 0:
            raise IOError("%s exited with non-zero status" %
                    (list2cmdline(self.args)))

    def write(self, data):
        self._process.stdin.write(data)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        try:
            self.close()
        except:
            if exc_type is None:
                raise

class BaseCompressionPlugin(StreamPlugin):
    ext = ''

    def open(self, name, mode):
        cfg = self.config
        try:
            cmd = which(cfg['method'])
        except OSError as exc:
            raise HollandError("Could not find '%s' on path" % cfg['method'])

        args = [ cmd ]

        if cfg.get('options'):
            args.extend(cfg['options'])

        if 'r' in mode:
            args.insert(1, '-d')

        path = name

        if not path.endswith(self.ext):
            path += self.ext

        if 'r' in mode:
            return CompressionInputStream(path, mode, args)
        if 'w' in mode:
            if cfg.level:
                args.append('-' + str(cfg.level))
            return CompressionOutputStream(path, mode, args)
        raise IOError('invalid mode: ' + mode)

    def configspec(self):
        return """
        method = compression(default=gzip)
        level = integer(min=0, max=9, default=1)
        options = cmdline(default=list())
        additional-args = cmdline(default=list(), aliasof='options')
        inline = boolean(default=True)
        """
    @property
    def command(self):
        return self.name

# Handle variants
# gzip -> gzip, pigz
# bzip2 -> bzip2, pbzip2
# lzma -> xz, lzma (note: lzma is old and xz-utils is newer)
# lzop -> lzop
@plugin_registry.register
class GzipCompressionPlugin(BaseCompressionPlugin):
    name = 'gzip'
    ext = '.gz'
    summary = 'gzip compression'

@plugin_registry.register
class PigzCompressionPlugin(GzipCompressionPlugin):
    name = 'pigz'
    summary = 'parallel gzip compression'

@plugin_registry.register
class Bzip2CompressionPlugin(BaseCompressionPlugin):
    name = 'bzip2'
    ext = '.bz2'
    summary = 'bzip2 compression'


class Pbzip2CompressionPlugin(Bzip2CompressionPlugin):
    name = 'pbzip2'
    summary = 'parallel bzip2 compression'

@plugin_registry.register
class LzmaCompressionPlugin(BaseCompressionPlugin):
    name = 'lzma'
    aliases = tuple(['xz'])
    ext = '.xz'
    summary = 'lzma compression'

@plugin_registry.register
class LzopCompressionPlugin(BaseCompressionPlugin):
    name = 'lzop'
    ext = '.lzo'
    summary =  'lzo compression'

