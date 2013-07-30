"""
holland.cli.util
~~~~~~~~~~~~~~~

Utility functions for holland cli

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import logging
import os
import pkgutil
import sys
import warnings

from holland import core

DEFAULT_LOG_FORMAT = '%(asctime)s %(levelname)-8s: %(message)s'
DEFAULT_LOG_LEVEL = logging.INFO

LOG = logging.getLogger(__name__)

class GlobalHollandConfig(core.Config):
    """Config for the global holland.conf

    This object is passed to each subcommand holland runs via that
    commands configure() method. This provides access to global
    config options and loading other configs relative to the root
    holland.conf's directory
    """

    def basedir(self):
        """Find the base directory where this holland.conf lives"""
        return os.path.abspath(os.path.dirname(self.path or '.'))

    def load_backupset(self, name):
        """Load a backupset relative to this holland.conf instance"""
        if not os.path.isabs(name):
            name = os.path.join(self.basedir(), 'backupsets', name)

        if not os.path.isdir(name) and not name.endswith('.conf'):
            name += '.conf'

        cfg = Config.read([name])

        # load providers/$plugin.conf if available
        plugin = cfg.get('holland:backup', {}).get('plugin')
        if plugin:
            provider_path = os.path.join(self.basedir(),
                                         'providers',
                                         plugin + '.conf')
            try:
                cfg.meld(Config.read([provider_path]))
            except core.ConfigError:
                LOG.debug("No global provider found.  Skipping.")
        cfg.name = os.path.splitext(os.path.basename(name))[0]
        return cfg

    @classmethod
    def configspec(cls):
        """Retrieve the configspec from this class"""
        pkg = __name__.rpartition('.')[0]
        data = pkgutil.get_data(pkg, 'holland-cli.configspec')
        return core.Configspec.from_string(data)

def load_global_config(path):
    """Conditionally load the global holland.conf

    If the requested path does not exist a default
    GlobalHollandConfig instance will be returned
    """
    if path:
        try:
            cfg = GlobalHollandConfig.read([path])
            cfg.name = path
        except core.ConfigError, exc:
            LOG.error("Failed to read %s: %s", path, exc)
            cfg = GlobalHollandConfig()
    else:
        cfg = GlobalHollandConfig()

    GlobalHollandConfig.configspec().validate(cfg)
    return cfg

def _clear_root_handlers():
    """Remove all pre-existing handlers on the root logger"""
    root = logging.getLogger()
    for handler in root.handlers:
        root.removeHandler(handler)

def configure_basic_logger():
    """Configure a simple console logger"""
    root = logging.getLogger()

    if not os.isatty(sys.stderr.fileno()):
        class NullHandler(logging.Handler):
            """No-op log handler"""
            def emit(self, something):
                """Null emitter"""
                pass
        handler = NullHandler()
    else:
        handler = logging.StreamHandler()

    configure_logger(logger=root,
                     handler=handler,
                     fmt='%(message)s',
                     level=logging.INFO)

def configure_logger(logger, handler, fmt, level):
    """Configure a new logger"""
    formatter = logging.Formatter(fmt)
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)

def log_warning(message, category, filename, lineno, _file=None, _line=None):
    """Log a warning message.

    This currently only logs DeprecationWarnings at debug level and otherwise
    only logs the message at 'info' level.  The formatted warning can be
    seen by enabling debug level logging.
    """
    log = logging.getLogger()
    args = [x for x in (_line,)]
    warning_string = warnings.formatwarning(message,
                                            category,
                                            filename,
                                            lineno, *args)
    if category == DeprecationWarning:
        log.debug("(%s) %s", _file, warning_string)
    else:
        log.debug(warning_string)

def configure_warnings():
    """Ensure warnings go through log_warning"""
    # Monkey patch in routing warnings through logging
    warnings.showwarning = log_warning


def configure_logging(config, quiet=False):
    """Configure CLI logging based on config

    config must be a dict-like object that has 3 paramters:
    * level - the log level
    * format - the log output format
    * filename - what file to log to (if any)
    """
    # Initially holland adds a simple console logger
    # This removes that to configure a new logger with
    # a message format potentially defined by the configuration
    # as well as adding additional file loggers
    _clear_root_handlers()

    if not quiet and os.isatty(sys.stderr.fileno()):
        configure_logger(logger=logging.getLogger(),
                         handler=logging.StreamHandler(),
                         fmt=DEFAULT_LOG_FORMAT,
                         level=config['level'])
    try:
        configure_logger(logger=logging.getLogger(),
                         handler=logging.FileHandler(config['filename'],
                                                     encoding='utf8'),
                         fmt=config['format'],
                         level=config['level'])
    except IOError, exc:
        LOG.info("Failed to open log file: %s", exc)
        LOG.info("Skipping file logging.")

    configure_warnings()
