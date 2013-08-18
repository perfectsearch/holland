"""
holland.cli.main
~~~~~~~~~~~~~~~~~~~

Main holland cli script

:copyright: 2008-2011 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import logging
import os
import signal
import traceback

from holland import version
from holland.cli import util
from holland.cli.cmd import interface
from holland.cli.cmd import exc

HOLLAND_BANNER = """
Holland Backup v%s
Copyright (c) 2008-2011 Rackspace US, Inc.
More info available at http://hollandbackup.org

[[[[[[[]]]]]]] [[[[[[[]]]]]]]
[[[[[[[]]]]]]]       [[[[[[[]]]]]]]
[[[[[[[]]]]]]] [[[[[[[]]]]]]]
[[[[[[[]]]]]]] [[[[[[[]]]]]]]

""" % version.__version__

LOG = logging.getLogger(__name__)

util.configure_warnings()
util.configure_basic_logger()

argument = interface.argument

def terminate(signum, frame):
    """Terminate from SIGTERM cleanly"""
    LOG.debug("terminate(signum=%r, frame=%r)", signum, frame)
    raise SystemExit("Caught SIGTERM")

class HollandCli(interface.ArgparseCommand):
    """Main holland command interface"""

    name = 'holland'

    summary = 'Holland command line'

    description = HOLLAND_BANNER

    arguments = [
        argument('--config', '-c', metavar='<file>',
                 default=os.environ.get('HOLLAND_CONFIG',
                                        '/etc/holland/holland.conf'),
                 help='Read configuration from the given file'),
        argument('--log-level', '-l', metavar='<log-level>',
                    choices=('debug', 'info', 'warning', 'error', 'fatal'),
                    help="Specify the log level."),
        argument('--debug', '-d', action='store_const',
                 dest='log_level', const='debug',
                 help='Log debug output (alias for --log-level=debug)'),
        argument('--verbose', '-v', action='store_const',
                 dest='log_level', const='info',
                 help='Log verbose output (alias for --log-level=info)'),
        argument('--quiet', '-q', action='store_true',
                 help="Disable all console output."),
        argument('subcommand', nargs='?'),
        argument('args', nargs='...'),
    ]

    def __init__(self, name):
        interface.ArgparseCommand.__init__(self, name)
        self.configure(None)

    def execute(self, opts, parser):
        """Execute the main holland command

        This will load the global config if it exists and
        dispatch to a subcommand if one is specified.

        If not subcommand is given this defaults to 'list-commands'
        and only prints the available commands.
        """
        try:
            config = util.load_global_config(opts.config)
        except (IOError, ValueError) as exc:
            self.stderr("Failed to load config file %s: %s", opts.config, exc)
            return 1

        if opts.log_level:
            level_names = logging._levelNames
            level_name = opts.log_level.upper()
            try:
                config['logging']['level'] = level_names[level_name]
            except KeyError:
                self.stderr("Invalid --log-level '%s'", opts.log_level)
        if config['holland']['umask'] is not None:
            os.umask(config['holland']['umask'])
        if config['holland']['tmpdir']:
            os.environ['TMPDIR'] = config['holland']['tmpdir']
        if config['holland']['path']:
            os.environ['PATH'] = config['holland']['path']
        util.configure_logging(config['logging'], quiet=opts.quiet)
        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGQUIT, terminate)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

        if not opts.subcommand:
            parser.print_help()
            opts.subcommand = 'list-commands'

        self.configure(config)
        try:
            return self.chain(opts.subcommand, opts.args)
        except KeyboardInterrupt:
            self.stderr("Interrupted")
        except SystemExit:
            self.stderr("Terminated")
        except interface.CommandNotFoundError as exc:
            self.stderr("'%s' is not a valid holland command. "
                        "See holland help for valid commands.", exc.name)
        except: # unexpected command failure
            self.stderr('Unexpected exception while running command "%s"',
                        opts.subcommand)
            traceback.print_exc()
        return 1

holland = HollandCli('holland')
