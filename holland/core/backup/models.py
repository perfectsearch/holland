"""
holland.core.backup.models
~~~~~~~~~~~~~~~~~~~~~~~~~~

Catalog database SQLAlchemy models

:copyright: 2008-2013 Rackspace US, Inc.
:license: BSD, see LICENSE.rst for details
"""

import os, sys
import logging
from contextlib import contextmanager
from decimal import Decimal
from datetime import datetime
from subprocess import list2cmdline
from sqlalchemy import create_engine, types
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import String, Text, Integer, Numeric, DateTime
from sqlalchemy.orm import backref, relation, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from holland.version import __version__ as __holland_version__

LOG = logging.getLogger(__name__)

class BaseExt(object):
    """Does much nicer repr/print of class instances
    from sqlalchemy list suggested by Michael Bayer
    """
    def __repr__(self):
        attributes = []
        for column in self.__table__.c:
            name = column.name
            value = getattr(self, name)
            attributes.append('{name}={value!r}'.format(
                                name=name, value=value
                              )
                             )

        return "{cls}({attributes})".format(
                    cls=self.__class__.__name__,
                    attributes=', '.join(attributes)
               )

DeclarativeBase = declarative_base(cls=BaseExt)

# Monkey patch support for BigInt, as needed
try:
    from sqlalchemy.types import BigInteger
except ImportError:
    class BigInteger(Integer): pass
    class BIGINT(BigInteger):
        """SQL BigInt Type"""
    class DBBigInteger(BigInteger):
        def get_col_spec(self): return "BIGINT"
    # monkey patch supported platforms
    import sqlalchemy.databases.postgres
    import sqlalchemy.databases.sqlite
    import sqlalchemy.databases.mysql
    sqlalchemy.databases.postgres.PGBigInteger = DBBigInteger
    sqlalchemy.databases.postgres.colspecs[BigInteger] = DBBigInteger
    sqlalchemy.databases.sqlite.SLBigInteger = DBBigInteger
    sqlalchemy.databases.sqlite.colspecs[BigInteger] = DBBigInteger
    class MSBigInteger(BigInteger, sqlalchemy.databases.mysql.MSInteger):
        def __init__(self, display_width=None, **kw):
            self.display_width = display_width
            sqlalchemy.databases.mysql._NumericType.__init__(self, kw)
            BigInteger.__init__(self, **kw)

    def get_col_spec(self):
        if self.display_width is not None:
            return self._extend("BIGINT(%(display_width)s)" % {'display_width': self.display_width})
        else:
            return self._extend("BIGINT")

    sqlalchemy.databases.mysql.MSBigInteger = MSBigInteger
    sqlalchemy.databases.mysql.colspecs[BigInteger] = MSBigInteger

class SchemaVersion(DeclarativeBase):
    """Version table for the current model version in use

    This is intended to be used for future upgrades, if needed
    """
    __tablename__ = 'schema_version'
    __table_args__ = {'mysql_engine':'InnoDB'}
    version = Column(Integer, primary_key=True)
    holland_version = Column(String(128), default=__holland_version__)

class Job(DeclarativeBase):
    """Backup job consisting of one or more backups"""
    __tablename__ = 'job'
    __table_args__ = {'mysql_engine':'InnoDB'}

    ## Database attributes
    id = Column(Integer, primary_key=True, autoincrement=True)
    pid = Column(Integer, default=os.getpid)
    cmdline = Column(Text, default=list2cmdline(sys.argv))
    start_time = Column(DateTime, default=datetime.now)
    stop_time = Column(DateTime)
    status = Column(String, default='initialized')
    external_id = Column(String(128), index=True)
    is_dryrun = False

    def __enter__(self):
        self.start_time = datetime.now()
        return self

    def __exit__(self, exctype, exc, traceback):
        self.stop_time = datetime.now()

class Backup(DeclarativeBase):
    """Backup run mapping to a single backup strategy"""
    __tablename__ = 'backup'
    __table_args__ = {'mysql_engine':'InnoDB'}

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("job.id"))
    name = Column(String(255))
    start_time = Column(DateTime, default=datetime.now)
    stop_time = Column(DateTime)
    message = Column(Text)
    status = Column(String, default='initialized')
    estimated_size = Column(BigInteger, default=None)
    real_size = Column(BigInteger, default=None)
    backup_directory = Column(String(4096))
    config_path = Column(String(4096))
    config = Column(Text)

    job = relation("Job", backref=backref("backups", order_by=id))

    def __enter__(self):
        self.start_time = datetime.now()
        return self

    def __exit__(self, exctype, exc, traceback):
        self.stop_time = datetime.now()

    def duration(self):
        start_time = self.start_time
        stop_time = self.stop_time
        if start_time and stop_time:
            delta = stop_time - start_time
            return (delta.days*24*60*60 + delta.seconds +
                    delta.microseconds*10**-6)
        else:
            return None

@contextmanager
def timestamp_model(model):
    """Set start_time/stop_time on a model

    This is intended for use as a ContextManager
    so that one can run:

    with Backup() as backup:
        # run a backup

    And have the start/stop times automatically set.
    """
    model.start_time = datetime.now()
    try:
        yield model
    finally:
        model.stop_time = datetime.now()

def create_session(*args, **kwargs):
    """Create a session"""
    engine = create_engine(*args, **kwargs)
    DeclarativeBase.metadata.create_all(engine)
    session = Session(bind=engine)

    try:
        if not session.query(SchemaVersion).first():
            session.add(SchemaVersion())
    finally:
        session.commit()

    return session
