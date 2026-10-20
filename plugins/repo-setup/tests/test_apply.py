"""Tests for apply.py, against a fake GitHub: no network and no `gh`.

Run from the repository's root:
  python3 -m unittest discover -s plugins/repo-setup/tests
"""

import json
import os
import tempfile
import unittest

from fake_github import (
    ADMINS_PULL_REQUEST,
    FORCE_PUSH_AND_DELETION,
    FakeGitHub,
    checks_rule,
    load,
    pull_request_rule,
    run,
)

RULESET_NAME = "repo-setup: default branch"

FULL_RULESET = {
    "require_pull_request": True,
    "approvals": 0,
    "resolve_threads": True,
    "checks": ["test"],
    "block_force_push_and_deletion": True,
    "bypass": "admins_pull_request",
}


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.apply = load("apply")
        self.github = FakeGitHub()
        self.apply.gh_api = self.github.gh_api
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def apply_plan(self, ruleset, *, repo="octo/widgets", merge=(), dry_run=False):
        path = os.path.join(self.dir.name, "plan.json")
        with open(path, "w", encoding="utf-8") as file:
            json.dump({"repo": repo, "merge": list(merge), "ruleset": ruleset}, file)
        return run(self.apply.main, ["apply.py", "--plan", path] + (["--dry-run"] if dry_run else []))

    def planned_ruleset_call(self, ruleset, **kwargs):
        code, out = self.apply_plan(ruleset, dry_run=True, **kwargs)
        self.assertEqual(code, 0, out)
        calls = [call for call in out["calls"] if "rulesets" in call["path"]]
        self.assertEqual(len(calls), 1, out)
        return calls[0]


class LookupTest(ApplyTest):
    def test_finds_its_ruleset_beyond_the_first_page(self):
        for number in range(35):
            self.github.add_ruleset(f"other {number}")
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        call = self.planned_ruleset_call(FULL_RULESET)
        self.assertEqual(call["method"], "PUT")
        self.assertTrue(call["path"].endswith(f"/rulesets/{ours}"))

    def test_finds_its_ruleset_whatever_the_case_of_the_name_in_the_plan(self):
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        call = self.planned_ruleset_call(FULL_RULESET, repo="Octo/Widgets")
        self.assertEqual(call["method"], "PUT")
        self.assertTrue(call["path"].endswith(f"/rulesets/{ours}"))

    def test_confirms_the_bypass_of_a_ruleset_beyond_the_first_fifty(self):
        for number in range(55):
            self.github.add_ruleset(f"other {number}")
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        code, out = self.apply_plan(FULL_RULESET)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["ruleset"]["id"], ours)
        self.assertEqual(out["ruleset"]["action"], "updated")
        self.assertEqual(out["ruleset"]["bypass"], [{"role": "admin", "mode": "PULL_REQUEST"}])


if __name__ == "__main__":
    unittest.main()
