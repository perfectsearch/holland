"""
holland.mysql.server
~~~~~~~~~~~~~~~~~~~~

Run a MySQL instance

This process can be used to run a bootstrap mysqld process to
initiate InnoDB recovery on a cold MySQL datadir (e.g. after
an LVM snapshot) or to spin up an instance suitable for running
mysqldump.

This implementation uses jinja2 templates to generate an appropriate
my.cnf for the server to use.
Some points to keep in mind:

    * Ensure log-bin/relay-log is always set to some harmless location
      Otherwise, phantom binlogs may interfere with normal operation
    * Ensure we do not listen on the network
      Otherwise, we may interefere or be interefered with a running
      mysqld process
    * Use a non-standard socket file
      Sanity-check to avoid overwriting an existing socket file
    * Skip NDB - we should never need to backup NDB data anyway
    * Ensure we use the correct innodb-log-file-size/innodb-data-file-path
      If these are not set InnoDB may make incorrect assumptions and we
      will crash or fail to run the desired procedure
"""

import os
import logging
import socket
from time import time, sleep
from subprocess import Popen, STDOUT, list2cmdline
from jinja2 import Environment, PackageLoader
from holland.core import HollandError
from holland.core.util import format_interval
from holland.mysql.util import render_template

LOG = logging.getLogger(__name__)
info = LOG.info
warn = LOG.warn
debug = LOG.debug
error = LOG.error

class MySQLInterfaceError(HollandError):
    "Raised if the API is used incorrectly"


class MySQLTimeoutError(HollandError):
    "Raised if an operation timesout"

def test_unix_socket(path):
    if not os.path.exists(path):
        return False
    fd = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        fd.connect(path)
    except IOError, exc:
        LOG.debug("connection to '%s' failed: (%d) %s", path, exc.errno, exc.strerror)
        return False
    else:
        LOG.debug("Connected to '%s'", path)
        return True
    finally:
        fd.close()

class MySQLServer(object):
    """Control the creation and termination of mysqld processes"""

    def __init__(self,
                 options,
                 mysqld='mysqld',
                 name='mysql',
                 stdin=os.devnull,
                 start_timeout=1800,
                 stop_timeout=1800):
        """
        Create a new MySQLServer instance

        :param options: dictionary of options to pass to underlying template
        :param mysqld: path to mysqld executable
        :param name: name of this instance - used for naming pid, socket, log
        :param stdin: stdinput for mysql process.  Usefull when running in
                      bootstrap mode to create a new sandbox.
        :param start_timeout: maximum wait time for mysqld to start
        :param stop_timeout: maximum wait time for mysqld to exit gracefully
        """
        self.mysqld = mysqld
        self.options = options
        self.name = name
        self.stdin = stdin
        self.start_timeout = start_timeout
        self.stop_timeout = stop_timeout
        self.process = None

    def write_defaults(self):
        """Write the instance's configured options to a default file

        This method renders a jinja2 template with the options provided
        to this MySQLServer instance. The resulting string is then saved
        to this instance's ``defaults_file``.
        """
        self.options['log_error'] = self.error_log
        self.options['socket'] = self.socket
        self.options['pid_file'] = self.pid_file
        defaults = render_template('server.defaults', self.options)
        with open(self.defaults_file, 'wb') as fileobj:
            fileobj.write(defaults)


    def to_argv(self):
        """
        Generate an argv list for starting mysqld
        """
        # The additional options are specified explicitly here to
        # make troubleshooting easier should mysqld hang
        # it will be immediately obvous where the socket, datadir and
        # error log were intended to be.  These options are all also
        # written to the my.cnf defaults_file as created in
        # ``write_defaults``
        debug("Generating argv")
        return [
            self.mysqld,
            '--defaults-file=' + self.defaults_file,
            '--datadir=' + self.datadir,
            '--socket=' + self.socket,
            '--log-error=' + self.error_log,
        ]

    def start(self):
        """
        Start a MySQL server process
        """
        if self.process:
            raise MySQLInterfaceError("mysqld process already started")
        self.write_defaults() # write out the *my.cnf file
        #if not self.options['bootstrap']:
        #    error_log = '/dev/null'
        error_log = self.error_log
        with open(self.stdin, 'rb') as stdin:
            with open(error_log, 'ab') as stdout:
                debug("opened stdout = %r", stdout)
                argv = self.to_argv()
                info("$ %s", list2cmdline(argv))
                self.process = Popen(argv,
                                     stdin=stdin,
                                     stdout=stdout,
                                     stderr=STDOUT,
                                     close_fds=True
                                     )
        # wait for socket
        if not self.options['bootstrap']:
            anchor_time = time()
            while time() - anchor_time < self.start_timeout:
                if self.process.poll() is not None:
                    with open(error_log, 'rb') as errors:
                        for line in errors:
                            info("! %s", line)
                    raise MySQLTimeoutError("Startup failed")
                if test_unix_socket(self.socket):
                    LOG.info("%s now accepting connections.", self.socket)
                    break
                # wait for the socket to come online
                sleep(0.5)
            else:
                # timeout
                # check one last time and then kill
                if not os.path.exists(self.socket):
                    self.kill()
                    raise MySQLTimeoutError("startup timed out")
            info("%s startup took %s", argv[0], format_interval(time() - anchor_time))
        else:
            debug("bootstrap is set, not checking for socket file")

    def stop(self):
        """
        Stop a running MySQL server process

        :raises: timeout error if stopping the service exceess `stop_timeout`
        """
        process = self.process
        if not process:
            raise MySQLInterfaceError("No mysqld process has been started.")
        if not self.options['bootstrap'] and process.poll() is None:
            process.terminate() # send SIGTERM to initiate shutdown
            info("Sent SIGTERM to pid=%s", process.pid)
        debug("Waiting for mysqld to stop")
        anchor_time = time()
        while time() - anchor_time < self.stop_timeout:
            if process.poll() is not None:
                debug("Exiting because process.poll() is not None: %s",
                        process.poll())
                break
            debug("  - MySQL is still not done. Sleeping for 1 second")
            sleep(1)
        else:
            # this is hit if we did not break from the loop
            # i.e. we triggered the stop_timeout condition
            info(" ! Timed out after %s. Terminating mysql with SIGKILL",
                    self.stop_timeout)
            if process.poll() is None:
                error(" ! Timeout. mysqld did not stop within %d seconds",
                      self.stop_timeout)
                self.kill()
                info(" ! Process terminated with SIGKILL")

        returncode = process.poll()
        info("%s stopped in %s", self.to_argv()[0], format_interval(time() - anchor_time))
        if returncode != 0:
            error(" !  %s exited with non-zero status: %d", self.to_argv()[0], returncode)
            raise MySQLTimeoutError("mysqld exited with non-zero status %d" % (
                            returncode,))

    def kill(self):
        """
        Immediately terminate the running mysqld process

        """
        debug("running kill()")
        process = self.process
        if not process:
            error(" !! Internal error - attempt to kill a mysqld process that was "
                  "never started")
            raise MySQLInterfaceError("No mysqld has been started")
        if process.poll() is None:
            process.kill()
        return process.wait()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            info("Stopping the MySQL server '%s'", self.datadir)
            self.stop()
        except Exception, exc:
            # suppress the Timeout exception from stop() unless
            # no other exception is active.  This avoids overwriting
            # an active exception with our own
            debug("stop() failed.", exc_info=True)
            if exc_type is not None:
                raise
            else:
                # but at least log the error
                warn(" ! %s did not stop cleanly: %s", self.to_argv()[0], exc)

    @property
    def datadir(self):
        """Datadir as retrieve from options"""
        return os.path.normpath(os.path.realpath(self.options['datadir']))

    @property
    def error_log(self):
        """Calculated path to this instance's --log-error"""
        return os.path.join(self.datadir,
                            '{name}.log'.format(name=self.name))

    @property
    def defaults_file(self):
        """Calculated path to this instance's --defaults-file"""
        return os.path.join(self.datadir,
                            '{name}-my.cnf'.format(name=self.name))

    @property
    def socket(self):
        """Calcuated path to this instance's socket file"""
        return os.path.join(self.datadir, '{name}.sock'.format(name=self.name))

    @property
    def pid_file(self):
        """Calculated path to this instance's pid file"""
        return os.path.join(self.datadir, '{name}.pid'.format(name=self.name))
