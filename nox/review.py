import sys
import tempfile
import subprocess
from pathlib import Path

import click
import requests

from .cache import region


def to_sha(commit):
    """Translate a git commit name in the current dir to a sha"""
    output = subprocess.check_output(['git', 'rev-parse', '--verify', commit])
    return output.decode().strip()


def packages(path):
    """List all nix packages in the given path"""
    output = subprocess.check_output(['nix-env', '-f', path, '-qaP', '--drv-path'],
                                     universal_newlines=True)
    return set(output.split('\n'))


@region.cache_on_arguments()
def packages_for_sha(sha):
    """List all nix packages for the given sha"""
    nixpkgs = get_nixpkgs()
    subprocess.check_call(['git', 'checkout', '--quiet', sha], cwd=nixpkgs)
    return packages(nixpkgs)


def build_in_path(attrs, path):
    """Build the given package attributes in the given nixpkgs path"""
    if not attrs:
        click.echo('Nothing changed')
        return

    canonical_path = str(Path(path).resolve())
    result_dir = tempfile.mkdtemp(prefix='nox-review-')
    click.echo('Building in {}: {}'.format(click.style(result_dir, bold=True),
                                           click.style(' '.join(attrs), bold=True)))
    command = ['nix-build']
    for a in attrs:
        command.append('-A')
        command.append(a)
    command.append(canonical_path)

    try:
        subprocess.check_call(command, cwd=result_dir)
    except subprocess.CalledProcessError:
        click.secho('The invocation of "{}" failed'.format(' '.join(command)), fg='red')
        sys.exit(1)
    click.echo('Result in {}'.format(click.style(result_dir, bold=True)))
    subprocess.check_call(['ls', '-l', result_dir])


def build_sha(attrs, sha):
    """Build the given package attributs for a given sha"""
    nixpkgs = get_nixpkgs()
    subprocess.check_call(['git', 'checkout', '--quiet', sha], cwd=nixpkgs)
    build_in_path(attrs, nixpkgs)


def get_nixpkgs():
    """Get nox's dedicated nixpkgs clone"""
    # TODO: provide some feedback on what happens in git
    nox_dir = Path(click.get_app_dir('nox', force_posix=True))
    if not nox_dir.exists():
        nox_dir.mkdir()

    nixpkgs = nox_dir / 'nixpkgs'
    if not nixpkgs.exists():
        click.echo('Cloning nixpkgs')
        subprocess.check_call(['git', 'init', '--quiet', str(nixpkgs)])
        subprocess.check_call(['git', 'remote', 'add', 'origin', 'https://github.com/NixOS/nixpkgs.git'],
                              cwd=str(nixpkgs))

    # Fetch nixpkgs master
    subprocess.check_call(['git', 'fetch', 'origin', 'master', '--quiet'], cwd=str(nixpkgs))

    # Fetch the pull requests
    subprocess.check_call(['git', 'fetch', 'origin', '--quiet', '+refs/pull/*/head:refs/remotes/origin/pr/*'],
                          cwd=str(nixpkgs))
    return str(nixpkgs)


def differences(old, new):
    """Return set of attributes that changed between two packages list"""
    raw = new - old
    # Only keep the attribute name
    return {l.split()[0] for l in raw}


@click.group()
def cli():
    """Review a change by building the touched commits"""
    pass


@cli.command(short_help='difference between working tree and a commit')
@click.option('--against', default='HEAD')
def wip(against):
    """Build in the current dir the packages that different from AGAINST (default to HEAD)"""
    attrs = differences(packages_for_sha(to_sha(against)),
                        packages('.'))

    build_in_path(attrs, '.')


@cli.command('pr', short_help='changes in a pull request')
@click.argument('pr', type=click.INT)
def review_pr(pr):
    """Build the changes induced by the given pull request"""
    payload = requests.get('https://api.github.com/repos/NixOS/nixpkgs/pulls/{}'.format(pr)).json()
    click.echo('Reviewing PR {} : {}'.format(click.style(str(pr), bold=True),
                                             click.style(payload['title'], bold=True)))
    head = payload['head']['sha']
    base = payload['base']['sha']

    # Determine the root of the pull request
    root = subprocess.check_output(['git', 'merge-base', head, base], cwd=get_nixpkgs()).decode().strip()

    attrs = differences(packages_for_sha(root),
                        packages_for_sha(head))

    build_sha(attrs, head)
