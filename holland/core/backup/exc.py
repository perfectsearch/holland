"""
holland.core.backup.exc
~~~~~~~~~~~~~~~~~~~~~~~

Backup exceptions
"""

from holland.core.exc import HollandError

class BackupError(HollandError):
    """Generic BackupError encountered"""

class BackupHookError(HollandError):
    """Error encountered while executing a backup hook"""
