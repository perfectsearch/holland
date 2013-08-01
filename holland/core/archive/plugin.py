"""
holland.core.archive.plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Archiver plugin interface
"""

import os
import logging
from subprocess import Popen, list2cmdline
from holland.core.exc import HollandError
from holland.core.plugin import (ConfigurablePlugin,
                                 plugin_registry,
                                 load_plugin,
                                 iterate_plugins)
from holland.core.config.validators import AbstractValidator, ValidatorError

LOG = logging.getLogger(__name__)

class ArchiveError(HollandError):
    "Base exception for errors that occur during archiving"

class ArchiverBase(ConfigurablePlugin):

    namespace = 'holland.archiver'

    config = None

    def __init__(self, name):
        ConfigurablePlugin.__init__(self, name)
        self.paths = []

    def bind(self, context):
        self.context = context
        self.config = self.context.config[self.name]

    def terminate(self, signal):
        """External processes may want to terminate the long-running
        archival process abruptly.
        """
        raise NotImplemented

    def add_path(self, path, basedir='.'):
        self.paths.append((path, basedir))

    def archive(self, dstdir):
        "Archive data from srcdir to dstdir"
        raise NotImplementedError()

def available_archivers():
    results = []
    for plugin in set(iterate_plugins('holland.archiver')):
        results.append(plugin.name)
    return results

def load_archiver(name):
    return load_plugin('holland.archiver', name)

@plugin_registry.register
class ArchiveValidator(AbstractValidator):
    """Validate a compression method"""

    name = 'archive_method'

    def convert(self, value):
        """Verify an archiving method is available"""
        available = available_archivers()
        if value not in available:
            msg = "Invalid archiving method '%s'. Available methods %s" % (
                    value, ','.join(available)
                  )
            raise ValidationError(msg, value)
        return value

    def format(self, value):
        return value
