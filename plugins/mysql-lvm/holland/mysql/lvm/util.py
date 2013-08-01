"""
holland.mysql.lvm.util
~~~~~~~~~~~~~~~~~~~~~~

Utility methods

"""

import os
import logging
from os.path import join, normpath, isabs
from itertools import takewhile
from holland.core.util.path import relpath, getmount, which
from holland.mysql.pathinfo import MySQLPathInfo
from holland.mysql.util import format_binlog_info

LOG = logging.getLogger(__name__)

def allnamesequal(name):
    return all(n==name[0] for n in name[1:])

def commonpath(paths, sep=os.sep):
    bydirectorylevels = zip(*[p.split(sep) for p in paths])
    return sep.join(x[0] for x in takewhile(allnamesequal, bydirectorylevels))

def remap_path(path, basedir):
    """Remap a path against a new basedir

    This method calculates the relative path of path against it's mountpoint
    and determines the absolute path relative to a new mountpoint.

    This is a utility method for snapshot based backups where we must backup
    some set of resources from a new mountpoint.
    """
    return join(basedir, relpath(path, getmount(path)))


def remap_options(mysql, basedir):
    """Remap MySQL path options relative to a new mountpoint"""
    # dump global variables from mysql
    paths = dict(mysql.variables_like("%"))
    pathinfo = MySQLPathInfo.from_mysql(mysql)
    mountpoint = basedir
    paths['datadir'] = remap_path(pathinfo.datadir, mountpoint)
    LOG.info("Remapped datadir '%s' to '%s'",
             pathinfo.datadir, paths['datadir'])

    if pathinfo.abs_tablespace_paths:
        # need to remap innodb_data_file_path, potentially
        ib_specs = []
        for spec in pathinfo.walk_innodb_data_file_path():
            if isabs(spec.name):
                old_spec = spec
                spec = spec._replace(name=remap_path(spec.name, mountpoint))
                LOG.info("Remapped %s to %s", old_spec.name, spec.name)
            ib_specs.append(spec)
        paths['innodb_data_file_path'] = ';'.join(map(str, ib_specs))
    else:
        paths['innodb_data_file_path'] = pathinfo.innodb_data_file_path
        LOG.debug("Not remapping relative innodb-data-file-path")

    if pathinfo.innodb_data_home_dir:
        paths['innodb_data_home_dir'] = remap_path(pathinfo.get_innodb_datadir(), mountpoint)
        LOG.info("Remapped innodb-data-home-dir = %s to %s",
                pathinfo.innodb_data_home_dir, paths['innodb_data_home_dir'])
    else:
        LOG.debug("Not remapping empty innodb-data-home-dir")


    if pathinfo.innodb_log_group_home_dir != './':
        ib_logdir = normpath(join(pathinfo.datadir,
                             pathinfo.innodb_log_group_home_dir))
        paths['innodb_log_group_home_dir'] = remap_path(ib_logdir, mountpoint)
        LOG.info("Remapped innodb-log-group-home-dir = %s to %s",
                pathinfo.innodb_log_group_home_dir,
                paths['innodb_log_group_home_dir'])
    else:
        LOG.debug("Not remapping innodb-log-group-home-dir = ./")
    paths['user'] = 'mysql'
    return paths

def discover_mysql_datafiles(mysql, mountpoint):
    """Discover MySQL data files relative to a new mountpoint"""
    pathinfo = MySQLPathInfo.from_mysql(mysql)
    yield relpath(pathinfo.datadir, getmount(pathinfo.datadir))
    yield relpath(pathinfo.get_innodb_logdir(),
                  getmount(pathinfo.get_innodb_logdir()))
    yield relpath(pathinfo.get_innodb_datadir(),
                  getmount(pathinfo.get_innodb_datadir()))


def find_mysqld(candidates):
    for name in candidates:
        try:
            return which(name)
        except OSError, exc:
            continue
    else:
        raise HollandError("Failed to find suitable mysqld process")

def write_slave_status(path, status):
    if not status:
        return
    info = format_binlog_info(filename=status.relay_master_log_file,
                              position=status.exec_master_log_pos,
                              source='SHOW SLAVE STATUS')
    with open(os.path.join(path, 'holland_slave_info'), 'wb') as fileobj:
        print >>fileobj, info
        LOG.info("Wrote slave status info to '%s'", fileobj.name)

def write_master_status(path, status):
    if not status:
        return
    info = format_binlog_info(filename=status.file,
                              position=status.position,
                              source='SHOW MASTER STATUS')
    with open(os.path.join(path, 'holland_master_info'), 'wb') as fileobj:
        print >>fileobj, info
        LOG.info("Wrote master status info to '%s'", fileobj.name)

def update_config_slave_status(config, slave_status):
    if not slave_status:
        return
    section = config.setdefault('mysql:replication', config.__class__())
    section['slave_master_log_file'] = slave_status.relay_master_log_file
    section['slave_master_log_pos'] = slave_status.exec_master_log_pos

def update_config_master_status(config, master_status):
    if not master_status:
        return
    section = config.setdefault('mysql:replication', config.__class__())
    section['master_log_file'] = master_status.file
    section['master_log_pos'] = str(master_status.position)
