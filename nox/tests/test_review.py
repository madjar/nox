import unittest

from .. import review


class TestReview(unittest.TestCase):
    def test_get_build_command(self):
        result = review.get_build_command([], ["nox"], ".")
        self.assertEqual(["nix-build", "-A", "nox", "."], result)

    def test_build_in_path(self):
        # Just do a dry run to make sure there aren't any exceptions
        self.assertIs(None, review.build_in_path([], ["nox"], ".", dry_run=True))

    def test_differences(self):
        # Tuples of <old set>, <new set>, <expected difference>
        TESTS = [
            (set(["same"]), set(["same", "diff"]), set(["diff"])),
            (set(["same"]), set(["same"]), set()),
            (set(), set(["diff"]), set(["diff"]))
        ]
        for old, new, result in TESTS:
            self.assertEqual(result, review.differences(old, new))
