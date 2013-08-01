"""
holland.mysql.lvm.mylvmdump.plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

mylvmdump backup strategy plugin for holland

This backup strategy leverage the mylvmsnapshot plugin
but overrides the archiving method to perform a logical
backup rather than a physical backup of the mysql datafiles.

Specifically this plugin starts a secondary mysqld instance
that runs off the of the snapshot filesystem.  A unix socket
path is exposed under the snapshot datadir for mysqldump to
connect to. mylvmdump then loads the holland mysqldump backup
strategy to generate the logical backup.

Some quirks here:

    * Presently we only support running through a local socket
    * There is the assumption that we have $backup_user@localhost
      permissions to run mysqldump.
    * Unlike mysqldump, we default to lock-method = none, which
      uses --skip-lock-tables.  This is effectively an 'at-rest'
      instance of mysql that no one else but holland should be
      connected to, so many of the locking problems of mysqldump
      can be relaxed significantly.

"""
import os
import logging

from holland.core.backup.plugin import load_backup_plugin
from holland.mysql.server import MySQLServer
from holland.mysql.lvm import util
from holland.mysql.lvm.plugin import MyLVMSnapshot
from holland.mysql.lvm.mylvmdump.util import prepare_binlogs
from holland.mysql.lvm.mylvmdump.util import path_owner

LOG = logging.getLogger(__name__)

class MyLVMDump(MyLVMSnapshot):
    summary = 'mysqldump backups using an LVM snapshot'
    aliases = tuple(['mysqldump-lvm'])

    def __init__(self, name):
        super(MyLVMDump, self).__init__(name)
        self.name = 'mylvmdump'
        self.backup_plugin = load_backup_plugin('mysqldump')

    def setup(self):
        super(MyLVMDump, self).setup()
        if self.config.mysql_lvm.synchronize_binlogs:
            if not self.config.mysql_lvm.flush_logs:
                self.config.mysql_lvm.flush_logs = True
                LOG.info("Enabled flush-logs for synchronize-binlogs")
            if not self.config.mysql_lvm.lock_tables:
                self.config.mysql_lvm.lock_tables = True
                LOG.info("Enabled lock-tables for synchronize-binlogs")

    def archive(self, mountpoint):
        LOG.info("Remapping mysqld options against mountpoint '%s'",
                 mountpoint)
        options = util.remap_options(self.mysql, mountpoint)
        mysql_user = path_owner(options['datadir'])
        if mysql_user:
            options['user'] = mysql_user
        # Ensure we don't bootstrap - mysqldump must connect to this instance
        options['bootstrap'] = False
        # if replication is configured, ensure we don't start the slave
        options['skip_slave_start'] = True

        if self.master_status:
            if self.config.mysql_lvm.synchronize_binlogs:
                prepare_binlogs(options['datadir'], self.master_status.file)
                options['binlog_basename'] = os.path.splitext(self.master_status.file)[0]
            else:
                options['binlog_basename'] = None

        mysqld = util.find_mysqld(self.config.mysqld.mysqld_exe)
        LOG.info("Using mysqld binary '%s'", mysqld)
        with MySQLServer(options, mysqld=mysqld) as server:
            config = self.config.copy()
            config['mysql:client']['socket'] = server.socket
            if self.master_status:
                if self.config.mysql_lvm.synchronize_binlogs:
                    config['mysqldump']['bin-log-position'] = True
                    LOG.info("Enabling mysqldump --master-data")
                if config.mysqldump.flush_logs:
                    config['mysqldump']['flush-logs'] = False
                    LOG.info("Disabled mysqldump --flush-logs")

            LOG.info("Using mysqldump socket '%s'", server.socket)
            context = self.context._replace(config=config)
            LOG.debug("Duplicated mylvmdump context")
            self.backup_plugin.bind(context)
            LOG.debug("Bound context to mysqldump plugin")
            self.backup_plugin.setup()
            LOG.debug("Executed mysqldump plugin setup")
            try:
                self.backup_plugin.backup()
            finally:
                self.backup_plugin.cleanup()

    def dryrun(self):
        super(MyLVMDump, self).dryrun()
        mysqldump_plugin = load_backup_plugin('mysqldump')
        mysqldump_plugin.bind(self.context)
        mysqldump_plugin.setup()
        mysqldump_plugin.dryrun()
        del mysqldump_plugin

    def configspec(self):
        configspec = super(MyLVMDump, self).configspec()
        configspec.meld(self.backup_plugin.configspec())
        return configspec
