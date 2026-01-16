import os
import sys
import tempfile
import subprocess
import re
from pathlib import Path

import click
import requests

from .nixpkgs_repo import get_repo, at_given_sha, get_build_commands, packages_for_sha, tests_for_sha


@at_given_sha
def build_sha(path, buildables, extra_args=[], dry_run=False):
    """Build the given package attributes in the given nixpkgs path"""
    if not buildables:
        click.echo('Nothing changed')
        return

    canonical_path = str(Path(path).resolve())
    result_dir = tempfile.mkdtemp(prefix='nox-review-')
    click.echo('Building in {}: {}'.format(click.style(result_dir, bold=True),
                                           click.style(' '.join(s.attr for s in buildables), bold=True)))

    for command in get_build_commands(buildables, extra_args=extra_args+["-I", "nixpkgs="+canonical_path]):
        click.echo('Invoking {}'.format(' '.join(command)))

        if not dry_run:
            try:
                subprocess.check_call(command, cwd=result_dir)
            except subprocess.CalledProcessError:
                click.secho('The invocation of "{}" failed'.format(' '.join(command)), fg='red')
                sys.exit(1)
            click.echo('Result in {}'.format(click.style(result_dir, bold=True)))
            subprocess.check_call(['ls', '-l', result_dir])


def build_difference(old_sha, new_sha, extra_args=[], with_tests=False, disable_test_blacklist=False, dry_run=False):
    click.echo("Listing old packages...")
    before = packages_for_sha(old_sha)
    if with_tests:
        click.echo("Listing old tests...")
        before |= tests_for_sha(old_sha, disable_test_blacklist)
    click.echo("Listing new packages...")
    after = packages_for_sha(new_sha)
    if with_tests:
        click.echo("Listing new tests...")
        after |= tests_for_sha(new_sha, disable_test_blacklist)
    build_sha(new_sha, after-before, extra_args, dry_run)


def setup_nixpkgs_config(f):
    def _(*args, **kwargs):
        with tempfile.NamedTemporaryFile() as cfg:
            cfg.write(b"pkgs: {}")
            cfg.flush()
            os.environ['NIXPKGS_CONFIG'] = cfg.name
            f(*args, **kwargs)
    return _


@click.group()
@click.option('--keep-going', '-k', is_flag=True, help='Keep going in case of failed builds')
@click.option('--dry-run', is_flag=True, help="Don't actually build packages, just print the commands that would have been run")
@click.option('--with-tests', is_flag=True, help="Also rebuild affected NixOS tests")
@click.option('--all-tests', is_flag=True, help="Do not blacklist tests known to be false positives")
@click.pass_context
def cli(ctx, keep_going, dry_run, with_tests, all_tests):
    """Review a change by building the touched commits"""
    ctx.obj = {'extra-args': []}
    if keep_going:
        ctx.obj['extra-args'].append('--keep-going')
    ctx.obj['dry_run'] = dry_run
    ctx.obj['tests'] = with_tests
    ctx.obj['no-blacklist'] = all_tests


@cli.command('wip', short_help='difference between working tree and a commit')
@click.option('--against', default='HEAD')
@click.pass_context
@setup_nixpkgs_config
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

    build_difference(sha, None, extra_args=ctx.obj['extra-args'], with_tests=ctx.obj["tests"], disable_test_blacklist=ctx.obj["no-blacklist"], dry_run=ctx.obj['dry_run'])


@cli.command('pr', short_help='changes in a pull request')
@click.option('--slug', default=None, help='The GitHub "slug" of the repository in the from of owner_name/repo_name.')
@click.option('--token', help='The GitHub API token to use.')
@click.option('--merge/--no-merge', default=True, help='Merge the PR against its base.')
@click.argument('pr', type=click.STRING)
@click.pass_context
@setup_nixpkgs_config
def review_pr(ctx, slug, token, merge, pr):
    """Build the changes induced by the given pull request"""

    # Allow the 'pr' parameter to be either the numerical ID or an URL to the PR on GitHub.
    # Also if it's an URL, parse the proper --slug argument from that.
    m = re.match('^(?:https?://(?:www\.)?github\.com/([^/]+/[^/]+)/pull/)?([0-9]+)$', pr, re.IGNORECASE)
    if not m:
        click.echo("Error: parameter to 'nox-review pr' must be a valid pull request number or URL.")
        sys.exit(1)
    pr = m[2]
    if m[1]:
        if slug:
            click.echo("Error: '--slug' option can't be used together with a pull request URL.")
            sys.exit(1)
        slug = m[1]
    elif not slug:
        slug = 'NixOS/nixpkgs'

    pr_url = 'https://api.github.com/repos/{}/pulls/{}'.format(slug, pr)
    headers = {}
    if token:
        headers['Authorization'] = 'token {}'.format(token)
    request = requests.get(pr_url, headers=headers)
    if request.status_code == 403 and request.headers['X-RateLimit-Remaining'] == '0':
        click.secho('You have exceeded the GitHub API rate limit. Try again in about an hour.')
        if not token:
            click.secho('Or try running this again, providing an access token:')
            click.secho('$ nox-review pr --token=YOUR_TOKEN_HERE {}'.format(pr))
        sys.exit(1)
    payload = request.json()
    click.echo('=== Reviewing PR {} : {}'.format(
               click.style(pr, bold=True),
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

    if merge:
        click.echo('==> Fetching extra history for merging')
        depth = 10
        while not repo.merge_base(head, base):
            repo.fetch(base_refspec, depth=depth)
            repo.fetch(head_refspec, depth=depth)
            depth *= 2

        # It looks like this isn't enough for a merge, so we fetch more
        repo.fetch(base_refspec, depth=depth)

        click.echo('==> Merging PR into base')

        repo.checkout(base)
        repo.git(['merge', head, '--no-ff', '-qm', 'Nox automatic merge'])
        merged = repo.sha('HEAD')

        old = base
        new = merged

    else:
        commits = requests.get(payload['commits_url'], headers=headers).json()
        old = commits[-1]['parents'][0]['sha']
        new = payload['head']['sha']

    build_difference(old, new, extra_args=ctx.obj['extra-args'], with_tests=ctx.obj["tests"], disable_test_blacklist=ctx.obj["no-blacklist"], dry_run=ctx.obj['dry_run'])
