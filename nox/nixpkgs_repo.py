import os
import subprocess
import json
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fnmatch import fnmatch

from .cache import region

import click
import psutil


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
        # suppress gpg prompt when git command tries to create/modify commit
        command = ['git', '-c', 'commit.gpgSign=false'] + command
        f = subprocess.check_output if output else subprocess.check_call
        return f(command, *args, cwd=cwd, universal_newlines=output, **kwargs)

    def checkout(self, sha):
        self.git(['checkout', '-f', '--quiet', sha])

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


class Buildable:
    """
    attr (str): attribute name under which the buildable can be built
    path (str or tuple of them): for example <nixpkgs>, a list can be used to
        pass other arguments like --argstr foo bar
    hash: anything which contains the drvPath for example
    __slots__ = "path", "attr", "extra_args", "hash"
    """
    def __init__(self, attr, hash, path="<nixpkgs>"):
        self.attr = attr
        self.hash = hash
        self.path = path

    def __eq__(self, other):
        return hash(self) == hash(other)

    def __hash__(self):
        return hash(self.hash)

    @property
    def path_args(self):
        if isinstance(self.path, str):
            return (self.path, )
        return self.path

    def __repr__(self):
        return "Buildable(attr={!r}, hash={!r}, path={!r})".format(self.attr, self.hash, self.path_args)


def get_build_commands(buildables, program="nix-build", extra_args=[]):
    """ Get the appropriate commands to use to build the given buildables """
    prefix = [program]
    prefix += extra_args
    path_to_cmd = defaultdict(lambda *x: prefix[:])
    for b in buildables:
        command = path_to_cmd[b.path_args]
        command.append('-A')
        command.append(b.attr)
    return [command + list(path) for path, command in path_to_cmd.items()]


def at_given_sha(f):
    """decorator which calls the wrappee with the path of nixpkgs at the given sha

    Turns a function path -> 'a into a function sha -> 'a.
    If the sha passed is None, passes the current directory as argument.
    """
    def _wrapped(sha, *args, **kwargs):
        if sha is not None:
            repo = get_repo()
            repo.checkout(sha)
            path = repo.path
        else:
            path = os.getcwd()
        return f(path, *args, **kwargs)
    _wrapped.__name__ = f.__name__
    return _wrapped


def cache_on_not_None(f):
    """like region.cache_on_argument() but does not cache if the key starts None"""
    wf = region.cache_on_arguments()(f)
    def _wrapped(arg, *args):
        if arg is None:
            return f(arg, *args)
        return wf(arg, *args)
    _wrapped.__name__ = f.__name__
    return _wrapped


@cache_on_not_None
@at_given_sha
def packages_for_sha(path):
    """List all nix packages in the repo, as a set of buildables"""
    output = subprocess.check_output(['nix-env', '-f', path, '-qaP',
        '--out-path', '--show-trace'], universal_newlines=True)
    return {Buildable(attr, hash) for attr, hash in
            map(lambda line: line.split(" ", 1), output.splitlines())}


enumerate_tests = str(Path(__file__).parent / "enumerate_tests.nix")


@cache_on_not_None
@at_given_sha
def tests_for_sha(path, disable_blacklist=False):
    """List all tests wich evaluate in the repo, as a set of (attr, drvPath)"""
    num_jobs = 32
    # at this size, each job takes 1~1.7 GB mem
    max_workers = max(1, psutil.virtual_memory().available//(1700*1024*1024))
    # a job is also cpu hungry
    try:
        max_workers = min(max_workers, os.cpu_count())
    except: pass

    def eval(i):
        output = subprocess.check_output(['nix-instantiate', '--eval',
            '--json', '--strict', '-I', "nixpkgs="+str(path), enumerate_tests,
            '--arg', "jobIndex", str(i), '--arg', 'numJobs', str(num_jobs),
            '--arg', 'disableBlacklist', str(disable_blacklist).lower(),
            '--show-trace'], universal_newlines=True)
        return json.loads(output)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        evals = executor.map(eval, range(num_jobs))

    path = ("<nixpkgs/nixos/release.nix>", "--arg", "supportedSystems", "[builtins.currentSystem]")
    attrs = set()
    for partial in evals:
        for test in partial:
            b = Buildable(test["attr"], test["drv"], path=path)
            attrs.add(b)

    return attrs

