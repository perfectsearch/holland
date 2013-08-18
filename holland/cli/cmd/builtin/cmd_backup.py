"""Command to run a holland backup"""
import os
from holland.core.exc import HollandError
from holland.core.backup import BackupController, BackupError
from holland.core.config import ConfigError
from holland.core.plugin import plugin_registry
from holland.cli.cmd.interface import ArgparseCommand, argument

@plugin_registry.register
class Backup(ArgparseCommand):
    """Run a backup for one or more backupset configurations

    """
    name = 'backup'
    summary = "Run a backup"
    description = """
    Run a backup
    """
    aliases = ('bk',)
    arguments = [
        argument('--backup-directory', '-d', dest='directory'),
        argument('--dry-run', '-n', action='store_true'),
        argument('--catalog-db'),
        argument('backupset', nargs='*'),
    ]

    def __init__(self, *args, **kwargs):
        super(Backup, self).__init__(*args, **kwargs)

    def configure(self, config):
        self.config = config

    def create_parser(self):
        parser = ArgparseCommand.create_parser(self)
        parser.set_defaults(
            directory=self.config['holland']['backup-directory'],
            backupset=self.config['holland']['backupsets'],
            catalog_db=self.config['holland']['catalog-db'],
        )
        return parser

    def execute(self, namespace, parser):
        "Run the backup command"
        backupsets = namespace.backupset

        if not backupsets:
            self.stderr("Nothing to backup")
            return 1

        if not namespace.directory:
            self.stderr("No backup-directory specified.  "
                        "Please set a backup-directory in /etc/holland.conf "
                        "or use the --backup-directory=<path> option")
            return 1

    def execute(self, namespace, parser):
        "Run the backup command"
        backupsets = namespace.backupset

        if not backupsets:
            self.stderr("Nothing to backup")
            return 1

        if not namespace.directory:
            self.stderr("No backup-directory specified.  "
                        "Please set a backup-directory in /etc/holland/holland.conf "
                        "or use the --backup-directory=<path> option")
            return 1

        self.config['holland']['backup-directory'] = namespace.directory
        self.config['holland']['catalog-db'] = namespace.catalog_db
        dry_run = namespace.dry_run
        join = os.path.join
        controller = BackupController.from_config(self.config['holland'])
        try:
            with controller.job(is_dryrun=dry_run):
                for name in namespace.backupset:
                    cfg = self.load_config(name)
                    name, _ = os.path.splitext(os.path.basename(name))
                    controller.backup(cfg, name=name)
        except (KeyboardInterrupt, SystemExit):
            raise
        except HollandError as exc:
            self.debug("Failed backup", exc_info=True)
            self.stderr("%s", exc)
        except:
            self.stderr("Uncaught exception. Logging stacktrace for debugging purposes", exc_info=True)
        else:
            return 0
        return 1

    def load_config(self, name):
        "Run a single backup"
        try:
            return self.config.load_backupset(name)
        except IOError as exc:
            raise HollandError("Failed to load backup config %s: %s" %
                                (name, exc))


@plugin_registry.register
class ReleaseBackup(ArgparseCommand):
    name = 'release'
    summary = "release resources from an old backup"
    description = """
    Loads the plugin for a backup and requests that old
    resources be released.  This is usually called after
    a backup has been archived and may have allocated
    extended resources (e.g. allocated a snapshot that
    has been backed up, etc.)
    """

    arguments = [
        argument('--backup-directory', '-d', dest='directory'),
        argument('--catalog-db'),
        argument('paths', nargs='*'),
    ]

    def create_parser(self):
        parser = ArgparseCommand.create_parser(self)
        parser.set_defaults(
            directory=self.config['holland']['backup-directory'],
            catalog_db=self.config['holland']['catalog-db'],
        )
        return parser

    def execute(self, namespace, parser):
        self.config['holland']['backup-directory'] = namespace.directory
        self.config['holland']['catalog-db'] = namespace.catalog_db
        controller = BackupController.from_config(self.config['holland'])
        for path in namespace.paths:
            controller.release(path)
        return 0
