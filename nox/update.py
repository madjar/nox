import click
import re
import subprocess

from enum import Enum
from bisect import bisect
from pkg_resources import parse_version
from pathlib import Path
from characteristic import attributes
from collections import defaultdict

def query(*args):
    return subprocess.check_output(['nix-store', '--query'] + list(args),
                                   universal_newlines=True)

@attributes(['full_name', 'path'], apply_with_init=False)
class NixPath:
    def __init__(self, path):
        self.path = path
        self.is_drv = self.path.endswith('.drv')
        name_slice_end = -4 if self.is_drv else None
        self.full_name = self.path[44:name_slice_end]

        m = re.search(r'-(\d.*)', self.full_name)
        if m:
            self.name = self.full_name[:m.start()]
            self.version = self.full_name[m.start()+1:]
            m = re.search(r'(\.[a-zA-Z][a-zA-Z0-9]*)+$', self.version)
            if m:
                self.extension = self.version[m.start()+1:]
                self.shortversion = self.version[:m.start()]
            else:
                self.extension = None
                self.shortversion = self.version
        else:
            self.name = self.full_name
            self.version = None
            self.extension = None
            self.shortversion = None

    def refs(self):
        return {NixPath(p) for p in query('--references', self.path).strip().split('\n')}

    def outputs(self):
        return set(query('--outputs', self.path).strip().split('\n'))


def current_system_drv(old_path):
    current_system = str(Path(old_path if old_path else '/run/current-system').resolve())
    return NixPath(current_system if current_system.endswith('.drv') else query('--deriver', current_system).strip())


def new_system_drv(new_path):
    if new_path:
      new_system = str(Path(new_path).resolve())
      return NixPath(new_system if new_system.endswith('.drv') else query('--deriver', new_system).strip())
    with subprocess.Popen(['nixos-rebuild', 'dry-run'],
                          stderr=subprocess.PIPE,
                          universal_newlines=True) as process:
        _, output = process.communicate()

    m = re.search(r'.*nixos-\d{2}.*', output)
    return m and NixPath(m.group().strip())


def display_path(pkg, bold):
    is_drv = pkg.is_drv
    name_slice_end = -4 if is_drv else None
    path = pkg.path
    return (path[:44] +
            click.style(path[44:name_slice_end], bold=bold) +
            (path[name_slice_end:] if is_drv else ''))

ChangeType = Enum('ChangeType', 'source fixed expression new version normal')

class DepsTree:
    def __init__(self, refs_tree):
        self.seen = set()
        self.refs_tree = refs_tree

    def show(self, pkg, opts, level=0):
        ctype = self.refs_tree[pkg.path][1]
        if pkg.path not in self.seen and (not opts['quiet'] or ctype != ChangeType.fixed):
            self.seen.add(pkg.path)
            click.echo('  '*level + display_path(pkg, bold=True) + ' : ', nl=False)
            if ctype == ChangeType.source:
                click.secho('Source file changed', bold=True)
            elif ctype == ChangeType.fixed:
                click.secho('Fixed-output derivation changed', bold=True)
            elif ctype == ChangeType.expression:
                click.secho('Expression changed', bold=True)
            elif ctype == ChangeType.new:
                click.secho('seems to be new', bold=True)
            elif ctype == ChangeType.version:
                opkg = self.refs_tree[pkg.path][2]
                if opkg.extension == pkg.extension:
                    click.secho('new version ({} -> {})'.format(opkg.shortversion, pkg.shortversion), bold=True)
                else:
                    click.secho('new version ({} -> {})'.format(opkg.version, pkg.version), bold=True)
            elif ctype == ChangeType.normal:
                click.echo()

            if self.refs_tree[pkg.path][0]:
                (removed_packages, recurse_packages) = self.refs_tree[pkg.path][3:]
                level=level+1
                for rpkg in removed_packages:
                    click.echo('  '*level + display_path(rpkg, bold=True) + ' : seems to be removed')
                for rpkg in recurse_packages:
                    self.show(rpkg, opts, level)
        elif not opts['quiet']:
            click.echo('  '*level + display_path(pkg, bold=False) + ' [...]')

def diff_pkgs(refs_tree, current_drv, new_drv, opts, level=0):
    if new_drv.path in refs_tree:
        return

    if not current_drv:
        refs_tree[new_drv.path] = (False, ChangeType.new, current_drv)
        return

    if not current_drv.is_drv or not new_drv.is_drv:
        refs_tree[new_drv.path] = (False, ChangeType.source, current_drv)
        return

    ctype = ChangeType.normal
    if current_drv.version != new_drv.version:
        if level > opts['max_level']:
          refs_tree[new_drv.path] = (False, ChangeType.version, current_drv)
          return
        else:
          ctype = ChangeType.version

    # Fixed-output derivation changed, but content didn't
    if current_drv.outputs() == new_drv.outputs():
        if level > opts['max_level']:
          refs_tree[new_drv.path] = (False, ChangeType.fixed, current_drv)
          return
        else:
          ctype = ChangeType.fixed

    old_pkgs = current_drv.refs()
    new_pkgs = new_drv.refs()

    if old_pkgs == new_pkgs:
        refs_tree[new_drv.path] = (False, ChangeType.expression if ctype == ChangeType.normal else ctype, current_drv);
        return

    removed_packages = old_pkgs - new_pkgs
    current_fullnames = defaultdict(list)
    current_names = defaultdict(list)
    for drv in removed_packages:
      current_fullnames[drv.full_name].append(drv)
      if drv.version:
        current_names[(drv.name, bool(drv.extension))].append((parse_version(drv.version), drv))
    for l in current_names.values():
        l.sort()

    recurse_packages = new_pkgs - old_pkgs
    for pkg in recurse_packages:
        previous = None
        pkgs = current_fullnames[pkg.full_name]
        if pkgs:
            previous = pkgs[0]
        elif pkg.version:
            versions = current_names[(pkg.name, bool(pkg.extension))]
            v = parse_version(pkg.version)
            prev = bisect(versions, (v, pkg)) - 1
            if prev >= 0:
                previous = versions[prev][1]

        if previous:
            current_fullnames[previous.full_name].remove(previous)
            if previous.version:
                current_names[(previous.name, bool(previous.extension))].remove((parse_version(previous.version), previous))
            removed_packages.discard(previous)

        diff_pkgs(refs_tree, previous, pkg, opts, level + 1)

    refs_tree[new_drv.path] = (True, ctype, current_drv, sorted(removed_packages), sorted(recurse_packages))


@click.command()
@click.option('--max-level', default=0, type=click.INT)
@click.option('--quiet', default=False, is_flag=True)
@click.argument('old-path', default='', type=click.Path(exists=True))
@click.argument('new-path', default='', type=click.Path(exists=True))
def main(old_path, new_path, **opts):
    new_drv = new_system_drv(new_path)
    if not new_drv:
        click.echo('No system updates')
        return

    current_drv = current_system_drv(old_path)

    refs_tree = {}
    diff_pkgs(refs_tree, current_drv, new_drv, opts)
    tree = DepsTree(refs_tree)
    tree.show(new_drv, opts)

# TODO : option -> display only thing to install, deps tree without
# repetition, deps tree with omission of repeated paths, or full tree
