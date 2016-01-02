import sys
import tempfile
import subprocess
from pathlib import Path

import click
import requests

from .nixpkgs_repo import get_repo, packages, packages_for_sha


def build_in_path(args, attrs, path):
    """Build the given package attributes in the given nixpkgs path"""
    if not attrs:
        click.echo('Nothing changed')
        return

    canonical_path = str(Path(path).resolve())
    result_dir = tempfile.mkdtemp(prefix='nox-review-')
    click.echo('Building in {}: {}'.format(click.style(result_dir, bold=True),
                                           click.style(' '.join(attrs), bold=True)))
    command = ['nix-build']
    command += args
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


def build_sha(args, attrs, sha):
    """Build the given package attributs for a given sha"""
    repo = get_repo()
    repo.checkout(sha)
    build_in_path(args, attrs, repo.path)


def differences(old, new):
    """Return set of attributes that changed between two packages list"""
    raw = new - old
    # Only keep the attribute name
    return {l.split()[0] for l in raw}


@click.group()
@click.option('--keep-going', '-k', is_flag=True, help='Keep going in case of failed builds')
@click.pass_context
def cli(ctx, keep_going):
    """Review a change by building the touched commits"""
    if keep_going:
        ctx.obj = {'extra-args': ['--keep-going']}
    else:
        ctx.obj = {'extra-args': []}


@cli.command(short_help='difference between working tree and a commit')
@click.option('--against', default='HEAD')
@click.pass_context
def wip(ctx, against):
    """Build in the current dir the packages that different from AGAINST (default to HEAD)"""
    if not Path('default.nix').exists():
        click.secho('"nox-review wip" must be run in a nix repository.', fg='red')
        return

    dirty_working_tree = subprocess.call('git diff --quiet --ignore-submodules HEAD'.split())

    if not dirty_working_tree:
        if against == 'HEAD':
            click.secho('No uncommit changes. Did you mean to use the "--against" option?')
            return

    sha = subprocess.check_output(['git', 'rev-parse', '--verify', against]).decode().strip()

    attrs = differences(packages_for_sha(sha),
                        packages('.'))

    build_in_path(ctx.obj['extra-args'], attrs, '.')


@cli.command('pr', short_help='changes in a pull request')
@click.argument('pr', type=click.INT)
@click.pass_context
def review_pr(ctx, pr):
    """Build the changes induced by the given pull request"""
    pr_url = 'https://api.github.com/repos/NixOS/nixpkgs/pulls/{}'.format(pr)
    payload = requests.get(pr_url).json()
    click.echo('=== Reviewing PR {} : {}'.format(
               click.style(str(pr), bold=True),
               click.style(payload.get('title', '(n/a)'), bold=True)))

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

    # It looks like this isn't enough for a merge, so we fetch more
    repo.fetch(base_refspec, depth=depth)

    click.echo('==> Merging PR into base')
    repo.checkout(base)
    repo.git(['merge', head, '-qm', 'Nox automatic merge'])
    merged = repo.sha('HEAD')

    attrs = differences(packages_for_sha(base),
                        packages_for_sha(merged))

    build_sha(ctx.obj['extra-args'], attrs, merged)
