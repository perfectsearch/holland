"""
    holland.core.backup
    ~~~~~~~~~~~~~~~~~~~

    Holland Backup API

    :copyright: 2010-2011 Rackspace US, Inc.
    :license: BSD, see LICENSE.rst for details
"""

from holland.core.backup.exc import BackupError
from holland.core.backup.plugin import BackupPlugin
from holland.core.backup.controller import BackupController, PurgeOptions
from holland.core.backup.spool import BackupSpool

__all__ = [
    'BackupPlugin',
    'BackupError',
    'BackupManager',
    'BackupSpool',
]
