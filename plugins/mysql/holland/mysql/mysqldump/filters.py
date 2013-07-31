"""
holland.mysql.mysqldump.filters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""
from holland.mysql.schema import (inclusion_filter,
                                  exclusion_filter,
                                  tablename_inclusion_filter,
                                  tablename_exclusion_filter)

def apply_filters(schema, config):
    """Add filters to an InformationSchema object"""
    schema_name = schema.Schemata.schema_name
    engine = schema.Table.engine

    if config['databases'] != ['*']:
        filter = inclusion_filter(schema_name, config['databases'])
        schema.add_database_filter(filter)

    if config['exclude-databases']:
        filter = exclusion_filter(schema_name, config['exclude-databases'])
        schema.add_database_filter(filter)

    if config['tables'] != ['*']:
        filter = tablename_inclusion_filter(config['tables'])
        schema.add_table_filter(filter)

    if config['exclude-tables']:
        filter = tablename_exclusion_filter(config['exclude-tables'])
        schema.add_table_filter(filter)

    if config['ignore-tables']:
        filter = tablename_exclusion_filter(config['ignore-tables'])
        schema.add_table_filter(filter)

    if config['engines'] != ['*']:
        schema.add_table_filter(inclusion_filter(engine, config['engines']))

    if config['exclude-engines']:
        filter = exclusion_filter(engine, config['exclude-engines'])
        schema.add_table_filter(filter)

