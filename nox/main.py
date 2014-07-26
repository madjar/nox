import collections
import json
import subprocess

import click
from dogpile.cache import make_region

region = make_region().configure(
    'dogpile.cache.dbm',
    expiration_time=3600,
    arguments={'filename': '/tmp/nox.dbm'}
)


@region.cache_on_arguments()
def nix_packages_json():
    output = subprocess.check_output(['nix-env', '-qa', '--json'],
                                     universal_newlines=True)
    return json.loads(output)


Package = collections.namedtuple('Package', 'attribute name description')


def all_packages():
    return (Package(attr, v['name'], v['meta'].get('description', ''))
            for attr, v in nix_packages_json().items())


@click.command()
@click.argument('query', default='')
def search(query):
    """Search a package in nix"""
    results = [p for p in all_packages()
               if any(query in s for s in p)]
    results.sort()
    for i, p in enumerate(results, 1):
        line = '{} {} ({})\n    {}'.format(
            click.style(str(i), fg='black', bg='yellow'),
            click.style(p.name, bold=True),
            click.style(p.attribute, dim=True),
            click.style(p.description))
        click.echo(line)

    if results:
        to_install = click.prompt('Package to install', type=int)
        package = results[to_install - 1]
        subprocess.check_call(['nix-env', '-iA', package.attribute])
