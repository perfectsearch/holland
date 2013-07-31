from jinja2 import Environment, PackageLoader

def format_binlog_info(filename, position, source):
    env = Environment(loader=PackageLoader(__name__, 'templates'))
    template = env.get_template('replication.change_master')
    return template.render(name=filename, position=position, source=source)
