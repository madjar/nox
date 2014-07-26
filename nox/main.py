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
def nix_packages():
    output = subprocess.check_output(['nix-env', '-qa', '--json'],
                                     universal_newlines=True)
    return json.loads(output)


@click.command()
@click.argument('package', default='')
def search(package):
    """Search a package in nix"""
    for attr, v in nix_packages().items():
        name = v['name']
        desc = v['meta'].get('description', '')
        if not any(package in s for s in (attr, name, desc)):
            continue
        line = '{} ({})\n  {}'.format(
            click.style(name, bold=True),
            click.style(attr, dim=True),
            click.style(desc))
        click.echo(line)
