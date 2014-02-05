"""
holland.mysql.lvm.plugin
~~~~~~~~~~~~~~~~~~~~~~~~

mysql-lvm plugin implementation

"""

import os
import time
import errno
import logging
from contextlib import contextmanager
from holland.core.util.path import getmount, relpath, directory_size
from holland.core.util.fmt import format_interval
from holland.lvm.plugin import LVMSnapshot
from holland.mysql.client import MySQL, MySQLFlushLock, generate_defaults_file
from holland.mysql.server import MySQLServer
from holland.mysql.lvm import util

LOG = logging.getLogger(__name__)

class MyLVMSnapshot(LVMSnapshot):
    name = 'mylvmsnapshot'
    aliases = tuple(['mysql-lvm'])
    summary = 'archive MySQL datadir from an LVM snapshot'

    #: mysql client handle
    #: maintained for lifecycle of plugin
    mysql = None

    master_status = None
    slave_status = None

    def load_volume(self):
        try:
            self.lvm_config.target_path = self.mysql.var('datadir')
        except self.mysql.DatabaseError as exc:
            self.fail("Error discovering datadir: [%d] %s" % exc.orig.args)
        LOG.info("Set target-path to datadir: %s",
                 self.lvm_config.target_path)
        return super(MyLVMSnapshot, self).load_volume()

    @property
    def lvm_config(self):
        return self.config['mysql-lvm']

    def estimate(self):
        try:
            datadir = self.mysql.var('datadir')
            return directory_size(self.mysql.var('datadir'))
        except OSError as exc:
            self.fail("Error calculating size of '%s': [%d] %s" %
                      (datadir, exc.errno, exc.strerror))
        except self.mysql.DatabaseError as exc:
            self.fail("Error discovering datadir: [%d] %s" % exc.orig.args)

    def setup(self):
        defaults_file = os.path.join(self.backup_directory,
                                     'holland-mysql-lvm.cnf')
        mysql_cfg  = self.config['mysql:client']
        generate_defaults_file(defaults_file,
                               include=mysql_cfg.defaults_file,
                               **mysql_cfg)
        LOG.info("Generated MySQL defaults file: %s", defaults_file)
        self.mysql = MySQL.from_defaults(defaults_file)


    @contextmanager
    def create_snapshot(self, volume):
        preflush_tables = self.lvm_config.extra_flush_tables
        lock_tables = self.lvm_config.lock_tables
        with MySQLFlushLock(self.mysql,
                            preflush_tables=preflush_tables,
                            lock_tables=lock_tables) as lock:
            start_time = time.time()
            LOG.info("Acquiring replication info")
            if self.lvm_config.flush_logs:
                LOG.info("Executing FLUSH /*!50503 BINARY */LOGS")
                self.mysql.execute('FLUSH /*!50503 BINARY */LOGS')
            self.master_status = self.mysql.master_status()
            if self.master_status:
                LOG.info("Recorded master info: file = '%s' position = %d",
                         self.master_status.file, self.master_status.position)
            self.slave_status = self.mysql.slave_status()
            if self.slave_status:
                LOG.info("Record slave info: file = '%s' position = %d",
                         self.slave_status.relay_master_log_file,
                         self.slave_status.exec_master_log_pos)
            LOG.info("Replication info collected in %s",
                    format_interval(time.time() - start_time))
            with super(MyLVMSnapshot, self).create_snapshot(volume) as snapshot:
                # release the lock early
                lock.unlock()
                # write out the information we obtained
                util.write_slave_status(self.backup_directory, self.slave_status)
                util.write_master_status(self.backup_directory, self.master_status)
                # legacy: save master/slave status to [mysql:replication] section
                # in global "backup.conf"
                util.update_config_slave_status(self.config, self.slave_status)
                util.update_config_master_status(self.config, self.master_status)
                yield snapshot

    def archive(self, mountpoint):
        mysql = self.mysql
        if self.lvm_config.innodb_recovery:
            options = util.remap_options(mysql, mountpoint)
            options['engines'] = self.mysql.show_engines()
            # Twiddle some options specific for innodb recovery
            # disable the binary log for innodb recovery
            options['log_bin'] = False
            # set a user (this needs to be configurable)
            options['user'] = 'mysql'
            options['skip_slave_start'] = True
            options['bootstrap'] = True
            options['innodb_buffer_pool_size'] = self.config.mysqld.innodb_buffer_pool_size
            #options['log_error'] = normpath(join(options['datadir'],
            #                                     'holland-backup-error.log'))
            # remove master.info to avoid replication accidentally starting
            options['log_error'] = None
            try:
                os.unlink(os.path.join(options['datadir'], 'master.info'))
            except OSError as exc:
                if exc.errno != errno.ENOENT:
                    raise

            mysqld = util.find_mysqld(self.config.mysqld.mysqld_exe)
            LOG.info("Using mysqld binary '%s'", mysqld)

            with MySQLServer(options, mysqld=mysqld) as server:
                LOG.info("Running innodb-recovery")
            with open(server.error_log, 'rb') as fileobj:
                LOG.info("Reading entries from error log: %s",
                         server.error_log)
                LOG.debug("stat %s : %r", fileobj.name, os.stat(fileobj.name))
                for line in fileobj:
                    LOG.info("mysqld: %s", line.rstrip())
        rpaths = set(util.discover_mysql_datafiles(mysql, mountpoint))
        basedir = os.path.join(mountpoint, util.commonpath(rpaths))
        self.lvm_config.relative_paths.clear()
        for path in rpaths:
            cpath = os.path.join(mountpoint, path)
            rpath = relpath(cpath, basedir)
            self.lvm_config.relative_paths.add(rpath)
        LOG.info("Relative paths: %s", ','.join(self.lvm_config.relative_paths))
        # close any outstanding pooled connections before we archive
        self.mysql.dispose()
        super(MyLVMSnapshot, self).archive(basedir)
