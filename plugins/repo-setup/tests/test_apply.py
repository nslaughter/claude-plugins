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


class LaterRunTest(ApplyTest):
    def test_keeps_the_rules_left_unticked(self):
        ours = self.github.add_ruleset(
            RULESET_NAME,
            rules=[pull_request_rule(approvals=1), checks_rule("test")],
            bypass_actors=ADMINS_PULL_REQUEST,
        )
        call = self.planned_ruleset_call({"block_force_push_and_deletion": True, "bypass": "admins_pull_request"})
        self.assertEqual(call["method"], "PUT")
        self.assertTrue(call["path"].endswith(f"/rulesets/{ours}"))
        rules = {rule["type"]: rule for rule in call["body"]["rules"]}
        self.assertEqual(set(rules), {"pull_request", "required_status_checks", "non_fast_forward", "deletion"})
        self.assertEqual(rules["pull_request"]["parameters"]["required_approving_review_count"], 1)
        self.assertEqual(rules["required_status_checks"], checks_rule("test"))

    def test_keeps_thread_resolution_left_unticked(self):
        self.github.add_ruleset(RULESET_NAME, rules=[pull_request_rule(resolve_threads=True)])
        call = self.planned_ruleset_call({"require_pull_request": True, "approvals": 1, "bypass": "none"})
        (pull,) = [rule for rule in call["body"]["rules"] if rule["type"] == "pull_request"]
        self.assertTrue(pull["parameters"]["required_review_thread_resolution"])
        self.assertEqual(pull["parameters"]["required_approving_review_count"], 1)

    def test_does_not_carry_over_the_rules_of_a_disabled_ruleset(self):
        self.github.add_ruleset(RULESET_NAME, enforcement="disabled", rules=[pull_request_rule(), checks_rule("test")])
        call = self.planned_ruleset_call({"block_force_push_and_deletion": True, "bypass": "none"})
        self.assertEqual(call["method"], "PUT")
        self.assertEqual(call["body"]["rules"], FORCE_PUSH_AND_DELETION)
        self.assertEqual(call["body"]["enforcement"], "active")


class ReadBackTest(ApplyTest):
    def test_a_ruleset_that_reads_back_as_asked_is_ok(self):
        code, out = self.apply_plan(FULL_RULESET)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["ruleset"]["action"], "created")
        self.assertTrue(out["ruleset"]["ok"])
        self.assertEqual(out["ruleset"]["mismatches"], [])

    def assert_reads_back_differently(self, change):
        self.github.after_save = change
        code, out = self.apply_plan(FULL_RULESET)
        self.assertEqual(code, 1, out)
        self.assertFalse(out["ruleset"]["ok"])
        self.assertTrue(out["ruleset"]["mismatches"])
        return out["ruleset"]["mismatches"]

    def test_a_bypass_mode_that_reads_back_differently_fails(self):
        def always(ruleset):
            ruleset["bypass_actors"][0]["bypass_mode"] = "always"

        mismatches = self.assert_reads_back_differently(always)
        self.assertTrue(any("bypass" in mismatch for mismatch in mismatches), mismatches)

    def test_approvals_that_read_back_differently_fail(self):
        def two(ruleset):
            ruleset["rules"][0]["parameters"]["required_approving_review_count"] = 2

        self.assert_reads_back_differently(two)

    def test_thread_resolution_that_reads_back_differently_fails(self):
        def unresolved(ruleset):
            ruleset["rules"][0]["parameters"]["required_review_thread_resolution"] = False

        self.assert_reads_back_differently(unresolved)

    def test_checks_that_read_back_differently_fail(self):
        def other(ruleset):
            ruleset["rules"][1]["parameters"]["required_status_checks"] = [{"context": "lint"}]

        self.assert_reads_back_differently(other)

    def test_a_branch_condition_that_reads_back_differently_fails(self):
        def every_branch(ruleset):
            ruleset["conditions"]["ref_name"]["include"] = ["~ALL"]

        self.assert_reads_back_differently(every_branch)

    def test_names_the_saved_ruleset_when_reading_it_back_fails(self):
        self.github.failing.add(("GET", f"repos/octo/widgets/rulesets/{self.github.next_id}"))
        code, out = self.apply_plan(FULL_RULESET)
        self.assertEqual(code, 1, out)
        self.assertTrue(out["errors"], out)
        self.assertIsNotNone(out["ruleset"], out)
        self.assertEqual(out["ruleset"]["id"], self.github.next_id - 1)
        self.assertEqual(out["ruleset"]["action"], "created")
        self.assertFalse(out["ruleset"]["ok"])


class MergeSettingsTest(ApplyTest):
    def test_reports_saved_settings_when_reading_them_back_fails(self):
        self.github.after_patch = lambda: self.github.failing.add(("GET", "repos/octo/widgets"))
        code, out = self.apply_plan(FULL_RULESET, merge=["delete_branch"])
        self.assertEqual(code, 1, out)
        self.assertIsInstance(out, dict, out)
        self.assertTrue(any(error.startswith("GET repos/octo/widgets:") for error in out["errors"]), out)
        self.assertEqual(
            out["settings"],
            [{"setting": "delete_branch_on_merge", "before": False, "after": None, "saved": True, "ok": False}],
        )
        # The ruleset is still applied.
        self.assertEqual(out["ruleset"]["action"], "created")
        self.assertTrue(out["ruleset"]["ok"], out)

    def test_reports_settings_that_were_not_saved(self):
        self.github.failing.add(("PATCH", "repos/octo/widgets"))
        code, out = self.apply_plan(None, merge=["delete_branch", "auto_merge_off"])
        self.assertEqual(code, 1, out)
        settings = {entry["setting"]: entry for entry in out["settings"]}
        self.assertFalse(settings["delete_branch_on_merge"]["saved"])
        self.assertFalse(settings["delete_branch_on_merge"]["ok"])
        # Already off: it reads back as asked, though the change wasn't saved.
        self.assertFalse(settings["allow_auto_merge"]["saved"])
        self.assertTrue(settings["allow_auto_merge"]["ok"])


if __name__ == "__main__":
    unittest.main()
