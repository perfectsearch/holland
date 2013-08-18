"""
holland.mysql.path
~~~~~~~~~~~~~~~~

Path utility functions for inspect MySQL files

"""
import os
import logging
from os.path import isabs, join, realpath, abspath, splitext, normpath
from collections import namedtuple

_InnoDBDatafileSpec = namedtuple('InnoDBDatafileSpec',
                                 'name size autoextend max')

class InnoDBDatafileSpec(_InnoDBDatafileSpec):
    @classmethod
    def from_string(cls, value):
        parts = value.split(':')
        # ensure we set any remaining fields to None, if not specified
        parts += [None] * (len(cls._fields) - len(parts))
        kwargs = dict(zip(cls._fields, parts))
        return cls(**kwargs)

    def __str__(self):
        return ':'.join(filter(None, self))


_AbstractMySQLPathInfo = namedtuple('MySQLPathInfo',
                                    ('datadir '
                                     'innodb_log_group_home_dir '
                                     'innodb_log_files_in_group '
                                     'innodb_data_home_dir '
                                     'innodb_data_file_path '
                                     'abs_tablespace_paths')
                                    )

LOG = logging.getLogger(__name__)

class MySQLPathInfo(_AbstractMySQLPathInfo):
    """Named tuple whose attributes describe the important
    file paths for the files in a MySQL instance.
    """

    @classmethod
    def from_mysql(cls, mysql):
        """Create a MySQLPathInfo instance from a live MySQL connection"""
        var = mysql.var
        ibd_homedir = var('innodb_data_home_dir')
        if ibd_homedir == '':
            try:
                sql = 'SELECT @@global.innodb_data_home_dir'
                abs_tablespace_paths = bool(mysql.execute(sql).scalar())
            except mysql.DatabaseError as exc:
                # either mysql 5.0 or we had a connection failure
                # here we will just assume 'yes'
                abs_tablespace_paths = True
        else:
            abs_tablespace_paths = True
        return cls(
            datadir=os.path.realpath(var('datadir')),
            innodb_log_group_home_dir=var('innodb_log_group_home_dir'),
            innodb_log_files_in_group=int(var('innodb_log_files_in_group')),
            innodb_data_home_dir=ibd_homedir,
            innodb_data_file_path=var('innodb_data_file_path'),
            abs_tablespace_paths=abs_tablespace_paths
        )

    def get_innodb_logdir(self):
        """Determine the directory for innodb's log files"""
        if isabs(self.innodb_log_group_home_dir):
            logdir = self.innodb_log_group_home_dir
        else:
            logdir = join(self.datadir, self.innodb_log_group_home_dir)

        return abspath(realpath(logdir))

    def get_innodb_datadir(self):
        """Determine the base directory for innodb shared tablespaces"""
        ibd_home_dir = self.innodb_data_home_dir or ''
        if not ibd_home_dir or not isabs(ibd_home_dir):
            ibd_home_dir = join(self.datadir, ibd_home_dir)

        return abspath(realpath(ibd_home_dir))

    def walk_innodb_data_file_path(self):
        for datafile_spec in self.innodb_data_file_path.split(';'):
            yield InnoDBDatafileSpec.from_string(datafile_spec)

    def walk_innodb_shared_tablespaces(self):
        """Iterate over InnoDB shared tablespace paths"""
        ibd_homedir = self.get_innodb_datadir()
        ibd_data_file_path = self.innodb_data_file_path

        for spec in self.walk_innodb_data_file_path():
            yield normpath(realpath(join(ibd_homedir, spec.name)))

    def walk_innodb_logs(self):
        """Iterate over InnoDB redo log paths"""
        basedir = self.get_innodb_logdir()
        for logid in xrange(self.innodb_log_files_in_group):
            yield join(basedir, 'ib_logfile' + str(logid))

    def relative_to_datadir(self):
        # we assume all files in datadir are relative to datadir :P
        if relpath(get_innodb_logdir(), datadir).startswith(os.pardir):
            return False
        if relpath(get_innodb_datadir(), datadir).startswith(os.pardir):
            return False
        for path in walk_innodb_shared_tablespaces():
            if not os.path.isabs(path):
                continue
            if relpath(path, datadir).startswith(os.pardir):
                return False

        for path in self.walk_mysql_datadir():
            # this follows symlinks to see if anything is outside the datadir
            if relpath(path, datadir).startswith(os.pardir):
                return False

    @staticmethod
    def is_mysql_datafile(path):
        """Determine if a given filename looks like a MySQL datafile"""
        save_files = [
            'mysql_upgrade_info',
            'auto.cnf', # mysql 5.6
        ]
        # save a few metadata files
        if os.path.basename(path) in save_files:
            return True
        suffixes = [
                    '.frm',
                    '.MYD', '.MYI', '.MRG', # MyISAM
                    '.ibd', '.isl', '.cfg', # InnoDB
                    '.TRG', '.TRN', # Triggers
                    '.ARM', '.ARZ', # Archive engine
                    '.CSM', '.CSV', # CSV engine
                    '.opt', # DB option files
                    '.par', # partionining metadata
                   ]
        _, ext = splitext(path)
        return ext in suffixes

    def walk_mysql_datadir(self, dbdir_only=False):
        """Iterate over the data files in a MySQL datadir"""
        LOG.info("Walking mysql datadir %s", self.datadir)
        for dirpath, _, filenames in os.walk(self.datadir, followlinks=True):
            for filepath in filenames:
                if self.is_mysql_datafile(filepath):
                    if dbdir_only:
                        yield dirpath
                        break
                    else:
                        yield join(dirpath, filepath)
                        if filepath.endswith('.isl'):
                            # isl files are links to actual innodb locations
                            yield contents(join(dirpath, filepath))
                else:
                    LOG.info("Skipping: %s", filepath)
