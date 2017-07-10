import unittest

from .. import review

class TestReview(unittest.TestCase):

    def test_differences(self):
        # Tuples of <old set>, <new set>, <expected difference>
        TESTS = [
            (set(["same"]), set(["same", "diff"]), set(["diff"])),
            (set(["same"]), set(["same"]), set()),
            (set(), set(["diff"]), set(["diff"]))
        ]
        for old, new, result in TESTS:
            self.assertEqual(result, review.differences(old, new))
