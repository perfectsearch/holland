import os
import pwd
import logging
from tempfile import NamedTemporaryFile
from holland.core import which, HollandError

LOG = logging.getLogger(__name__)

def recursive_chown(datadir, username):
    entry = pwd.getpwnam(username)
    for dirpath, dirnames, filenames in os.walk(datadir):
        for name in dirnames + filenames:
            os.chown(os.path.join(dirpath, name), entry.pw_uid, entry.pw_gid)

def path_owner(path):
    """Find the name of the user who owns ``path``

    This is used to set a proper user option for mysqld
    """
    try:
        st = os.stat(path)
    except OSError:
        LOG.debug("stat(%r) failed: [%d] %s", path, exc.errno, exc.strerror)
        return None

    try:
        pw_st = pwd.getpwuid(st.st_uid)
    except KeyError, exc:
        LOG.debug("getwuid(%r) failed.", st.st_uid)
        return None
    else:
        return pw_st.pw_name


def prepare_binlogs(datadir, target_binlog):
    LOG.info("Preparing snapshot path '%s' to support mysqldump --master-data",
              datadir)
    LOG.info("Recorded binary log: %s", target_binlog)
    log_bin, ext = os.path.splitext(target_binlog)
    base_path = os.path.join(datadir, log_bin)
    index_path = base_path + '.index'
    if os.path.exists(base_path + ext):
        with NamedTemporaryFile(prefix=base_path, delete=False) as f:
            LOG.info("Renaming existing binary log %s to %s", base_path + ext, f.name)
            os.rename(base_path + ext, f.name)
    # ensure at least a zero byte file exists
    first_binlog = "{0}.{1:0>6}".format(base_path, int(ext[1:]) - 1)
    LOG.info("Ensuring %s exists", first_binlog)
    datadir_st = os.stat(datadir)
    with open(first_binlog, 'a') as binlog:
        binlog.write('\xfebin') # binlog magic
        os.fchown(binlog.fileno(), datadir_st.st_uid, datadir_st.st_gid)
    with open(index_path, 'w') as f:
        f.write(first_binlog + os.linesep)
        os.fchown(f.fileno(), datadir_st.st_uid, datadir_st.st_gid)
