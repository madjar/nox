import click
import collections
import re
import subprocess

from pathlib import Path
from characteristic import attributes
from .cache import region


@region.cache_on_arguments()
def query(*args):
    return subprocess.check_output(['nix-store', '--query'] + list(args),
                                   universal_newlines=True)


def requisites(drv):
    return set(query('--requisites', drv).strip().split('\n'))


def is_blacklisted(path):
    # TODO look in the derivation to known if it's a fetchurl
    # TODO : check what those 'stage-*' are
    return any(s in path for s in ('.tar.', '.tgz', '.zip', 'stage-1-init', 'stage-2-init', '.patch'))


@attributes(['path'], apply_with_init=False)
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
        else:
            self.name = self.full_name
            self.version = None

    def reqs(self):
        result = requisites(self.path)
        result.discard(self.path)
        return {NixPath(p) for p in result if not is_blacklisted(p)}

    def refs(self):
        return set(query('--references', self.path).strip().split('\n'))


def current_system_drv():
    current_system = Path('/run/current-system').resolve()
    return NixPath(query('--deriver', str(current_system)).strip())


def new_system_drv():
    with subprocess.Popen(['nixos-rebuild', 'dry-run'],
                          stderr=subprocess.PIPE,
                          universal_newlines=True) as process:
        _, output = process.communicate()

    m = re.search(r'.*nixos-\d{2}.*', output)
    return m and NixPath(m.group().strip())


def display_path(path, bold):
    is_drv = path.endswith('.drv')
    name_slice_end = -4 if is_drv else None
    return (path[:44] +
            click.style(path[44:name_slice_end], bold=bold) +
            (path[name_slice_end:] if is_drv else ''))


class DepsTree:
    def __init__(self, changed_refs_tree):
        self.seen = set()
        self.changed_refs_tree = changed_refs_tree

    def show(self, pkg, level=0):
        click.echo('  '*level + display_path(pkg, bold=pkg not in self.seen), nl=False)
        if pkg not in self.seen:
            click.echo()
            self.seen.add(pkg)
            for ref in self.changed_refs_tree[pkg]:
                self.show(ref, level+1)
        else:
            click.echo(' [...]')


@click.command()
def main():
    new_drv = new_system_drv()
    if not new_drv:
        click.echo('No system updates')
        return

    current_drv = current_system_drv()

    # must differenciate firefox-31 and firefox
    current_names = {(drv.name, bool(drv.version)): drv for drv in current_drv.reqs()
                     if not is_blacklisted(drv.path)}
    changed_refs_tree = collections.defaultdict(list)

    new_packages, new_versions, changed_expressions, rest = [], [], [], []

    for pkg in new_drv.reqs() - current_drv.reqs():
        previous = current_names.get((pkg.name, bool(pkg.version)))
        if not previous:
            new_packages.append(pkg)
            continue

        changed_refs = pkg.refs() - previous.refs()
        for r in changed_refs:
            changed_refs_tree[r].append(pkg.path)

        if previous.version != pkg.version:
            new_versions.append((pkg, previous.version))
        elif previous.refs() == pkg.refs():
            changed_expressions.append(pkg)
        else:
            rest.append(pkg)

    new_versions.sort(key=lambda x: x[0].name)
    for l in (new_packages, changed_expressions, rest):
        l.sort(key=lambda p: p.name)

    tree = DepsTree(changed_refs_tree)

    for pkg in new_packages:
        click.secho('{} : seems to be new'.format(pkg.full_name), bold=True)
        tree.show(pkg.path)
    for pkg, old_version in new_versions:
        click.secho('{} : new version ({} -> {})'.format(pkg.name,
                                                         old_version,
                                                         pkg.version),
                    bold=True)
        tree.show(pkg.path)
    for pkg in changed_expressions:
        click.secho('{} : new expression'.format(pkg.full_name), bold=True)
        tree.show(pkg.path)

    forgotten = set(p.path for p in rest) - tree.seen
    if forgotten:
        print('Some packages where forgotten : {}'.format(forgotten))

# TODO : option -> display only thing to install, deps tree without
# repetition, deps tree with omission of repeated paths, or full tree
