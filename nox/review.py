import sys
import tempfile
import subprocess
from pathlib import Path

import click
import requests

from .nixpkgs_repo import get_repo, packages_for_sha

def to_sha(commit):
    """Translate a git commit name in the current dir to a sha"""
    output = subprocess.check_output(['git', 'rev-parse', '--verify', commit])
    return output.decode().strip()

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
    repo = get_repo()
    repo.checkout(sha)
    build_in_path(attrs, repo.path)


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
    click.echo('=== Reviewing PR {} : {}'.format(click.style(str(pr), bold=True),
                                             click.style(payload['title'], bold=True)))

    base_ref = payload['base']['ref']

    repo = get_repo()

    click.echo('==> Fetching base ({})'.format(base_ref))
    base_refspec = 'heads/{}'.format(payload['base']['ref'])
    repo.fetch(base_refspec)
    base = repo.sha('FETCH_HEAD')

    click.echo('==> Fetching PR')
    head_refspec = 'pull/{}/head'.format(pr)
    repo.fetch(head_refspec)
    head = repo.sha('FETCH_HEAD')

    click.echo('==> Fetching extra history for merging')
    depth = 10
    while not repo.merge_base(head, base):
        repo.fetch(base_refspec, depth=depth)
        repo.fetch(head_refspec, depth=depth)
        depth *=2

    click.echo('==> Merging PR into base')
    repo.checkout(base)
    repo.git(['merge', head, '-qm', 'Nox automatic merge'])
    merged = repo.sha('HEAD')

    attrs = differences(packages_for_sha(base),
                        packages_for_sha(merged))

    build_sha(attrs, merged)
