"""
holland.mysql.mysqldump.strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Strategies for executing mysqldump

This module provides an interface for
loading a strategy, where a strategy
is some method to generate one or
more mysqldump commandlines.

Specifically this module currently provides
three (3) strategies:

    1) A single mysqldump of all databases
    2) A separate mysqldump of each database
    3) A separate mysqldump of each table
       and a separate mysqldump per database for
       routines and events
"""
import logging
from os.path import join
from functools import wraps
from . import filters

LOG = logging.getLogger(__name__)

def mysqldump(bin_mysqldump='mysqldump',
              defaults_file=None,
              additional_options=()):
    @wraps(mysqldump)
    def wrapper(*args):
        argv = [
            bin_mysqldump,
        ]
        if defaults_file:
            argv.append('--defaults-file=' + defaults_file)
        argv.extend(args)
        argv.extend(additional_options)
        return argv
    return wrapper

def lock_options(schema, databases, config):
    if config.lock_method == 'single-transaction':
        return ['--single-transaction']
    elif config.lock_method == 'lock-tables':
        return ['--lock-tables']
    elif config.lock_method == 'flush-lock':
        return ['--lock-all-tables']
    elif config.lock_method == 'none':
        return ['--skip-lock-tables']
    elif config.lock_method == 'auto-detect':
        LOG.info("lock-method = auto-detect - determining lock option to use")
        for name in databases:
            # ignore system databases
            if name in ('mysql', 'information_schema', 'performance_schema'):
                continue
            # if at least one table is non-transactional
            tables = schema.transactional_database(name)
            if tables:
                LOG.info("%d non-transactional tables detected", len(tables))
                for tbl, engine in tables:
                    LOG.info("%s.%s engine=%s", name, tbl, engine)
                LOG.info("Using --lock-tables")
                return ['--lock-tables']
        LOG.info("Using --single-transaction")
        return ['--single-transaction']
    else:
        return []

def mysqldump_all_databases(mysqldump, schema, config):
    databases = schema.databases()
    all_databases = set(schema.all_databases())
    default_exclusions = set(['information_schema', 'performance_schema'])
    if not (all_databases - set(databases)) - default_exclusions:
        args = ('--all-databases',)
    else:
        args = tuple(['--databases'] + databases)

    lock_opts = lock_options(schema, databases, config)
    yield 'all_databases.sql', mysqldump(*args + tuple(lock_opts))

def mysqldump_per_database(mysqldump, schema, config):
    databases = schema.databases()
    for name in schema.databases():
        try:
            lock_opts = lock_options(schema, [name], config)
        except:
            raise
        try:
            yield name + '.sql', mysqldump(*lock_opts + [name])
        except:
            raise

def mysqldump_per_table(mysqldump, schema, config):
    for schema_name in schema.databases():
        yield (join(schema_name, 'routines.ddl'),
               mysqldump('--no-data',
                         '--no-create-info',
                         '--skip-triggers',
                         '--routines',
                         schema_name))
        yield (join(schema_name, 'events.ddl'),
               mysqldump('--no-data',
                         '--no-create-info',
                         '--skip-triggers',
                         '--events',
                         schema_name))
        for table_schema, table_name in schema.tables(schema_name):
            options = ['--skip-lock-tables']
            if (table_schema, table_name) == ('mysql', 'event'):
                options.append('--events')
            if (table_schema, table_name) == ('mysql', 'general_log'):
                options.extend(['--no-data'])
            if (table_schema, table_name) == ('mysql', 'slow_log'):
                options.extend(['--no-data'])
            options.extend([schema_name, table_name])
            yield (join(table_schema, table_name) + '.sql',
                   mysqldump(*options))

def load_strategy(name):
    if name == 'all-databases':
        return mysqldump_all_databases
    elif name == 'file-per-database':
        return mysqldump_per_database
    elif name == 'file-per-table':
        return mysqldump_per_table
    else:
        raise BackupError("Invalid mysqldump strategy '%s'" % name)
