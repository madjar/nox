Nox
===

Nox is a small tool that makes the use of the Nix package manager
easier.

Nox is written in python 3 and requires nix 1.8 and git.

Usage
-----

Just run ``nox QUERY`` to search for a nix package. The underlying
``nix-env`` invocation is cached to make the search faster than your
usual ``nix-env -qa | grep QUERY``.

.. image:: screen.png

Once you have the results, type the numbers of the packages to install.

Bonus: if you enter the letter 's' at the beginning of the package
numbers list, a nix-shell will be started with those packages instead.

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
