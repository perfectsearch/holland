import re
import fnmatch
import logging
from operator import itemgetter

from sqlalchemy import Column, ForeignKey, String, Integer
from sqlalchemy.sql import and_, or_, not_, func, alias, literal_column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import OperationalError, DBAPIError
from holland.core.util import format_bytes, format_interval
from holland.mysql.client import first

LOG = logging.getLogger(__name__)

DeclarativeBase = declarative_base()

#: match strings that have glob wildcards
GLOB_CRE = re.compile('[*?\[\]]')

def glob_to_regex(pattern):
    # fnmatch.translate always appends \\Z(?ms)
    # we skip these 7 characters
    return '^' + fnmatch.translate(pattern)[:-7] + '$'

def tablename_inclusion_filter(patterns):
    """Handle db.tbl as well as bare tbl patterns"""
    selection = []
    table_schema = InformationSchema.Table.table_schema
    table_name = InformationSchema.Table.table_name
    qualified_name = func.concat(table_schema,
                                 literal_column("'.'"),
                                 table_name)
    for pattern in patterns:
        if GLOB_CRE.search(pattern):
            selection.append(qualified_name.op('regexp')(glob_to_regex(pattern)))
        else:
            clause = []
            db, tbl = itemgetter(0,2)(pattern.rpartition('.'))
            if db:
                clause.append(table_schema == db)
            clause.append(table_name == tbl)
            selection.append(and_(*clause))

    return or_(*selection)

def tablename_exclusion_filter(patterns):
    """Handle db.tbl as well as bare tbl patterns"""
    selection = []
    table_schema = InformationSchema.Table.table_schema
    table_name = InformationSchema.Table.table_name
    qualified_name = func.concat(table_schema,
                                 literal_column("'.'"),
                                 table_name)
    for pattern in patterns:
        if GLOB_CRE.search(pattern):
            selection.append(qualified_name.op('not regexp')(glob_to_regex(pattern)))
        else:
            selection.append(not_(qualified_name == pattern))

    return and_(*selection)

def inclusion_filter(column, pattern_list):
    literals = []
    regexp = []

    for pattern in pattern_list:
        if GLOB_CRE.match(pattern):
            regexp.append(column.op('regexp')(glob_to_regex(pattern)))
        else:
            literals.append(pattern)
    return or_(column.in_(literals), *regexp)

def exclusion_filter(column, pattern_list):
    literals = []
    regexp = []

    for pattern in pattern_list:
        if GLOB_CRE.match(pattern):
            regexp.append(column.opn('not regexp')(glob_to_regex(pattern)))
        else:
            literals.append(pattern)
    return and_(~column.in_(literals), *regexp)

class InformationSchemaSchemata(DeclarativeBase):
    __tablename__ = 'schemata'
    __table_args__ = { 'schema' : 'information_schema' }

    schema_name = Column(String(64), primary_key=True)

class InformationSchemaTable(DeclarativeBase):
    __tablename__ = 'tables'
    __table_args__ = { 'schema' : 'information_schema' }

    table_schema = Column(String(64),
                          ForeignKey('information_schema.schemata.schema_name'),
                          primary_key=True)
    table_name = Column(String(64), primary_key=True)
    table_type = Column(String(64))
    engine = Column(String(64))
    data_length = Column(Integer)
    index_length = Column(Integer)
    table_comment = Column(String)

class InformationSchema(object):
    Schemata = InformationSchemaSchemata

    Table = InformationSchemaTable

    def __init__(self, mysql):
        self.mysql = mysql
        self.database_clauses = []
        self.table_clauses = []
        self.is_filtered = False

    def add_database_filter(self, clause):
        self.database_clauses.append(clause)
        #XXX: lru_cache not implemented
        #self.databases.clear()

    def add_table_filter(self, clause):
        self.table_clauses.append(clause)

    def all_databases(self):
        Schemata = self.Schemata
        query = self.mysql.session().query(Schemata.schema_name)
        return [name for name, in query.all()]

    def databases(self):
        query = self.mysql.session().query(self.Schemata.schema_name)
        try:
            return [name
                    for name, in query.filter(and_(*self.database_clauses)).all()]
        except DBAPIError, exc:
            raise exc.orig

    def data_size(self, name, additional_exclusions=()):
        data_length = InformationSchema.Table.data_length
        index_length = InformationSchema.Table.index_length
        sum_size_expr = func.COALESCE(func.SUM(data_length),
                                      literal_column('0')).label('table_size')

        query = self.mysql.session().query(sum_size_expr)
        if self.table_clauses:
            query = query.filter(*self.table_clauses)
        if additional_exclusions:
            clauses = tablename_exclusion_filter(*additional_exclusions)
            query = query.filter(*clauses)

        value = int(query.filter(self.Table.table_schema == name).scalar())
        return value

    def excluded_tables(self):
        # if no filtering clauses, nothing filtered
        if self.table_clauses:
            query = self.mysql.session().query(self.Table.table_schema,
                                               self.Table.table_name)
            query = query.filter(not_(or_(*self.table_clauses)))
            for name in self.databases():
                for schema, table in query.filter_by(table_schema=name).all():
                    yield schema, table

    def tables(self, schema_name):
        query = self.mysql.session().query(self.Table.table_schema,
                                           self.Table.table_name)
        if self.table_clauses:
            query = query.filter(*self.table_clauses)
        for schema, table in query.filter_by(table_schema=schema_name).all():
            yield schema, table

    def transactional_database(self, name):
        table_schema = self.Table.table_schema
        table_name = self.Table.table_name
        table_type = self.Table.table_type
        engine = self.Table.engine

        # SELECT COUNT(*)
        # FROM TABLES
        # WHERE TABLE_TYPE = 'BASE TABLE'
        # AND ENGINE NOT IN ( /* tranasactional engines */)
        # /* OTHER FILTER CLAUSES */
        # AND TABLE_SCHEMA = '${current_schema}'
        query = self.mysql.session().query(table_name, engine).filter(
                    and_(
                         table_type != literal_column("'VIEW'"),
                         ~engine.in_(self.transactional_engines()),
                         *self.table_clauses
                    )
                )
        # find at least one table without a transactional engine
        #results = query.filter(table_schema == name).all()
        tables = query.filter(table_schema == name).limit(5).all()
        if not tables:
            return []

        return [(table_name, engine) for table_name, engine in tables]

    def transactional_engines(self):
        # XXX: Technically we could treat other engines as transactional
        # based of the engines table, but this is not really safe in
        # current versions of MySQL - at least from the perspective
        # of being able to use mysqldump --single-transaction for
        # a consistent backup
        return ['InnoDB']

    def all_tables(self):
        query = self.mysql.session().query(self.Table)
        if self.table_clauses:
            query = query.filter(self.table_clauses)
        return query.all()

    def broken_views(self, schema_name):
        schema = self.Table.table_schema
        name = self.Table.table_name
        table_type = self.Table.table_type
        query = self.mysql.session().query(schema, name)
        if self.table_clauses:
            query = query.filter(and_(*self.table_clauses))
        query = query.filter_by(table_type='view', table_schema=schema_name)
        views = query.all()
        '''
        views = self.mysql.session().query(schema, name).filter(
                    and_(table_type == 'VIEW',
                         schema == schema_name,
                         *self.table_clauses)
                ).all()
        '''
        for table_schema, table_name in views:
            try:
                first(self.mysql.execute('SHOW FIELDS FROM `%s`.`%s`' %
                                   (table_schema, table_name)))
                warnings = self.mysql.warnings()
                for _, code, message in warnings:
                    if code in (1142, 1143, 1356, 1449):
                        yield table_schema, table_name, "[{0}] {1}".format(
                                    code, message
                              )
            except OperationalError, exc:
                if exc.orig.args[0] in (1142, 1143, 1356, 1449):
                    message = "[{0}] {1}".format(*exc.orig.args)
                    yield table_schema, table_name, message
                else:
                    raise

