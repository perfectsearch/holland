"""Purge backups"""

from holland.core import BackupController, ConfigError
from holland.core.backup.controller import PurgeOptions
from holland.core.util.fmt import format_bytes
from holland.core.plugin import plugin_registry
from holland.cli.cmd.interface import ArgparseCommand, argument

@plugin_registry.register
class Purge(ArgparseCommand):
    """Purge backup command"""
    name = 'purge'
    summary = 'Purge a backup'
    description = """
    Purge a backup
    """

    arguments = [
        argument('--all', const=0,
                 action='store_const',
                 dest='retention_count'),
        argument('--retention-count', default=None,
                 type=int),
        argument('--dry-run', '-n', dest='dry_run', default=True),
        argument('--force', action='store_false', dest='dry_run'),
        argument('--execute', dest='dry_run', action='store_false'),
        argument('--backup-directory', '-d'),
        argument('backups', nargs='*'),
    ]

    def create_parser(self):
        parser = ArgparseCommand.create_parser(self)
        parser.set_defaults(
            backup_directory=self.config['holland']['backup-directory'],
            backups=self.config['holland']['backupsets'],
        )
        return parser

    def execute(self, namespace, parser):
        "Purge a backup"

        if not namespace.backup_directory:
            self.stderr("No backup-directory defined.")
            return 1

        self.config.holland.backup_directory = namespace.backup_directory
        controller = BackupController.from_config(self.config['holland'])

        if namespace.dry_run:
            self.stderr("Running in dry-run mode. "
                        "Use --force to run a real purge")

        dry_run = namespace.dry_run
        for name in namespace.backups:
            retention_count = self._retention_count(name)
            purge_opts = PurgeOptions(retention_count, dry_run)
            controller.purge_set(name)
        return 0

    def _retention_count(self, backupset):
        """Calculate the retention count for the backupset

        If the existing backupset configuration is not available this
        method currently assumes 1.
        """
        try:
            config = self.config.load_backupset(backupset)['holland:backup']
            return config['retention-count']
        except ConfigError:
            self.stderr("Failed to load backupset config for %s. "
                        "Defaulting to retention-count = 1", backupset)
            return 1

