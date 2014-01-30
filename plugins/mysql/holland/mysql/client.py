"""
holland.mysql.client
~~~~~~~~~~~~~~~~~~~

MySQL client connection wrapper
"""
import time
import logging
import codecs
import collections
from os.path import basename, splitext, expanduser, abspath
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.exc import DatabaseError, DBAPIError, OperationalError

from holland.core import HollandError
from holland.core.util import format_interval

from holland.mysql.util import render_template

LOG = logging.getLogger(__name__)

EngineInfo = collections.namedtuple('EngineInfo',
                                    'name support comment transactions xa '
                                    'savepoints is_enabled')

# XXX: Deprecate once sqlalchemy < 0.6 no longer supported
def first(result):
    """Return first row from a SQLAlchemy ResultProxy and close result

    This is supported directly via ResultProxy.first() in SQLAlchemy 0.6+
    However, this package currently supports sqlalchemy 0.5.5 in order
    to ease deployment on RHEL6.

    :returns: RowProxy for first row
    """
    try:
        return result.fetchone()
    finally:
        result.close()

class MySQLFlushLock(object):
    def __init__(self, mysql, preflush_tables=True, lock_tables=True):
        """
        :param mysql: mysql client connection through which to issue queries
        :param preflush_tables: whether to rn a FLUSH /* LOCAL */ TABLES prior
                                to running FLUSH TABLES WITH READ LOCK
        :param lock_tables: whether to run FLUSH TABLES WITH READ LOCK
                            if false, this context manager is a noop and does
                            nothing
        """
        self.mysql = mysql
        self.locked = False
        self.preflush_tables = preflush_tables
        self.lock_tables = lock_tables

    def lock(self):
        self.locked = True
        LOG.info("Executing FLUSH TABLES WITH READ LOCK")
        self.lock_start = time.time()
        self.mysql.flush_tables_with_read_lock()
        LOG.info("FLUSH TABLES WITH READ LOCK completed in %s",
                 format_interval(time.time() - self.lock_start, precision=5))

    def unlock(self):
        if self.locked:
            LOG.info("Executing UNLOCK TABLES")
            start = time.time()
            self.mysql.unlock_tables()
            LOG.info("UNLOCK TABLES completed in %s",
                    format_interval(time.time() - start))
            LOG.info("MySQL was locked for %s",
                     format_interval(time.time() - self.lock_start, precision=5))
            self.locked = False

    def __enter__(self):
        if self.lock_tables and self.preflush_tables:
            LOG.info("Executing pre-flush FLUSH /*!40101 LOCAL */TABLES")
            start = time.time()
            self.mysql.flush_tables()
            LOG.info("FLUSH /*!40101 LOCAL */TABLES took %s",
                     format_interval(time.time() - start))
        self.lock()
        return self

    def __exit__(self, exc_type, value, traceback):
        self.unlock()


@contextmanager
def pause_mysql_slave(mysql, wrap_exception=None):
    """Context manager that pauses a slave for the duration of the with block
    by issuing STOP SLAVE SQL_THREAD on entry, and START SLAVE SQL_THREAD
    on exit
    """
    if mysql.status('slave_running') != 'ON':
        yield
    else:
        try:
            mysql.stop_slave(sql_thread=True, io_thread=False)
        except mysql.DatabaseError as exc:
            if wrap_exception:
                exc = wrap_exception(exc)
            raise exc
        try:
            yield
        finally:
            mysql.start_slave(sql_thread=True, io_thread=False)


class MySQL(object):
    """A MySQL client interface with various convenience functions for
    common admin actions.
    """
    DatabaseError = DatabaseError

    def __init__(self, *args, **kwargs):
        # workaround for sqlalchemy 0.8 where we default
        # to case sensitive:
        try:
            kwargs['case_sensitive'] = False
            self._engine = create_engine(*args, **kwargs)
        except TypeError:
            del kwargs['case_sensitive']
            self._engine = create_engine(*args, **kwargs)
        #self.DatabaseError = self._engine.dialect.dbapi.DatabaseError

    def execute(self, sql, *multiparams, **params):
        """Execute an arbitrary query"""
        #try:
        return self._engine.execute(sql, *multiparams, **params)
        #except DBAPIError as exc:
        #    raise exc.orig


    # XXX: Various compatibility issues with MySQL 5.0 for some variables
    def variable(self, name, session=False):
        """Show value of various MySQL system variables

        By default this runs SELECT @@{scope}.{variable}
        This will not provide the value for all variables in
        older versions of MySQL - namely many InnoDB variables
        will only be available via SHOW [GLOBAL|SESSION] VARIABLES
        and SELECT @@variable may fail.  You may need to use
        SHOW GLOBAL VARIABLES LIKE 'innodb_...' in that case.
        """
        scope = 'global' if not session else 'session'
        sql = "SELECT @@{scope}.{name}".format(scope=scope,
                                               name=name)
        try:
            return self.execute(sql).scalar()
        except AttributeError:
            return None

    #: shorthand for `variable`
    var = variable

    def variables_like(self, pattern='%', session=False):
        """Iterate of set of variable matching the given pattern

        :param pattern: pattern to pass to LIKE
        :param session: whether to look at session or global variables
                        defaults to false and global variables are returned
        :yields: key, value pairs of matching variables
        """
        scope = 'GLOBAL' if not session else 'SESSION'
        sql = "SHOW {scope} VARIABLES LIKE %s".format(scope=scope)

        for key, value in self.execute(sql, pattern):
            yield key, value

    def status(self, name, session=False):
        """Execute SHOW GLOBAL STATUS

        If session is True only session status will be examined.

        By default GLOBAL status is examined.
        """
        scope = 'GLOBAL' if not session else ''
        sql = "SHOW {scope} STATUS LIKE '{name}'".format(scope=scope,
                                                         name=name)
        try:
            return first(self.execute(sql)).value
        except AttributeError:
            return None

    def master_status(self):
        """Execute SHOW MASTER STATUS and return a named tuple
        """
        return first(self.execute("SHOW MASTER STATUS"))

    def slave_status(self):
        """Execute SHOW SLAVE STATUS and return a named tuple
        representing the current replication status

        :returns: named tuple
        """
        return first(self.execute("SHOW SLAVE STATUS"))

    def start_slave(self, io_thread=True, sql_thread=True):
        """Execute a START SLAVE query

        If either io_thread or sql_thread is false only one of the
        replication threads will be started
        """
        sql = "START SLAVE"
        if not (io_thread and sql_thread):
            sql += ' IO_THREAD' if io_thread else ' SQL_THREAD'
        LOG.info("%s", sql)
        self.execute(sql)

    def stop_slave(self, io_thread=True, sql_thread=True):
        """Execute a STOP SLAVE query

        If either io_thread or sql_thread is false, then only
        one of the two replication threads will be stopped.

        This is convenient to only pause SQL replay and not also
        generation of relay logs.
        """
        sql = "STOP SLAVE"
        if not (io_thread and sql_thread):
            sql += ' IO_THREAD' if io_thread else ' SQL_THREAD'
        LOG.info("%s", sql)
        self.execute(sql)

    @contextmanager
    def pause_replication(self):
        try:
            LOG.info("Pausing MySQL replication")
            self.stop_slave(io_thread=False)
            yield
        finally:
            LOG.info("Resuming MySQL replication")
            self.start_slave(io_thread=False)

    def show_create_table(self, name, schema):
        """Execute SHOW CREATE TABLE and returns results
        """
        sql = 'SHOW CREATE TABLE `{schema}`.`{table}`'.format(
                schema=schema,
                table=name
              )
        ddl = first(self.execute(sql))
        if ddl:
            return "\n".join([
            '/*!40101 SET @saved_cs_client     = @@character_set_client */;',
            '/*!40101 SET character_set_client = %s */;' % ddl[2],
            ddl[1],
            '/*!40101 SET character_set_client = @saved_cs_client */;'
            ])

    def show_create_view(self, name, schema):
        sql = "SHOW CREATE VIEW `{0}`.`{1}`".format(schema, name)
        try:
            ddl = first(self.execute(sql))
            params = {}
            if ddl:
                params['view_ddl'] = ddl[1]
                if ddl.has_key('character_set_client'):
                    params['character_set_client'] = ddl.character_set_client
                if ddl.has_key('collation_connection'):
                    params['collation_connection'] = ddl.collation_connection
            return render_template('create_view', params)
                            
        except OperationalError as exc:
            sql = ('SELECT * '
                   'FROM INFORMATION_SCHEMA.VIEWS '
                   'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s')
            ddl = first(self.execute(sql, schema, name))
            params = {}
            if ddl:
                params['definer'] = ddl.definer
                params['security_type'] = ddl.security_type
                params['view_name'] = ddl.table_name
                params['view_definition'] = ddl.view_definition
                params['check_option'] = ddl.check_option
                if ddl.has_key('character_set_client'):
                    params['character_set_client'] = ddl.character_set_client
                if ddl.has_key('collation_connection'):
                    params['collation_connection'] = ddl.collation_connection
            return render_template('create_view', params)

    def flush_tables(self):
        """Execute a FLUSH TABLES query"""
        self.execute('FLUSH /*!40101 LOCAL */TABLES')

    def flush_tables_with_read_lock(self):
        """Execute a FLUSH TABLES WITH READ LOCK query"""
        sql = 'FLUSH TABLES WITH READ LOCK'
        self.execute(sql)

    def unlock_tables(self):
        """Execute an UNLOCK TABLES query"""
        self.execute('UNLOCK TABLES')

    def flush_logs(self):
        """Execute a FLUSH LOGS query"""
        self.execute('FLUSH LOGS')

    def session(self):
        """Create a SQLAlchemy `Session` instance
        from this MySQL instance.

        This can be used for further ORM querying against
        the MySQL server
        """
        return sessionmaker(bind=self._engine, autocommit=True)()

    def show_engines(self):
        """Retrieve current available engines from a MySQL instances

        :returns: a dict of name to ``EngineInfo`` instance
        """
        info = {}
        for row in self.execute("SHOW ENGINES"):
            engine_info = EngineInfo(
                name=row.engine,
                support = row.support,
                comment=row.comment,
                transactions=row.transactions if row.has_key('transactions') else None,
                xa=row.xa if row.has_key('xa') else None,
                savepoints=row.savepoints if row.has_key('savepoints') else None,
                is_enabled=row.support in ('DEFAULT', 'YES')
            )
            info[engine_info.name] = engine_info
        return info

    def binary_log_basename(self):
        """Determine the basename of the binary log in use by
        the MySQL engine associated with this engine.
        """
        master_status = self.master_status()
        if not master_status:
            return None
        return splitext(basename(master_status.file))[0]

    def host_info(self):
        """Returns a string describing the type of connection in use,
        including the server host name.
        """
        connection = self._engine.raw_connection()
        try:
            return connection.get_host_info()
        finally:
            connection.close()

    def ping(self):
        """Send COM_PING to the MySQL instance.

        This will raise an OperationalError if the server is not
        reachable or there are insufficient privileges.
        """
        connection = self._engine.raw_connection()
        try:
            connection.ping()
        finally:
            connection.close()

    def shutdown(self):
        """Send a COM_SHUTDOWN to the MySQL instance.

        This will raise an OperationalError if MySQL
        is down or this operation is not permitted.

        This will cause MySQL to shut itself down and
        any further queries will fail until MySQL is
        available again.
        """
        connection = self._engine.raw_connection()
        try:
            connection.shutdown()
        finally:
            connection.close()

    def format_error(self, mysql_error):
        """Format a DatabaseError derived instance into a mysql error string
        """
        fmt = "[{errno}] {message}"
        return fmt.format(errno=mysql_error.orig.args[0],
                          message=mysql_error.orig.args[1])

    def dispose(self):
        """Dispose of this instances engine.  The instance is not usable
        afterwards"""
        # drop any outstanding connections
        self._engine.dispose()

    def warnings(self):
        """List the warnings from the last executed statement"""
        return self.execute('SHOW WARNINGS').fetchall()

    @property
    def version(self):
        """MySQL server version as a X.X.X string"""
        version = self.var('version')
        # 5.6.6-m9-log
        return version.split('-')[0]

    @property
    def version_tuple(self):
        """MySQL Server version as a tuple"""
        version = self.version
        return tuple(int(digit) for digit in version.split('.'))

    @classmethod
    def from_dict(cls, config, **engine_kwargs):
        """Create a `MySQL` instance from a dict

        A config dict may consist of the following keys:
            * user - the mysql username to authenticate with
            * password - mysql password to authenticate with
            * host - host to connect to
            * port - port to connect to
            * socket - unix socket to connect to
            * defaults-file - my.cnf-like file to read other auth parameters
                              from

        :param config: dict of parameters to use when connecting to MySQL
        :param engine_kwargs: additional keyword arguments to pass directly
                              to the class constructor
        """
        std_kwargs = {}
        query_kwargs = {}
        for key, value in config.items():
            if key in ('user', 'password', 'host', 'port'):
                if key == 'user':
                    key = 'username'
                std_kwargs[key] = value
            if key == 'defaults-file' and value:
                query_kwargs['read_default_file'] = expanduser(value)
            if key == 'socket' and value:
                query_kwargs['unix_socket'] = value
        url = URL('mysql', database='', query=query_kwargs, **std_kwargs)
        return cls(url, pool_size=1, poolclass=SingletonThreadPool,
                   **engine_kwargs)

    @classmethod
    def from_defaults(cls, defaults_file, **engine_kwargs):
        query = {
            'read_default_file' : defaults_file
        }
        return cls(URL('mysql', database='', query=query), **engine_kwargs)

def quote_mysql_option(value):
    """Quote a value inside a my.cnf file"""
    value = str(value)
    return '"' + value.replace('"', '\\"') + '"'

def generate_defaults_file(defaults_file, include=(), **kwargs):
    """Generate a mysql option file

    :param path: path to write option file to
    :param include: other option file paths to include
                    These will be written to ``path`` as !include directives
    :param kwargs: key-value pairs of additional authentication options
                   any key that is not a valid mysql authentication option
                   will be skipped
    :returns: name of generated file
    """
    valid_auth_opts = set([
        'user',
        'password',
        'socket',
        'host',
        'port',
        'ssl',
        'ssl-ca',
        'ssl-capath',
        'ssl-cert',
        'ssl-cipher',
        'ssl-key',
        'ssl-verify-server-cert'
    ])
    with codecs.open(defaults_file, 'ab', encoding='utf8') as fileobj:
        option_files = set(abspath(expanduser(path)) for path in include)
        LOG.debug("Including mysql option files: %s", ','.join(option_files))
        for path in option_files:
            print >>fileobj, "!include {0}".format(path)
        options = []
        for name, value in kwargs.iteritems():
            if name in valid_auth_opts and value:
                value = quote_mysql_option(value)
                line = "{name} = {value}".format(name=name, value=value)
                options.append(line)
        if options:
            print >>fileobj, "# holland-mysql authentication options"
            print >>fileobj, "[client]"
            for line in options:
                print >>fileobj, line
        return defaults_file
