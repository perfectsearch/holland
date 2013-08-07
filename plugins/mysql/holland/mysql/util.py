from jinja2 import Environment, PackageLoader

def format_binlog_info(filename, position, source):
    return render_template('replication.change_master',
                           dict(name=filename,
                                position=position,
                                source=source))

def render_template(template_name, params):
    """Load a named template and render it with ``kwargs``

    :returns: text of rendered template
    """
    env = Environment(loader=PackageLoader(__name__, 'templates'),
                      trim_blocks=True)
    template = env.get_template(template_name)
    return template.render(**params)
