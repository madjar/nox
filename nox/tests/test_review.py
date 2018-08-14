import unittest

from .. import review, nixpkgs_repo


class TestReview(unittest.TestCase):
    def test_get_build_command(self):
        nox = nixpkgs_repo.Buildable("nox", hash("nox"))
        result = review.get_build_commands([nox])
        self.assertEqual([["nix-build", "-A", "nox", "<nixpkgs>"]], result)

    def test_build_in_path(self):
        nox = nixpkgs_repo.Buildable("nox", hash("nox"))
        # Just do a dry run to make sure there aren't any exceptions
        self.assertIs(None, review.build_sha(None, [nox], extra_args=[], dry_run=True))
