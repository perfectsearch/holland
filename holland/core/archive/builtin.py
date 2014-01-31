"""
holland.core.archive.builtin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implementations of various archiving methods
"""

import os
import logging
from subprocess import Popen, list2cmdline, check_call, CalledProcessError, STDOUT
from tempfile import TemporaryFile
from holland.core.util.path import relpath
from holland.core.plugin import plugin_registry
from holland.core.archive.plugin import ArchiverBase, ArchiveError
from holland.core.stream import open_stream, load_stream_plugin

LOG = logging.getLogger(__name__)


signum_to_name = {0: 'SIG_DFL',
 1: 'SIG_IGN',
 2: 'SIGINT',
 3: 'SIGQUIT',
 4: 'SIGILL',
 5: 'SIGTRAP',
 6: 'SIGABRT',
 7: 'SIGBUS',
 8: 'SIGFPE',
 9: 'SIGKILL',
 10: 'SIGUSR1',
 11: 'SIGSEGV',
 12: 'SIGUSR2',
 13: 'SIGPIPE',
 14: 'SIGALRM',
 15: 'SIGTERM',
 17: 'SIGCLD',
 18: 'SIGCONT',
 19: 'SIGSTOP',
 20: 'SIGTSTP',
 21: 'SIGTTIN',
 22: 'SIGTTOU',
 23: 'SIGURG',
 24: 'SIGXCPU',
 25: 'SIGXFSZ',
 26: 'SIGVTALRM',
 27: 'SIGPROF',
 28: 'SIGWINCH',
 29: 'SIGPOLL',
 30: 'SIGPWR',
 31: 'SIGSYS',
 34: 'SIGRTMIN',
 64: 'SIGRTMAX'}

@plugin_registry.register
class TarArchiver(ArchiverBase):

    name = 'tar'

    summary = 'Archive via the tar command'

    tar_process = None

    def bind(self, context):
        self.context = context

    def terminate(self, signal):
        LOG.info("Terminating archive process")
        if self.tar_process:
            LOG.info("Terminating tar(%d) with signal %d",
                    self.tar_process.pid, signal)
            os.kill(self.tar_process.pid, signal)

    def archive(self, dstdir):
        args = [
            'tar',
            '--verbose',
            '--totals',
            '-cf', '-',
        ]

        if not self.paths:
            raise ArchiveError("No paths to archive specified")

        config = self.context.config['tar']

        if config.pre_args:
            args[1:1] = config.pre_args
        last_basedir = None
        for path, basedir in self.paths:
            LOG.info("Considering path=%r basedir=%r", path, basedir)
            if not os.path.isabs(path) and last_basedir != basedir:
                args.extend(['-C', basedir])
                last_basedir = basedir
            args.append(path)
        if config.post_args:
            args.extend(config.post_args)
        for pattern in config.exclude:
            args.extend(['--exclude', pattern])

        dstpath = os.path.join(dstdir, 'backup.tar')
        errdstpath = os.path.join(dstdir, 'archive.log')
        # The nesting here is nasty but done for py2.6 compatibility
        try:
            method = self.context.config.compression.method
            zconfig = self.context.config.compression
            with open_stream(dstpath, 'wb', method, zconfig) as stdout:
                with open(errdstpath, 'w+b') as stderr:
                    LOG.info("+ Archiving via command: %s", list2cmdline(args))
                    LOG.info("+ Archive destination: %s", stdout.name)
                    if hasattr(stdout, 'args'):
                        LOG.info("+ Compressing via %s writing to %s",
                                list2cmdline(stdout.args), stdout.name)
                    self.tar_process = Popen(args,
                                             stdout=stdout,
                                             stderr=stderr,
                                             close_fds=True)
                    try:
                        retcode = self.tar_process.wait()
                    except:
                        self.tar_process.kill()
                        LOG.warning("Terminated tar process")
                        raise
                    if retcode != 0:
                        stderr.flush()
                        stderr.seek(0)
                        for line in stderr:
                            LOG.error("tar: %s", line.rstrip())
                        if retcode < 0:
                            message = "tar was terminated by %s [%d]" % \
                                      (signum_to_name[-retcode], -retcode)
                        else:
                            message = "tar exited with non-zero status [%d]" % retcode
                        raise ArchiveError(message)
        except IOError as exc:
            raise ArchiveError(unicode(exc))

    def configspec(self):
        return """
        exclude = force_list(default=list())
        pre-args = force_list(default=list())
        post-args = force_list(default=list())
        """

    def plugin_info(self):
        return dict(
            name='tar',
            group='holland.archive',
            summary="Archiving plugin to generate tar archives",
            description='',
            targeted_version='2.0.0',
            plugin_version='1.0',
        )

@plugin_registry.register
class RsyncArchiver(ArchiverBase):

    name = 'rsync'

    summary = 'Archive using the rsync command'

    def archive(self, dstdir):
        join = os.path.join
        dst_path = join(dstdir)
        args = [
            'rsync',
            '--archive',
            '--recursive',
            '--verbose',
            '--copy-unsafe-links',
            os.path.join(dst_path, ''),
        ]
        for rpath, parent in self.paths:
            argv = args[:]
            argv.insert(-1, os.path.join(parent, rpath))
            argv.extend(self.config.additional_args)
            with open(join(dstdir, 'archive.log'), 'wb') as stdout:
                try:
                    LOG.info("%s", list2cmdline(argv))
                    check_call(argv,
                               stdout=stdout, stderr=STDOUT,
                               close_fds=True)
                except CalledProcessError as exc:
                    raise ArchiveError()

    def configspec(self):
        return """
        additional-args = cmdline(default='')
        """

#@plugin_registry.register
class ShellCmdArchiver(ArchiverBase):
    name = 'shell'

    summary = 'Archive a directory via a shell command'

    def archive(self, srcdir, dstdir):
        join = os.path.join
        shell_cmd = self.config['command-line'].format(
                        srcdir=srcdir,
                        dstdir=dstdir,
                    )
        args = [
            self.config['shell'],
            '-c', shell_cmd,
        ]
        LOG.info(" + %s", list2cmdline(args))
        with open(join(dstdir, 'archive.log'), 'w') as stdout:
            try:
                check_call(args, stdout=stdout, stderr=STDOUT, close_fds=True)
            except CalledProcessError as exc:
                raise ArchiveError()

    def configspec(self):
        return """
        shell = string(default='/bin/bash')
        command-line = string(default='/bin/true')
        """

@plugin_registry.register
class DirCopyArchiver(ArchiverBase):

    name = 'dircopy'

    summary = 'Archive a directory tree to another directory'

    def archive(self, dstdir):
        join = os.path.join
        dirname = os.path.dirname
        normpath = os.path.normpath
        zconfig = self.context.config.compression
        LOG.info("Using compression method '%s'", zconfig['method'])
        stream = load_stream_plugin(zconfig)
        for rpath, parent in self.paths:
            LOG.info("* Archiving %s/%s", parent, rpath)
            srcpath = normpath(join(parent, rpath))
            dstpath = normpath(join(dstdir, rpath))
            if not os.path.isdir(srcpath):
                os.makedirs(dirname(dstpath))
                LOG.debug("Copy requested file %s -> %s", srcpath, dstpath)
                LOG.info("  + Creating directory %s", dirname(dstpath))
                with stream.open(dstpath, 'wb') as fileobj:
                    check_call(['/bin/cat', srcpath], stdout=fileobj, close_fds=True)
                continue
            LOG.debug("Copy requested directory %s -> %s recursively", srcpath, dstpath)
            for dirpath, dirnames, filenames in os.walk(srcpath, topdown=True):
                rpath = relpath(dirpath, srcpath)
                target_base_path = normpath(join(dstpath, rpath))
                if not os.path.exists(target_base_path):
                    LOG.debug("Creating directory '%s'", target_base_path)
                    LOG.info("+ Creating directory '%s'", rpath)
                    os.makedirs(target_base_path)
                for name in dirnames:
                    LOG.debug("Creating directory '%s'", join(target_base_path, name))
                    LOG.info("+ Creating directory '%s'", join(rpath, name))
                    os.makedirs(join(target_base_path, name))
                for name in filenames:
                    csrcpath = join(dirpath, name)
                    cdstpath = join(target_base_path, name)
                    # skip non-regular files
                    if not os.path.isfile(csrcpath):
                        LOG.info("- Skipping '%s' - not a regular file.", rpath)
                        continue
                    # copy (dirpath, name) -> (dstpath, relpath(
                    with stream.open(cdstpath, 'wb') as fileobj:
                        LOG.info("+ Copying '%s'", rpath)
                        check_call(['/bin/cat', csrcpath], stdout=fileobj, close_fds=True)
