import os
import errno
import shutil
import tempfile
import logging
import shlex
from subprocess import Popen
from holland.lib.compression import open_stream
from holland.backup.file.tar_action import TarArchiveAction

log = logging.getLogger(__name__)


class run_command(object):

    command = []

    def __init__(self, command):
        self.command = shlex.split(command.encode())

    def __call__(self, event, snapshot_fsm, snapshot_vol):
        command = self.command[:]
        command.append(event.encode())
        log.info('Running the quiesce-script with the following command: %s' %
            ' '.join(command))
        p = Popen(command)
        p.communicate()


def setup_actions(snapshot, config, spooldir, archive_name,
    snap_datadir=None, archive_func=None, filelist=None):
    """Setup actions for a LVM snapshot based on the provided
    configuration.
    """

    if config['lvm']['quiesce-script']:
        act = run_command(config['lvm']['quiesce-script'])
        snapshot.register('pre-snapshot', act, priority=100)
        snapshot.register('post-snapshot', act, priority=100)
        snapshot.register('post-mount', act, priority=50)
        # snapshot.register('pre-remove', act, priority=100)

    try:

        archive_stream = open_stream(os.path.join(spooldir,
                                                  '%s.tar' % archive_name),
                                     'w',
                                     method=config['tar']['method'],
                                     level=config['tar']['level'],
                                     extra_args=config['tar']['options'])
    except OSError, exc:
        raise BackupError("Unable to create archive file '%s': %s" %
                          (os.path.join(spooldir, '%s.tar' % archive_name), exc))

    act = TarArchiveAction(snap_datadir, archive_stream.fileobj, config['tar'],
        archive_func=archive_func, filelist=filelist)
    snapshot.register('post-mount', act, priority=50)
