#!/usr/bin/env python3
"""Report which settings repo-setup can apply to a repository, and how each stands now.

Usage:
  detect.py [owner/name]    (defaults to the current directory's repository)

Prints one JSON object: the repository, by the name GitHub gives it, who holds
its admin role, and `options`, one entry per setting with whether it is
available here (and the API's own reason when it isn't), its current state,
and its default. Availability is found by asking the API, not by reading the
plan name, so an organization's plan, a repository's visibility and the
caller's access all count.

Whether a ruleset applies to the default branch is GitHub's own answer, from
its branch-rules endpoint, so explicit refs, patterns, exclusions and the
ruleset's enforcement all count. A rule of the skill's own ruleset counts as
set only when GitHub enforces it there: a disabled ruleset sets nothing.

Needs only Python 3 and an authenticated `gh`. Reads only; changes nothing.
"""

import json
import subprocess
import sys

RULESET_NAME = "repo-setup: default branch"
PER_PAGE = 100
MERGE_KEYS = [
    "allow_squash_merge",
    "allow_merge_commit",
    "allow_rebase_merge",
    "squash_merge_commit_title",
    "squash_merge_commit_message",
    "delete_branch_on_merge",
    "allow_auto_merge",
]


def first_line(text):
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def api(path):
    """(True, data) on success, (False, the API's message) on any error."""
    run = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=False)
    if run.returncode == 0:
        return True, json.loads(run.stdout) if run.stdout.strip() else None
    try:
        message = json.loads(run.stdout).get("message")
    except (ValueError, AttributeError):
        message = None
    return False, message or first_line(run.stderr) or first_line(run.stdout) or "the request failed"


def api_pages(path):
    """Every item of a list the API pages: (True, items), or (False, the API's message)."""
    items, page = [], 1
    while True:
        ok, data = api(f"{path}{'&' if '?' in path else '?'}per_page={PER_PAGE}&page={page}")
        if not ok:
            return False, data
        items += data or []
        if len(data or []) < PER_PAGE:
            return True, items
        page += 1


def need(path):
    ok, data = api(path)
    if not ok:
        sys.exit(f"detect.py: gh api {path}: {data}")
    return data


def current_repo():
    run = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        sys.exit(f"detect.py: no repository given, and none here: {first_line(run.stderr)}")
    return run.stdout.strip()


def rule(ruleset, kind):
    return next((r for r in (ruleset or {}).get("rules", []) if r.get("type") == kind), None)


def bypass_of(ruleset):
    if ruleset is None:
        return None
    actors = ruleset.get("bypass_actors") or []
    admin = next(
        (a for a in actors if a.get("actor_type") == "RepositoryRole" and a.get("actor_id") == 5),
        None,
    )
    if admin is None:
        return "none" if not actors else "other"
    return "admins_always" if admin.get("bypass_mode") == "always" else "admins_pull_request"


def check_names(repo, branch):
    """The checks that ran on the latest merged pull request, and where they came from.

    Only a check that runs on pull requests can be required: one that runs
    only on pushes or on a schedule would never report, and every merge would
    wait for it. Without a merged pull request, the default branch's latest
    commit stands in.
    """
    ref, source = branch, f"{branch}'s latest commit"
    ok, pulls = api(f"repos/{repo}/pulls?state=closed&base={branch}&sort=updated&direction=desc&per_page=20")
    merged = next((p for p in pulls or [] if p.get("merged_at")), None) if ok else None
    if merged is not None:
        ref, source = merged["head"]["sha"], f"pull request #{merged['number']}, the latest merged"
    names = set()
    ok, runs = api(f"repos/{repo}/commits/{ref}/check-runs?per_page=100")
    if ok:
        names.update(run["name"] for run in runs.get("check_runs", []))
    ok, status = api(f"repos/{repo}/commits/{ref}/status")
    if ok:
        names.update(s["context"] for s in status.get("statuses", []))
    return sorted(names), source


def option(id, group, label, *, available, reason, current, default, description=""):
    return {
        "id": id,
        "group": group,
        "label": label,
        "description": description,
        "available": available,
        "reason": None if available else reason,
        "current": current,
        "default": default,
    }


def main():
    info = need(f"repos/{sys.argv[1] if len(sys.argv) > 1 else current_repo()}")
    repo = info["full_name"]  # GitHub's spelling: it matches owner and name in any case.
    viewer = need("user")["login"]
    branch = info["default_branch"]
    is_admin = bool((info.get("permissions") or {}).get("admin"))
    merge = {key: info.get(key) for key in MERGE_KEYS}

    # Rulesets: whether this repository may have them is the API's answer.
    rulesets_ok, listed = api_pages(f"repos/{repo}/rulesets")
    existing, ours, applying = [], None, set()
    if rulesets_ok:
        # The rulesets GitHub enforces on the default branch, by its own reading of
        # their conditions and enforcement.
        ok, applied = api_pages(f"repos/{repo}/rules/branches/{branch}")
        if not ok:
            sys.exit(f"detect.py: gh api repos/{repo}/rules/branches/{branch}: {applied}")
        applying = {r.get("ruleset_id") for r in applied}
        for summary in listed or []:
            ok, ruleset = api(f"repos/{repo}/rulesets/{summary['id']}")
            if not ok:
                continue
            entry = {
                "id": ruleset["id"],
                "name": ruleset["name"],
                "enforcement": ruleset.get("enforcement"),
                "source": ruleset.get("source"),
                "targets_default_branch": ruleset["id"] in applying,
            }
            existing.append(entry)
            if ruleset["name"] == RULESET_NAME and (ruleset.get("source") or "").lower() == repo.lower():
                ours = ruleset

    ok, protection = api(f"repos/{repo}/branches/{branch}/protection")
    classic = True if ok else (False if "not protected" in str(protection).lower() else None)

    if info["owner"]["type"] == "User":
        admins = [info["owner"]["login"]]
        admin_holders = f"only {info['owner']['login']}, the repository's owner"
    else:
        ok, people = api(f"repos/{repo}/collaborators?permission=admin&per_page=100")
        admins = sorted(p["login"] for p in people) if ok else []
        admin_holders = (
            f"everyone with admin access to the repository: {', '.join(admins)}"
            if admins
            else "everyone with admin access to the repository"
        )

    checks, checks_source = check_names(repo, branch)
    # Only what GitHub enforces on the default branch is already set.
    enforced = ours if ours is not None and ours["id"] in applying else None
    pull = rule(enforced, "pull_request")
    status_rule = rule(enforced, "required_status_checks")

    not_admin = f"{viewer} doesn't have admin access to {repo}, which changing its settings needs."
    rules_reason = not_admin if not is_admin else (None if rulesets_ok else listed)
    can_rule = is_admin and rulesets_ok

    options = [
        option(
            "squash_only",
            "merge",
            "Squash merges only",
            description="Turns off merge commits and rebase merges.",
            available=is_admin,
            reason=not_admin,
            current=merge["allow_squash_merge"] is True
            and merge["allow_merge_commit"] is False
            and merge["allow_rebase_merge"] is False,
            default=True,
        ),
        option(
            "squash_message",
            "merge",
            "Squash commit from the PR's title and description",
            description="The description, with the decisions it records, becomes the commit's body.",
            available=is_admin,
            reason=not_admin,
            current=merge["squash_merge_commit_title"] == "PR_TITLE"
            and merge["squash_merge_commit_message"] == "PR_BODY",
            default=True,
        ),
        option(
            "delete_branch",
            "merge",
            "Delete branches after merging",
            available=is_admin,
            reason=not_admin,
            current=merge["delete_branch_on_merge"] is True,
            default=True,
        ),
        option(
            "auto_merge_off",
            "merge",
            "Auto-merge off",
            description="No pull request merges itself once its checks pass.",
            available=is_admin,
            reason=not_admin,
            current=merge["allow_auto_merge"] is False,
            default=True,
        ),
        option(
            "require_pull_request",
            "ruleset",
            f"Require a pull request to change {branch}",
            description="No direct pushes to the default branch.",
            available=can_rule,
            reason=rules_reason,
            current=pull is not None,
            default=True,
        ),
        option(
            "required_checks",
            "ruleset",
            f"Require checks to pass: {', '.join(checks)}" if checks else "Require checks to pass",
            description=f"The checks that ran on {checks_source}.",
            available=can_rule and bool(checks),
            reason=rules_reason if not can_rule else f"No checks ran on {checks_source}.",
            current=sorted(
                c["context"]
                for c in ((status_rule or {}).get("parameters") or {}).get("required_status_checks", [])
            ),
            default=True,
        ),
        option(
            "resolve_threads",
            "ruleset",
            "Require review threads to be resolved",
            description="Needs the pull request rule.",
            available=can_rule,
            reason=rules_reason,
            current=bool(((pull or {}).get("parameters") or {}).get("required_review_thread_resolution")),
            default=True,
        ),
        option(
            "block_force_push_and_deletion",
            "ruleset",
            f"Block force pushes to {branch} and deleting it",
            available=can_rule,
            reason=rules_reason,
            current=rule(enforced, "non_fast_forward") is not None and rule(enforced, "deletion") is not None,
            default=True,
        ),
        option(
            "approvals",
            "review",
            "Required approvals",
            description="0, 1 or 2. GitHub doesn't let anyone approve their own pull request.",
            available=can_rule,
            reason=rules_reason,
            current=((pull or {}).get("parameters") or {}).get("required_approving_review_count"),
            default=0,
        ),
        option(
            "bypass",
            "review",
            "Who may bypass the ruleset",
            description=f"Rulesets grant a bypass to a role, not to one person. Admin here is {admin_holders}.",
            available=can_rule,
            reason=rules_reason,
            current=bypass_of(enforced),
            default="admins_pull_request",
        ),
    ]

    json.dump(
        {
            "repo": repo,
            "viewer": viewer,
            "visibility": info.get("visibility"),
            "owner_type": info["owner"]["type"],
            "is_admin": is_admin,
            "default_branch": branch,
            "admin_holders": admin_holders,
            "admins": admins,
            "merge": merge,
            "rulesets": {
                "available": rulesets_ok,
                "reason": None if rulesets_ok else listed,
                "existing": existing,
                "ours": None if ours is None else ours["id"],
            },
            "classic_protection": classic,
            "checks": checks,
            "checks_source": checks_source,
            "options": options,
        },
        sys.stdout,
        indent=2,
    )
    print()


if __name__ == "__main__":
    main()
