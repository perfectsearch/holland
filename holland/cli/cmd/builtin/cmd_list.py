"""Various list-* commands for holland.cli"""

import os
import textwrap
import logging
from holland.core import BackupSpool, iterate_plugins
from holland.core.util import format_bytes, format_datetime
from holland.cli.cmd.interface import ArgparseCommand, argument
from holland.core.plugin import plugin_registry

LOG = logging.getLogger(__name__)

@plugin_registry.register
class ListCommands(ArgparseCommand):
    """List available commands"""

    name = 'list-commands'
    aliases = ['lc']
    summary = 'List available holland commands'
    description = """
    List the available commands in holland with some
    information about each.
    """

    def execute(self, namespace, parser):
        """Run list-commands"""
        self.stdout("")
        self.stdout("Available commands:")
        commands = list(iterate_plugins(self.namespace))
        commands.sort()
        for cmd in commands:
            aliases = ''
            if cmd.aliases:
                aliases = " (%s)" % ','.join(cmd.aliases)
            self.stdout("%-15s%-5s %s", cmd.name, aliases, cmd.summary)
        return 0

    def plugin_info(self):
        return dict(
            name=self.name,
            summary=self.summary,
            description=self.description,
            author='Rackspace',
            version='1.1.0',
            holland_version='1.1.0'
        )

@plugin_registry.register
class ListPlugins(ArgparseCommand):
    """List available plugins"""

    name = 'list-plugins'
    aliases = ['lp']
    summary = 'List available holland plugins'
    description = """
    List available plugins in holland with some information about
    each

    Currently this lists the following plugin types:
    holland.backups     - backups plugins
    holland.stream      - output filtering plugins
    holland.hooks       - hook plugins
    holland.commands    - command plugins
    """

    def execute(self, namespace, parser):
        for group in ('backup', 'stream', 'archiver', 'commands'):
            plugin_list = list(iterate_plugins('holland.%s' % group))
            header = "%s plugins" % group.title()
            header_output = False
            seen = {}
            for plugin in plugin_list:
                if plugin.name in seen:
                    continue
                seen[plugin.name] = True
                if not header_output:
                    print header
                    print "-"*len(header)
                    header_output = True
                wrap = textwrap.wrap
                name = plugin.name
                name_width = 14 + 25 + 3
                summary = os.linesep.join(
                            wrap(getattr(plugin, 'summary') or '',
                                 initial_indent=' '*name_width,
                                 subsequent_indent=' '*name_width,
                                 width=79)).lstrip()   
                aliases = getattr(plugin, 'aliases')
                for alias in aliases:
                    seen[alias] = True
                extra = ''
                if aliases:
                    extra = '(aliases: %s)' % (' '.join(aliases),)
                print "%-14s%-25s - %-s" % (name, extra, summary)
            if seen:
                print
        return 0

class ListBackups(ArgparseCommand):
    """List backups stored in the backup directory

    This command will look in the global backup directory (if one is
    specified) or in the directory specified by the ``--backup-directory``
    option.  If neither is provided this command will fail and exit with
    non-zero status.
    """

    name = 'list-backups'
    aliases = ['lb']
    summary = 'List spooled backups'
    description = '''
    List available backups in the configured backup-directory
    '''

    arguments = [
        argument('--backup-directory', '-d'),
    ]
    def execute(self, namespace, parser):
        """List backups in a backup spool"""
        backup_directory = namespace.backup_directory or \
                           self.config['holland']['backup-directory']

        if backup_directory is None:
            self.stderr("No backup-directory specified")
            return 1

        spool = BackupSpool(backup_directory)
        backupsets = spool.list_backupsets() or ['']
        padding = max([len(name) for name in backupsets]) + 1
        self.stdout("%36s %*s %10s %5s",
                    "Created", padding, "Backupset", "Size", "Path")
        self.stdout("%36s %s %10s %s", "-"*36, "-"*padding, "-"*10, "-"*5)
        for backup in spool:
            self.stdout("<Created %s> %*s %10s %s",
                        format_datetime(backup.timestamp), padding, backup.name,
                        "[%s]" % format_bytes(backup.size()), backup.path)
        return 0

    def plugin_info(self):
        return dict(
            name=self.name,
            summary=self.summary,
            description=self.description,
            author='Rackspace',
            version='1.1.0',
            holland_version='1.1.0'
        )
