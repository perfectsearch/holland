"""
holland.core.stream.interface
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module provides the basic methods for the stream API

:copyright: 2010-2011 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import os
import logging
from holland.core.error import HollandError
from holland.core.config import Config, Configspec
from holland.core.plugin import ConfigurablePlugin, PluginError, \
                                load_plugin, iterate_plugins, plugin_registry
from holland.core.config.validators import BaseValidator, ValidationError

LOG = logging.getLogger(__name__)

class StreamError(HollandError):
    """Error encountered in the stream API"""

class StreamManager(object):
    def __init__(self, config):
        self.plugin = load_stream_plugin(config)
        self.streams = []

    def __enter__(self):
        return self

    def open(self, *args, **kwargs):
        """Open and register a new stream with this manager

        In this manager's __exit__  method, any registered streams will have their close() method invoked
        """
        stream = self.plugin.open(*args, **kwargs)
        self.streams.append(stream)
        return stream

    def __exit__(self, exc, exctype, traceback):
        error_count = 0
        for stream in self.streams:
            try:
                stream.close()
            except IOError, exc:
                error_count += 1
                LOG.error('Failed to close %s: %s', stream.name, exc)
                continue
        if error_count and exc is not None:
            raise StreamError("Failed to close one or more output streams.")


def load_stream_plugin(config):
    """Load a stream plugin by name"""
    LOG.debug("config: %r", config)
    try:
        method = config['method']
    except KeyError:
        raise StreamError("Error: Stream configuration has no 'method' option defined.")

    # XXX: raises PluginError
    plugin = load_plugin('holland.stream', method)

    plugin.configure(config)

    return plugin

def available_methods():
    """List available backup methods as strings

    These names are suitable for passing to open_stream(..., method=name, ...)
    """
    results = []
    for plugin in set(iterate_plugins('holland.stream')):
        results.append(plugin.name)
        results.extend(plugin.aliases)
    return results

class CompressionValidator(BaseValidator):
    """Validate a compression method"""

    def convert(self, value):
        """Verify a compression method is available"""
        available = available_methods()
        if value not in available:
            msg = "Invalid compression method '%s'. Available methods %s" % (
                    value, ','.join(available)
                  )
            raise ValidationError(msg, value)
        return value

    def format(self, value):
        return value

plugin_registry.register('holland.config.validators', 'compression',
                         CompressionValidator)

def open_basedir(basedir, method=None, config=()):
    """A wrapper to open a stream relative to some base path and dispatch to
    ``open_stream``

    :returns: 'open' compatible function
    """
    def dispatch(filename, mode='r'):
        """Dispatch to open_stream with the args/kwargs provided to the
        open_stream_wrapper method.

        :returns: File-like object from open-stream
        """
        filename = os.path.join(basedir, filename)
        return open_stream(filename, mode, method, config)
    return dispatch

def open_stream(filename, mode='r', method=None, config=()):
    """Open a stream with the provided method

    If not method is provided, this will default to the builtin file
    object
    """
    if method is None:
        method = 'builtin'
    cfg = Config(config)
    cfg.method = method

    try:
        stream = load_stream_plugin(config)
    except PluginError, exc:
        raise IOError("Stream plugin '%s' not found" % method)

    Configspec.from_string(stream.configspec()).validate(cfg)
    stream.configure(cfg)
    try:
        return stream.open(filename, mode)
    except IOError, exc:
        fancy_mode = ('r' in mode and 'reading' or
                      'w' in mode and 'writing' or
                      'a' in mode and 'appending' or
                      'invalid mode')
        msg = 'Failed to open stream {0} for {1}: {2}'.format(
                filename, fancy_mode, exc
              )
        LOG.error(msg)
        raise HollandError(msg)
