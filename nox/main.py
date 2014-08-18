import os
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


def nix_packages_json():
    click.echo('Refreshing cache')
    output = subprocess.check_output(['nix-env', '-qa', '--json'],
                                     universal_newlines=True)
    return json.loads(output)


Package = collections.namedtuple('Package', 'attribute name description')


def key_for_path(path):
    try:
        manifest = os.path.join(path, 'manifest.nix')
        with open(manifest) as f:
            return f.read()
    except FileNotFoundError:
        pass
    if os.path.exists(os.path.join(path, '.git')):
        return subprocess.check_output('git rev-parse --verify HEAD'.split(),
                                       cwd=path)
    click.echo('Could not find a version indicator for {}'.format(path))
    return None


def all_packages():
    defexpr = os.path.expanduser('~/.nix-defexpr/')
    paths = os.listdir(defexpr)
    key = str({p: key_for_path(defexpr + p) for p in paths})
    packages_json = region.get_or_create(key, nix_packages_json)
    return (Package(attr, v['name'], v['meta'].get('description', ''))
            for attr, v in packages_json.items())


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
        def parse_input(inp):
            if inp[0] == 's':
                action = 'shell'
                inp = inp[1:]
            else:
                action = 'install'
            packages = [results[int(i) - 1] for i in inp.split()]
            return action, packages

        action, packages = click.prompt('Packages to install',
                                        value_proc=parse_input)
        attributes = [p.attribute for p in packages]
        if action == 'install':
            subprocess.check_call(['nix-env', '-iA'] + attributes)
        elif action == 'shell':
            attributes = [a[len('nixpkgs.'):] for a in attributes]
            subprocess.check_call(['nix-shell', '-p'] + attributes)
