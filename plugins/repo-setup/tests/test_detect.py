"""Tests for detect.py, against a fake GitHub: no network and no `gh`.

Run from the repository's root:
  python3 -m unittest discover -s plugins/repo-setup/tests
"""

import unittest

from fake_github import (
    ADMINS_PULL_REQUEST,
    FORCE_PUSH_AND_DELETION,
    FakeGitHub,
    load,
    pull_request_rule,
    run,
)

RULESET_NAME = "repo-setup: default branch"


class DetectTest(unittest.TestCase):
    def setUp(self):
        self.detect = load("detect")
        self.github = FakeGitHub()
        self.detect.api = self.github.detect_api

    def detect_json(self, repo="octo/widgets"):
        code, out = run(self.detect.main, ["detect.py", repo])
        self.assertEqual(code, 0, out)
        return out

    def options(self, out):
        return {option["id"]: option for option in out["options"]}


class RulesetLookupTest(DetectTest):
    def test_finds_its_ruleset_beyond_the_first_page(self):
        for number in range(35):
            self.github.add_ruleset(f"other {number}", applies=False)
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        out = self.detect_json()
        self.assertEqual(out["rulesets"]["ours"], ours)
        self.assertEqual(len(out["rulesets"]["existing"]), 36)
        self.assertTrue(self.options(out)["block_force_push_and_deletion"]["current"])

    def test_finds_its_ruleset_whatever_the_case_of_the_name_given(self):
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        out = self.detect_json("Octo/Widgets")
        self.assertEqual(out["repo"], "octo/widgets")
        self.assertEqual(out["rulesets"]["ours"], ours)


if __name__ == "__main__":
    unittest.main()
