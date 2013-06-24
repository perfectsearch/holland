"""
holland.core.backup.catalog
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Front-end API to the catalog database

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from holland.core.config import Config, ConfigError
from . import models

def load_catalog(url, *args, **kwargs):
    """Create a session"""
    if not url:
        url = 'sqlite://'
    if '//:' not in url:
        url = 'sqlite:///' + url
    engine = create_engine(url, *args, **kwargs)
    models.DeclarativeBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # initialize the catalog, if necessary here
    session = Session()

    try:
        if not session.query(models.SchemaVersion).first():
            session.add(models.SchemaVersion())
    finally:
        session.commit()

    return Catalog(session)

class Catalog(object):
    def __init__(self, session):
        self.session = session

    def _query(self, model, *args, **kwargs):
        """Query the backup catalog"""
        query = self.session.query(model)
        if args:
            query = query.filter(*args)
        if kwargs:
            query = query.filter_by(**kwargs)
        return query

    @contextmanager
    def save(self, model):
        """Save a model to the catalog"""
        session = self.session
        session.add(model)
        session.commit()
        try:
            yield model
        except:
            raise
        finally:
            session.commit()

    def session(self):
        return self.session_factory()

    def load_backup(self, *args, **kwargs):
        """Load a backup

        Load the first matching backup that meets the filter criteria.

        To load all the matching backups use ``list_backups`` instead.

        :params args: args to filter backups by
        :params kwargs: kwargs to filter backups by
        :returns: ``Backup`` instance
        """
        query = self._query(models.Backup, *args, **kwargs)
        return query.order_by(models.Backup.start_time).first()

    def load_backup_from_node(self, node):
        """Create a backup instance from a spool node
        
        :param node: BackupNode instance to examine
        :returns: ``Backup`` model instance
        """
        backup = models.Backup(backup_directory=node.path)
        try:
            with node.open('.holland/status', 'rb') as statusf:
                status = Config.from_iterable(statusf)
        except (IOError, ConfigError):
            backup.status = 'failed'
        else:
            backup.status = status.status
        return backup

    def previous_backup(self, backup):
        """Load the first backup before the given backup

        Queries the catalog database for a backup with a start time
        preceding ``backup``

        :param backup: backup instance to find previous backup of
        :returns: ``Backup`` instance or None if no matching backup record
                  found
        """
        query = self._query(models.Backup,
                            models.Backup.start_time < backup.start_time)
        return query.order_by(models.Backup.start_time.desc()).limit(1).first()

    def next_backup(self, backup):
        """Load the first backup after the given backup

        :param backup: backup to base search on
        :returns: ``Backup`` instance or None if no matching backup record
        """
        query = self._query(models.Backup,
                            models.Backup.start_time > backup.start_time)
        return query.order_by(models.Backup.start_time.desc()).limit(1).first()

    def list_backups(self, *args, **kwargs):
        """List all backups

        :param args: args to filter backups by
        :param kwargs: kwargs to filter backups by
        :returns: list of ``Backup`` instances
        """
        query = self._query(models.Backup, *args, **kwargs)
        return query.order_by(models.Backup.start_time).all()

    def list_jobs(self):
        query = self._query(models.Job, *args, **kwargs)
        return query.order_by(models.Job.start_time).all()

