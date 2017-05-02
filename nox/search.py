import os
import collections
import json
import subprocess
import re

import click

from .cache import region


class NixEvalError(Exception):
    pass


def nix_packages_json():
    click.echo('Refreshing cache')
    try:
        output = subprocess.check_output(['nix-env', '-qa', '--json', '--show-trace'],
                                         universal_newlines=True)
    except subprocess.CalledProcessError as e:
        raise NixEvalError from e
    return json.loads(output)


Package = collections.namedtuple('Package', 'attribute name description')


def key_for_path(path):
    try:
        manifest = os.path.join(path, 'manifest.nix')
        with open(manifest) as f:
            return f.read()
    except (FileNotFoundError, NotADirectoryError):
        pass
    if os.path.exists(os.path.join(path, '.git')):
        return subprocess.check_output('git rev-parse --verify HEAD'.split(),
                                       cwd=path)
    click.echo('Warning: could not find a version indicator for {}'.format(path))
    return None


def all_packages(force_refresh=False):
    defexpr = os.path.expanduser('~/.nix-defexpr/')
    paths = os.listdir(defexpr)
    key = str({p: key_for_path(defexpr + p) for p in paths})

    if force_refresh:
        region.delete(key)

    packages_json = region.get_or_create(key, nix_packages_json)
    return (Package(attr, v['name'], v['meta'].get('description', ''))
            for attr, v in packages_json.items())


@click.command()
@click.argument('query', default='')
@click.option('--force-refresh', is_flag=True)
def main(query, force_refresh):
    """Search a package in nix"""
    query = re.compile(query, re.IGNORECASE)

    try:
        results = [p for p in all_packages()
                   if any((query.search(s) for s in p))]
    except NixEvalError:
        raise click.ClickException('An error occured while running nix (displayed above). Maybe the nixpkgs eval is broken.')
    results.sort()
    for p in results:
        line = '{} ({})\n    {}'.format(
            click.style(p.name, bold=True, fg="green"),
            click.style(p.attribute, dim=True),
            click.style(p.description.replace("\n", "\n    ")))
        click.echo(line)
