"""Tests for detect.py, against a fake GitHub: no network and no `gh`.

Run from the repository's root:
  python3 -m unittest discover -s plugins/repo-setup/tests
"""

import contextlib
import io
import sys
import unittest
from unittest import mock

from fake_github import (
    ADMINS_PULL_REQUEST,
    FORCE_PUSH_AND_DELETION,
    RELEASE_APP,
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
        # More than a page of 100: GitHub's default page of 30 wouldn't reach it either.
        for number in range(105):
            self.github.add_ruleset(f"other {number}", applies=False)
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        out = self.detect_json()
        self.assertEqual(out["rulesets"]["ours"], ours)
        self.assertEqual(len(out["rulesets"]["existing"]), 106)
        self.assertTrue(self.options(out)["block_force_push_and_deletion"]["current"])

    def test_finds_its_ruleset_whatever_the_case_of_the_name_given(self):
        ours = self.github.add_ruleset(RULESET_NAME, rules=FORCE_PUSH_AND_DELETION)
        out = self.detect_json("Octo/Widgets")
        self.assertEqual(out["repo"], "octo/widgets")
        self.assertEqual(out["rulesets"]["ours"], ours)

    def test_stops_when_its_ruleset_cannot_be_read(self):
        ours = self.github.add_ruleset(
            RULESET_NAME, rules=[pull_request_rule(approvals=2)], bypass_actors=ADMINS_PULL_REQUEST
        )
        self.github.failing.add(("GET", f"repos/octo/widgets/rulesets/{ours}"))
        printed = io.StringIO()
        with mock.patch.object(sys, "argv", ["detect.py", "octo/widgets"]), contextlib.redirect_stdout(printed):
            with self.assertRaises(SystemExit) as stop:
                self.detect.main()
        self.assertIn("Server Error", str(stop.exception.code))
        self.assertEqual(printed.getvalue(), "")  # no report with its rules as not set

    def test_lists_a_ruleset_it_does_not_read_in_full(self):
        other = self.github.add_ruleset("other", rules=FORCE_PUSH_AND_DELETION)
        self.github.failing.add(("GET", f"repos/octo/widgets/rulesets/{other}"))
        out = self.detect_json()
        self.assertEqual(
            out["rulesets"]["existing"],
            [
                {
                    "id": other,
                    "name": "other",
                    "enforcement": "active",
                    "source": "octo/widgets",
                    "targets_default_branch": True,
                }
            ],
        )


class DefaultBranchTest(DetectTest):
    def test_reports_the_rulesets_github_applies_to_the_default_branch(self):
        explicit = self.github.add_ruleset(
            "explicit ref",
            conditions={"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            rules=FORCE_PUSH_AND_DELETION,
            applies=True,
        )
        excluded = self.github.add_ruleset(
            "all but main",
            conditions={"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/main"]}},
            rules=FORCE_PUSH_AND_DELETION,
            applies=False,
        )
        out = self.detect_json()
        targets = {entry["id"]: entry["targets_default_branch"] for entry in out["rulesets"]["existing"]}
        self.assertEqual(targets, {explicit: True, excluded: False})

    def test_a_disabled_ruleset_counts_as_not_set(self):
        self.github.add_ruleset(
            RULESET_NAME,
            enforcement="disabled",
            rules=[pull_request_rule(approvals=1)] + FORCE_PUSH_AND_DELETION,
            bypass_actors=ADMINS_PULL_REQUEST,
        )
        options = self.options(self.detect_json())
        self.assertFalse(options["require_pull_request"]["current"])
        self.assertFalse(options["resolve_threads"]["current"])
        self.assertFalse(options["block_force_push_and_deletion"]["current"])
        self.assertIsNone(options["approvals"]["current"])
        self.assertIsNone(options["bypass"]["current"])

    def test_an_active_ruleset_counts_as_set(self):
        self.github.add_ruleset(
            RULESET_NAME,
            rules=[pull_request_rule(approvals=1)] + FORCE_PUSH_AND_DELETION,
            bypass_actors=ADMINS_PULL_REQUEST,
        )
        options = self.options(self.detect_json())
        self.assertTrue(options["require_pull_request"]["current"])
        self.assertTrue(options["resolve_threads"]["current"])
        self.assertTrue(options["block_force_push_and_deletion"]["current"])
        self.assertEqual(options["approvals"]["current"], 1)
        self.assertEqual(options["bypass"]["current"], "admins_pull_request")

    def test_a_bypass_list_with_anyone_besides_admins_is_no_choice(self):
        self.github.add_ruleset(
            RULESET_NAME, rules=FORCE_PUSH_AND_DELETION, bypass_actors=ADMINS_PULL_REQUEST + [RELEASE_APP]
        )
        out = self.detect_json()
        self.assertEqual(self.options(out)["bypass"]["current"], "other")
        self.assertEqual(out["rulesets"]["other_bypass"], [RELEASE_APP])


class CheckDiscoveryTest(DetectTest):
    def test_offers_the_checks_of_the_pull_request_merged_last(self):
        # #5 merged first, but a later comment makes it the most recently updated.
        self.github.add_pull(5, merged_at="2026-01-01T00:00:00Z", updated_at="2026-03-01T00:00:00Z", checks=["retired"])
        self.github.add_pull(7, merged_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", checks=["test"])
        out = self.detect_json()
        self.assertEqual(out["checks"], ["test"])
        self.assertIn("#7", out["checks_source"])

    def test_finds_a_merged_pull_request_behind_many_closed_ones(self):
        for number in range(100, 220):
            self.github.add_pull(number, updated_at=f"2026-05-01T00:{number % 60:02d}:00Z")
        self.github.add_pull(3, merged_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z", checks=["test"])
        out = self.detect_json()
        self.assertEqual(out["checks"], ["test"])
        self.assertIn("#3", out["checks_source"])

    def test_offers_the_checks_beyond_the_first_page(self):
        runs = [f"run {number}" for number in range(105)]
        statuses = [f"status {number}" for number in range(35)]
        self.github.add_pull(
            7, merged_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", checks=runs, statuses=statuses
        )
        out = self.detect_json()
        self.assertEqual(out["checks"], sorted(runs + statuses))

    def test_falls_back_to_the_default_branch_without_a_merged_pull_request(self):
        self.github.add_pull(4, updated_at="2026-01-01T00:00:00Z")
        self.github.checks["main"] = ["build"]
        out = self.detect_json()
        self.assertEqual(out["checks"], ["build"])
        self.assertEqual(out["checks_source"], "main's latest commit")

    def test_offers_no_checks_when_the_pull_requests_cannot_be_listed(self):
        self.github.add_pull(7, merged_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", checks=["test"])
        self.github.checks["main"] = ["scheduled-maintenance"]
        self.github.failing.add(("GET", "repos/octo/widgets/pulls"))
        out = self.detect_json()
        self.assertEqual(out["checks"], [])
        required = self.options(out)["required_checks"]
        self.assertFalse(required["available"])
        self.assertIn("Server Error", required["reason"])
        self.assertIn("pull requests", required["reason"])

    def test_offers_no_checks_when_they_cannot_be_read(self):
        self.github.add_pull(7, merged_at="2026-02-01T00:00:00Z", updated_at="2026-02-01T00:00:00Z", checks=["test"])
        self.github.failing.add(("GET", "repos/octo/widgets/commits/sha7/status"))
        out = self.detect_json()
        self.assertEqual(out["checks"], [])
        required = self.options(out)["required_checks"]
        self.assertFalse(required["available"])
        self.assertIn("Server Error", required["reason"])
        self.assertIn("#7", required["reason"])


if __name__ == "__main__":
    unittest.main()
