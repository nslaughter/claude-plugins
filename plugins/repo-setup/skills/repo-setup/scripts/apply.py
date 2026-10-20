#!/usr/bin/env python3
"""Apply the settings chosen in repo-setup to a repository, then read them back.

Usage:
  apply.py --plan plan.json [--dry-run]

The plan names only what was chosen; nothing else is changed:

  {
    "repo": "owner/name",
    "merge": ["squash_only", "squash_message", "delete_branch", "auto_merge_off"],
    "ruleset": {
      "require_pull_request": true,
      "approvals": 0,
      "resolve_threads": true,
      "checks": ["test"],
      "block_force_push_and_deletion": true,
      "bypass": "none" | "admins_pull_request" | "admins_always"
    }
  }

"ruleset" is null when no ruleset rule was chosen.

The ruleset is named "repo-setup: default branch" and targets the default
branch; a later run updates it in place. An update keeps every rule and
parameter the plan doesn't choose, so a rule left unticked stays as it is:
the plan adds rules and sets the parameters it names, and never removes a
rule or turns off thread resolution. "checks" replaces the list of required
checks. A ruleset that isn't active enforces nothing, so its rules aren't
kept, and the update makes it active with only the rules chosen.

Other rulesets and classic branch protection are never touched. With
--dry-run it prints the calls it would make and changes nothing. Otherwise
it prints a report: each setting before and after, and whether the
read-back matches what was asked.

Needs only Python 3 and an authenticated `gh` with admin access to the repository.
"""

import argparse
import copy
import json
import subprocess
import sys

RULESET_NAME = "repo-setup: default branch"
RULE_CHOICES = ("require_pull_request", "checks", "block_force_push_and_deletion")
ADMIN_ROLE = 5  # The built-in repository admin role, as rulesets name it.
PER_PAGE = 100

MERGE_SETTINGS = {
    "squash_only": {"allow_squash_merge": True, "allow_merge_commit": False, "allow_rebase_merge": False},
    "squash_message": {"squash_merge_commit_title": "PR_TITLE", "squash_merge_commit_message": "PR_BODY"},
    "delete_branch": {"delete_branch_on_merge": True},
    "auto_merge_off": {"allow_auto_merge": False},
}

BYPASS = {
    "none": [],
    "admins_pull_request": [{"actor_id": ADMIN_ROLE, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
    "admins_always": [{"actor_id": ADMIN_ROLE, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
}


def first_line(text):
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def gh_api(method, path, body=None, fields=()):
    args = ["gh", "api", "-X", method, path, *fields]
    if body is not None:
        args += ["--input", "-"]
    run = subprocess.run(
        args,
        input=None if body is None else json.dumps(body),
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        try:
            message = json.loads(run.stdout).get("message")
            errors = json.loads(run.stdout).get("errors")
        except (ValueError, AttributeError):
            message, errors = None, None
        detail = f" ({'; '.join(map(str, errors))})" if errors else ""
        raise RuntimeError(f"{method} {path}: {message or first_line(run.stderr) or 'failed'}{detail}")
    return json.loads(run.stdout) if run.stdout.strip() else None


def gh_pages(path):
    """Every item of a list the API pages."""
    items, page = [], 1
    while True:
        data = gh_api("GET", f"{path}?per_page={PER_PAGE}&page={page}") or []
        items += data
        if len(data) < PER_PAGE:
            return items
        page += 1


def find_ruleset(repo):
    """The ruleset this skill made, as GitHub returns it, or None.

    GitHub matches owner and repository names in any case, so the plan's
    spelling of the name may differ from the `source` GitHub reports.
    """
    for summary in gh_pages(f"repos/{repo}/rulesets"):
        if summary.get("name") == RULESET_NAME and (summary.get("source") or "").lower() == repo.lower():
            return gh_api("GET", f"repos/{repo}/rulesets/{summary['id']}")
    return None


def ruleset_body(plan, existing=None):
    """The ruleset to save: the plan's choices on top of the rules `existing` enforces.

    `existing` is this skill's ruleset from an earlier run, or None. When it
    is active, its rules and parameters the plan doesn't choose are kept, so
    a later run never drops a protection the user left unticked.
    """
    kept = (existing or {}).get("rules") if (existing or {}).get("enforcement") == "active" else None
    rules = [
        {key: copy.deepcopy(value) for key, value in old.items() if key in ("type", "parameters")}
        for old in kept or []
    ]

    def rule(kind, parameters=None):
        found = next((r for r in rules if r.get("type") == kind), None)
        if found is None:
            found = {"type": kind}
            if parameters is not None:
                found["parameters"] = parameters
            rules.append(found)
        return found

    if plan.get("require_pull_request"):
        parameters = rule(
            "pull_request",
            {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": False,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": False,
            },
        ).setdefault("parameters", {})
        parameters["required_approving_review_count"] = int(plan.get("approvals") or 0)
        if plan.get("resolve_threads"):
            parameters["required_review_thread_resolution"] = True
    if plan.get("checks"):
        parameters = rule(
            "required_status_checks",
            {"strict_required_status_checks_policy": False, "required_status_checks": []},
        ).setdefault("parameters", {})
        # A check already required keeps its other fields, such as the app it must come from.
        old = {c.get("context"): c for c in parameters.get("required_status_checks") or []}
        parameters["required_status_checks"] = [old.get(name, {"context": name}) for name in plan["checks"]]
    if plan.get("block_force_push_and_deletion"):
        rule("non_fast_forward")
        rule("deletion")
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": BYPASS[plan.get("bypass") or "none"],
        "rules": rules,
    }


def check_plan(plan):
    problems = []
    if not plan.get("repo"):
        problems.append('the plan names no "repo"')
    for name in plan.get("merge") or []:
        if name not in MERGE_SETTINGS:
            problems.append(f'unknown merge setting "{name}"')
    ruleset = plan.get("ruleset")
    if ruleset:
        if ruleset.get("resolve_threads") and not ruleset.get("require_pull_request"):
            problems.append("resolving threads is part of the pull request rule, which the plan leaves out")
        if (ruleset.get("approvals") or 0) and not ruleset.get("require_pull_request"):
            problems.append("required approvals are part of the pull request rule, which the plan leaves out")
        if (ruleset.get("bypass") or "none") not in BYPASS:
            problems.append(f'unknown bypass "{ruleset.get("bypass")}"')
        if int(ruleset.get("approvals") or 0) not in (0, 1, 2):
            problems.append("approvals must be 0, 1 or 2")
    return problems


def bypass_roles(node_id):
    """The role names GitHub reports for the ruleset's bypass list, so the role ID is confirmed.

    The ruleset is looked up by its node ID, so it's found however many
    rulesets the repository has.
    """
    query = """query($id: ID!) {
      node(id: $id) { ... on RepositoryRuleset { bypassActors(first: 100) {
        nodes { bypassMode repositoryRoleName } } } }
    }"""
    data = gh_api("POST", "graphql", fields=["-f", f"query={query}", "-f", f"id={node_id}"])
    node = ((data or {}).get("data") or {}).get("node") or {}
    return [
        {"role": actor.get("repositoryRoleName"), "mode": actor.get("bypassMode")}
        for actor in (node.get("bypassActors") or {}).get("nodes", [])
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--plan", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(args.plan, encoding="utf-8") as file:
        plan = json.load(file)
    problems = check_plan(plan)
    if problems:
        sys.exit("apply.py: " + "; ".join(problems))
    repo = plan["repo"]

    patch = {}
    for name in plan.get("merge") or []:
        patch.update(MERGE_SETTINGS[name])
    chosen = plan.get("ruleset") or {}
    body, existing = None, None
    if any(chosen.get(key) for key in RULE_CHOICES):  # With no rule chosen, no ruleset is made or changed.
        existing = find_ruleset(repo)
        body = ruleset_body(chosen, existing)

    if args.dry_run:
        calls = []
        if patch:
            calls.append({"method": "PATCH", "path": f"repos/{repo}", "body": patch})
        if body is not None:
            calls.append(
                {
                    "method": "PUT" if existing else "POST",
                    "path": f"repos/{repo}/rulesets/{existing['id']}" if existing else f"repos/{repo}/rulesets",
                    "body": body,
                }
            )
        json.dump({"repo": repo, "dry_run": True, "calls": calls}, sys.stdout, indent=2)
        print()
        return

    report = {"repo": repo, "settings": [], "ruleset": None, "errors": []}

    if patch:
        before = gh_api("GET", f"repos/{repo}")
        try:
            gh_api("PATCH", f"repos/{repo}", body=patch)
        except RuntimeError as error:
            report["errors"].append(str(error))
        after = gh_api("GET", f"repos/{repo}")
        for key, wanted in patch.items():
            report["settings"].append(
                {"setting": key, "before": before.get(key), "after": after.get(key), "ok": after.get(key) == wanted}
            )

    if body is not None:
        try:
            if existing:
                saved = gh_api("PUT", f"repos/{repo}/rulesets/{existing['id']}", body=body)
                action = "updated"
            else:
                saved = gh_api("POST", f"repos/{repo}/rulesets", body=body)
                action = "created"
            back = gh_api("GET", f"repos/{repo}/rulesets/{saved['id']}")
            got = sorted(r["type"] for r in back.get("rules", []))
            wanted = sorted(r["type"] for r in body["rules"])
            roles = bypass_roles(back.get("node_id"))
            report["ruleset"] = {
                "id": saved["id"],
                "url": f"https://github.com/{repo}/rules/{saved['id']}",
                "action": action,
                "rules": got,
                "bypass": roles,
                "ok": got == wanted
                and back.get("enforcement") == "active"
                and len(roles) == len(body["bypass_actors"])
                and all((r["role"] or "").lower() == "admin" for r in roles),
            }
        except RuntimeError as error:
            report["errors"].append(str(error))

    json.dump(report, sys.stdout, indent=2)
    print()
    if report["errors"] or not all(s["ok"] for s in report["settings"]) or (
        report["ruleset"] is not None and not report["ruleset"]["ok"]
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
