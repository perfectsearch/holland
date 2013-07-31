"""
holland.mysql.mysqldump.plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

myqldump backup plugin implementation

"""

import os
from os.path import join
import time
import logging
import contextlib
from tempfile import TemporaryFile
from subprocess import check_call, CalledProcessError
from holland.core.backup.plugin import BackupPlugin
from holland.core.stream import load_stream_plugin
from holland.core.util import format_interval, format_bytes, relpath
from holland.mysql.schema import InformationSchema
from holland.mysql.client import MySQL, generate_defaults_file
from . import util, filters, views, strategy

LOG = logging.getLogger(__name__)

class MySQLDumpBackupPlugin(BackupPlugin):
    name = 'mysqldump'
    summary = 'mysqldump backups'

    def setup(self):
        self.defaults_file = join(self.backup_directory, 'holland-mysqldump.cnf')
        client_cfg = self.config['mysql:client']
        include_paths = client_cfg.defaults_file
        generate_defaults_file(self.defaults_file, include_paths, **client_cfg)
        LOG.info("Generated defaults file: %s", self.defaults_file)
        for name in include_paths:
            LOG.info("Added !include %s to defaults", os.path.expanduser(name))
        self.mysql = MySQL.from_defaults(self.defaults_file)
        self.ischema = InformationSchema(self.mysql)
        LOG.info("Applying schema filters")
        database_exclusions = self.config.mysqldump.exclude_databases
        if 'information_schema' not in database_exclusions:
            LOG.info("Adding database exclusion for information_schema")
            database_exclusions.append('information_schema')
        if 'performance_schema' not in database_exclusions:
            LOG.info("Adding database exclusion for performance_schema")
            database_exclusions.append('performance_schema')
        filters.apply_filters(self.ischema, self.config.mysqldump)

    def estimate(self):
        total_size = 0
        try:
            for schema in self.ischema.databases():
                schema_size = self.ischema.data_size(schema)
                total_size += schema_size
                LOG.info("Estimated size for `%s`: %s", schema, format_bytes(schema_size))
        except self.mysql.DatabaseError, exc:
            LOG.error("MySQL error during estimation: [%d] %s", *exc.args)
            self.fail("MySQL error during estimation: [%d] %s" %
                       exc.args)
        return total_size

    @contextlib.contextmanager
    def mysqldump_context(self):
        config = self.config.mysqldump
        managers = []
        if config.stop_slave:
            managers.append(self.mysql.pause_replication())
        #if config.read-lock-during-dump:
        #    managers.append(self.mysql.lock_instance)

        with contextlib.nested(*managers):
            #record_replication(self.backup_directory,
            #                   slave_status=self.mysql.show_slave_status(),
            #                   master_status=elf.mysql.show_master_status())
            yield

    def dryrun(self):
        LOG.info("Dry-run for 'mysqldump'")
        config = self.config.mysqldump
        bin_mysqldump = util.which_mysqldump(config.mysql_binpath)
        mysqldump_version = util.mysqldump_version(bin_mysqldump)
        if config.exclude_invalid_views:
            LOG.info("Would check for invalid views")
        util.generate_mysqldump_options(self.defaults_file, config, mysqldump_version)
        compression = load_stream_plugin(self.config.compression)
        LOG.info("Compression method '%s'", compression.name)
        if config.file_per_database:
            LOG.info("file-per-database enabled. Forcing mysqldump-strategy=file-per-database")
            config.mysqldump_strategy = 'file-per-database'
        LOG.info("mysqldump-strategy: %s", config.mysqldump_strategy)
        s = strategy.load_strategy(config.mysqldump_strategy)
        mysqldump_cmd = strategy.mysqldump(bin_mysqldump,
                                           self.defaults_file,
                                           config.additional_options)
        if config.stop_slave:
            LOG.info("Would pause replication via STOP SLAVE SQL_THREAD")
        for basename, cmdline in s(mysqldump_cmd, self.ischema, config):
            if compression.ext:
                basename += compression.ext
            LOG.info("$ %s", ' '.join(cmdline))
            LOG.info("  > backup_data/%s", basename)
        if config.stop_slave:
            LOG.info("Would resume replication via START SLAVE SQL_THREAD")

    def backup(self):
        config = self.config.mysqldump
        defaults_file = self.defaults_file
        bin_mysqldump = util.which_mysqldump(config.mysql_binpath)
        mysqldump_version = util.mysqldump_version(bin_mysqldump)
        util.check_version(mysqldump_version, server_version=self.mysql.version)
        backup_datadir = join(self.backup_directory, 'backup_data')
        try:
            os.makedirs(backup_datadir)
        except OSError, exc:
            if exc.errno != errno.EEXIST:
                self.fail("Unable to create %s: [%d] %s" % (
                            backup_datadir,
                            exc.errno,
                            exc.strerror))

        util.generate_mysqldump_options(defaults_file, config, mysqldump_version)
        util.generate_table_exclusions(defaults_file, self.ischema)
        if config.exclude_invalid_views:
            invalid_views_path = join(backup_datadir, 'invalid_views.sql')
            views.dump_and_exclude_invalid_views(invalid_views_path,
                                                 defaults_file,
                                                 self.ischema)

        compression = load_stream_plugin(self.config.compression)

        if config.file_per_database:
            LOG.info("file-per-database enabled. Forcing mysqldump-strategy=file-per-database")
            config.mysqldump_strategy = 'file-per-database'
        LOG.info("mysqldump-strategy: %s", config.mysqldump_strategy)
        s = strategy.load_strategy(config.mysqldump_strategy)
        mysqldump_cmd = strategy.mysqldump(bin_mysqldump,
                                           defaults_file,
                                           config.additional_options)
        # handle any stop/start slave or other global
        # contextual behavior under which we will run the backup
        with self.mysqldump_context():
            for basename, cmdline in s(mysqldump_cmd, self.ischema, config):
                path = join(self.backup_directory, 'backup_data', basename)
                if not os.path.exists(os.path.dirname(path)):
                    os.makedirs(os.path.dirname(path))
                with compression.open(path, 'wb') as stdout:
                    with TemporaryFile(prefix='mysqldump') as stderr:
                        # XXX: list2cmdline or sarge.shell_quote
                        # may be more accurate here
                        LOG.info("$ %s ", ' '.join(cmdline))
                        LOG.info(" > %s", relpath(stdout.name,
                                                  self.backup_directory))
                        start_time = time.time()
                        try:
                            check_call(cmdline,
                                       stdout=stdout,
                                       stderr=stderr,
                                       close_fds=True)
                            LOG.info("%s dumped in %s",
                                     relpath(stdout.name,
                                             self.backup_directory),
                                     format_interval(time.time() - start_time))
                        except OSError, exc:
                            LOG.info("[%d] %s", exc.errno, exc.strerror)
                            self.fail("Failed to run mysqldump [%d] %s" %
                                    (exc.errno, exc.strerror))
                        except CalledProcessError, exc:
                            stderr.seek(0)
                            stderr.flush()
                            for line in stderr:
                                LOG.error("mysqldump: %s", line.rstrip())
                            LOG.info("mysqldump failed with status [%d]",
                                     exc.returncode)
                            self.fail("mysqldump failed with status [%d]" %
                                      exc.returncode)
