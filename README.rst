Nox
===

Nox is a small tool that makes the use of the Nix package manager
easier.

Nox is written in python 3 and requires nix 1.8 and git. It is
released under MIT license.

Try it
------

You can install it from nixpkgs by running ``nix-env -iA nox``.

To try the last version, just clone the repository, run ``nix-build``,
and run the resulting binaries in ``result/bin``. To install it, run
``nix-env -if .``.

Search
------

Just run ``nox QUERY`` to search for a nix package. The underlying
``nix-env`` invocation is cached to make the search faster than your
usual ``nix-env -qa | grep QUERY``.

.. image:: screen.png

Once you have the results, type the numbers of the packages to install.

Bonus: if you enter the letter 's' at the beginning of the package
numbers list, a nix-shell will be started with those packages instead.

Review
------

The ``nox-review`` command helps you find what has changed nixpkgs, and
build change packages, so you're sure they are not broken. There is 3 modes:

- ``nox-review revs CURRENT_REV REFERENCE_REV`` find the differences
  between two nixpks revisions, and build those packages as they are
  in ``CURRENT_REV``
- ``nox-review wip`` compares the nixpkgs in the current working dir
  against a commit, so you can check that your changes break
  nothing. Defaults to comparing to ``HEAD`` (the last commit), but you
  can change: ``nox-review wip --against master^'``.
- ``now-review pr PR`` finds the packages touched by the given PR and build them.

Experimental
------------

I'm working on a new commands, ``nox-update``, that will display
information about what is about to be update, especially giving info
not given by nixos-rebuild:

- Why is everything being installed?
- Which are package upgrades?
- Which are expression change?
- Which are only rebuild trigerred by dependency changes?
- Especially, what package triggered the rebuild?

A picture is better than a thousand words, so here is what it looks like for now

.. image:: http://i.imgur.com/jdOGN94.png
