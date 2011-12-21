#
# Jinja2 custom filters. In order to add a new one, just define a function and
# add it to the environment in register_filters
#

def format_datetime(format="%d %b %Y at %H:%M"):
    def _format_datetime(value):
        return value.strftime(format)
    return _format_datetime


def register_filters(env, site):

    env.filters['datetime'] = format_datetime(site.config['dateformat'])
