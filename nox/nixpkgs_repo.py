import os
import subprocess
from pathlib import Path

from .cache import region

import click


class Repo:
    def __init__(self):
        nox_dir = Path(click.get_app_dir('nox', force_posix=True))
        if not nox_dir.exists():
            nox_dir.mkdir()

        nixpkgs = nox_dir / 'nixpkgs'
        self.path = str(nixpkgs)

        if not nixpkgs.exists():
            click.echo('==> Creating nixpkgs repo in {}'.format(nixpkgs))
            self.git(['init', '--quiet', self.path], cwd=False)
            self.git('remote add origin https://github.com/NixOS/nixpkgs.git')
            self.git('config user.email nox@example.com')
            self.git('config user.name nox')


        if (Path.cwd() / '.git').exists():
            git_version = self.git('version', output=True).strip()
            if git_version >= 'git version 2':
                click.echo("==> We're in a git repo, trying to fetch it")

                self.git(['fetch', str(Path.cwd()), '--update-shallow', '--quiet'])
            else:
                click.echo("==> Old version of git detected ({}, maybe on travis),"
                " not trying to fetch from local, fetch 50 commits from master"
                " instead".format(git_version))
                self.git('fetch origin master --depth 50')

    def git(self, command, *args, cwd=None, output=False, **kwargs):
        if cwd is None:
            cwd = self.path
        elif cwd is False:
            cwd = None
        if isinstance(command, str):
            command = command.split()
        command.insert(0, 'git')
        f = subprocess.check_output if output else subprocess.check_call
        return f(command, *args, cwd=cwd, universal_newlines=output, **kwargs)




    def checkout(self, sha):
        self.git(['checkout', '--quiet', sha])

    def sha(self, ref):
        return self.git(['rev-parse', '--verify', ref], output=True).strip()

    def fetch(self, ref, depth=1):
        return self.git(['fetch', '--depth', str(depth), '--quiet',
            'origin', '+refs/{}'.format(ref)])

    def merge_base(self, first, second):
        try:
            return self.git(['merge-base', first, second], output=True).strip()
        except subprocess.CalledProcessError:
            return None

_repo = None

def get_repo():
    global _repo
    if not _repo:
        _repo = Repo()
    return _repo


def packages(path):
    """List all nix packages in the repo, as a set"""
    output = subprocess.check_output(['nix-env', '-f', path, '-qaP', '--out-path', '--show-trace'],
                                     universal_newlines=True)
    return set(output.split('\n'))


@region.cache_on_arguments()
def packages_for_sha(sha):
    """List all nix packages for the given sha"""
    repo = get_repo()
    repo.checkout(sha)
    return packages(repo.path)
