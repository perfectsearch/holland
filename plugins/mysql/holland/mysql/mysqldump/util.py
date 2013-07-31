"""
holland.mysql.mysqldump.util
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Utility methods for mysqldump plugin

"""

import os
import codecs
import logging
from holland.core import which, HollandError
from holland.core.util.pycompat import check_output, PIPE, STDOUT, CalledProcessError

LOG = logging.getLogger(__name__)

def generate_mysqldump_options(defaults_file, config, mysqldump_version):
    """Append mysqldump options to a my.cnf defaults file"""
    # code for each option in plugin's [mysqldump] section
    # to append to [mysqldump] section in defaults file
    LOG.info("Adding options to defaults-file %s", defaults_file)
    file_per_table = config.mysqldump_strategy == 'file-per-table'
    with codecs.open(defaults_file, 'ab', encoding='utf8') as fileobj:
        print >>fileobj, "# Holland mysqldump options"
        print >>fileobj, "[mysqldump]"
        if not file_per_table and config.dump_routines:
            if mysqldump_version < (5, 1, 2):
                LOG.warning("Skipping --routines - Not supported in "
                            "mysqldump < 5.1.2")
            else:
                print >>fileobj, "routines"
                LOG.info("Added routines option")
        if not file_per_table and config.dump_events:
            if mysqldump_version < (5, 1, 8):
                LOG.warn("Skipping --events - not supported in mysqldump "
                         "< 5.1.8")
            else:
                print >>fileobj, "events"
                LOG.info("Added events option")
        if config.max_allowed_packet:
            print >>fileobj, "max-allowed-packet=" + config.max_allowed_packet
            LOG.info("Added max-allowed-packet=%s",
                     config.max_allowed_packet)
        if not file_per_table and config.bin_log_position:
            print >>fileobj, "master-data=2"
            LOG.info("Added master-data=2")

def generate_table_exclusions(defaults_file, schema):
    """Append exclusions to a my.cnf defaults file."""
    LOG.info("Checking for table exclusions")
    with codecs.open(defaults_file, 'ab', encoding='utf8') as fileobj:
        exclusion_count = 0
        print >>fileobj, "[mysqldump]"
        for dbname, tblname in schema.excluded_tables():
            qualified_name = '{0}.{1}'.format(dbname, tblname)
            LOG.info("Added ignore-table=%s exclusion", qualified_name)
            print >>fileobj, 'ignore-table=' + qualified_name
            exclusion_count += 1
        if not exclusion_count:
            LOG.info("No tables excluded")
        else:
            LOG.info("%d tables excluded", exclusion_count)

def which_mysqldump(candidates=None):
    candidates = candidates or os.environ['PATH'].split(os.pathsep)
    for name in candidates:
        if os.path.isdir(name):
            name = os.path.join(name, 'mysqldump')
        try:
            result = which(name)
            LOG.info("Found %s", result)
            return result
        except OSError:
            continue
    raise HollandError("No mysqldump binary found")

def mysqldump_version(bin_mysqldump):
    try:
        result = check_output([bin_mysqldump, '--no-defaults', '--version'],
                              stderr=STDOUT, close_fds=True)
    except CalledProcessError, exc:
        for line in exc.output.splitlines():
            LOG.error("mysqldump --version: %s", line.rstrip())
        return None
    else:
        version_str = result.split()[4][:-1]
        LOG.info("%s version: %s", bin_mysqldump, version_str)
        version_tuple = tuple(map(int, version_str.split('.')))
        return version_tuple

def check_version(mysqldump_version, server_version):
    pass
