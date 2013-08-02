from jinja2 import Environment, PackageLoader

def format_binlog_info(filename, position, source):
    return render_template('replication.change_master',
                           name=filename,
                           position=position,
                           source=source)

def render_template(name, **kwargs):
    """Load a named template and render it with ``kwargs``

    :returns: text of rendered template
    """
    env = Environment(loader=PackageLoader(__name__, 'templates'),
                      trim_blocks=True,
                      lstrip_blocks=True)
    template = env.get_template(name)
    return template.render(**kwargs)
