"""
holland.core.stream.plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~

This module provides the plugin interface for stream plugins

:copyright: 2010-2011 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import os
from holland.core.plugin import (ConfigurablePlugin, PluginError,
                                 plugin_registry,
                                 load_plugin, iterate_plugins)


class BaseStream(object):
    closed = False
    encoding = None
    errors = None
    newlines = None
    softspace = 0

    def __init__(self, path, mode='r', *args, **kwargs):
        self.name = path
        self.mode = mode
        self.args = args
        self.kwargs = kwargs

    def close(self):
        """Close the stream.  A closed stream should not be written to any more
        and any more operations that attempt to do so should raise a ValueError
        per standard python file object semantics."""

    def flush(self):
        """Flush the stream's internal buffer."""

    def next(self):
        """Provide the next input line from the stream."""
        # IOError: File not open for reading if mode !~ 'r'
        raise NotImplementedError()

    def read(self, size=-1):
        """Read at most size bytes from the stream.
        If the size argument is negative or omitted read all data from the
        stream until EOF.
        """
        raise NotImplementedError()

    def readline(self, size=-1):
        """Read one entire line from the stream"""
        raise NotImplementedError()

    def readlines(self):
        """Read all the lines from the stream"""
        return [line for line in self]

    def seek(self, offset, whence=os.SEEK_SET):
        "Set the current position in the file."""
        #IOError: [Errno 29] Illegal seek
        raise NotImplementedError()

    def tell(self):
        """Return the files current position"""
        return 0

    def write(self, str):
        """Write a string to a file"""
        raise NotImplementedError()

    def writelines(self, sequence):
        """Write a sequence of string to the stream"""
        raise NotImplementedError()

    def __iter__(self):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        self.close()

class FileDescriptorStream(BaseStream):
    def fileno(self):
        raise NotImplementedError()

    def read(self, size=-1):
        chunk = size if size > 0 else 4096
        data = os.read(self.fileno(), chunk)
        while data:
            if size > 0:
                chunk -= len(data)
            buf = os.read(self.fileno(), chunk)
            if not buf:
                break
            data += buf
        return data

    def write(self, data):
        while data:
            nbytes = os.write(self.fileno(), data)
            data = data[nbytes:]

    def tell(self):
        return os.lseek(self.fileno(), 0, os.SEEK_CUR)

    def readlines(self):
        return [line for line in self]

    def __iter__(self):
        return os.fdopen(self.fileno(), self.mode)



class StreamError(IOError):
    """Exception in stream"""

class StreamPlugin(ConfigurablePlugin):
    """Base Plugin class"""
    
    namespace = 'holland.stream'
    name = '<default stream plugin>'
    aliases = ()

    def open(self, name, mode):
        """Open a stream and return a normal file"""
        return open(name, mode)

    def stream_info(self, name, method, *args, **kwargs):
        """Provide information about this stream"""
        return dict(
            extension='', # no special extensions
            name=name,
            method=method,
            description="%s: args=%r kwargs=%r" % (self.__class__.__name__,
                                                   args, kwargs)
        )

@plugin_registry.register
class FileStreamPlugin(StreamPlugin):
    """Stream plugin that opens standard files"""
    name = 'none'
    aliases = tuple(['file'])
    summary = 'uncompressed file stream'
    aliases = tuple(['none'])
