import subprocess
from pathlib import Path

from .cache import region

import click


class Repo:
    def __init__(self):
        # TODO: provide some feedback on what happens in git
        nox_dir = Path(click.get_app_dir('nox', force_posix=True))
        if not nox_dir.exists():
            nox_dir.mkdir()

        nixpkgs = nox_dir / 'nixpkgs'
        self.path = str(nixpkgs)

        if not nixpkgs.exists():
            click.echo('Creating nixpkgs repo in {}'.format(nixpkgs))
            self._git(['init', '--quiet', self.path], cwd=False)
            self._git('remote add origin https://github.com/NixOS/nixpkgs.git')

        # Fetch nixpkgs master
        self._git('fetch origin master --quiet')

        # Fetch the pull requests
        self._git('fetch origin --quiet +refs/pull/*/head:refs/remotes/origin/pr/*')

    def _git(self, command, *args, cwd=None, **kwargs):
        if cwd is None:
            cwd = self.path
        elif cwd is False:
            cwd = None
        if isinstance(command, str):
            command = command.split()
        command.insert(0, 'git')
        subprocess.check_call(command, *args, cwd=cwd, **kwargs)


    def packages(self):
        """List all nix packages in the repo, as a set"""
        output = subprocess.check_output(['nix-env', '-f', path, '-qaP', '--drv-path'],
                                         universal_newlines=True)
        return set(output.split('\n'))

    def checkout(self, sha):
        self._git(['checkout', '--quiet', sha])


_repo = None

def get_repo():
    global _repo
    if not _repo:
        _repo = Repo()
    return _repo


@region.cache_on_arguments()
def packages_for_sha(self, sha):
    """List all nix packages for the given sha"""
    repo = get_repo()
    repo.checkout(sha)
    return repo.packages()
