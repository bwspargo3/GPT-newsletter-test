
from jinja2 import Environment,FileSystemLoader
def render(items):
    env=Environment(loader=FileSystemLoader('templates'))
    return env.get_template('daily.html').render(items=items)
