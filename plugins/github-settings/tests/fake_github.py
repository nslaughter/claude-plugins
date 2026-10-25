"""A stand-in for the parts of GitHub's API that detect.py and apply.py call.

The tests replace each script's `gh` helper with this fake, so they need no
network and no `gh`. It keeps a repository, its rulesets and its closed pull
requests in memory, and pages lists the way GitHub does (30 a page unless
`per_page` says otherwise). It reads a path as gh sends it and GitHub reads
it: a `#` ends it, and each of its parts and query values is unescaped.
"""

import contextlib
import copy
import importlib.util
import io
import json
import os
import sys
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "github-settings", "scripts")
ADMIN_ROLE = 5


def load(name):
    """Import one of the skill's scripts as a module."""
    spec = importlib.util.spec_from_file_location(f"github_settings_{name}", os.path.join(SCRIPTS, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Refused(Exception):
    """GitHub answered with an error; the message is the API's."""


class FakeGitHub:
    def __init__(self, repo="octo/widgets"):
        self.repo = repo  # GitHub's own spelling of the name
        self.info = {
            "full_name": repo,
            "default_branch": "main",
            "visibility": "public",
            "permissions": {"admin": True},
            "owner": {"login": repo.split("/")[0], "type": "User"},
            "allow_squash_merge": True,
            "allow_merge_commit": True,
            "allow_rebase_merge": True,
            "squash_merge_commit_title": "COMMIT_OR_PR_TITLE",
            "squash_merge_commit_message": "COMMIT_MESSAGES",
            "delete_branch_on_merge": False,
            "allow_auto_merge": False,
        }
        self.rulesets = {}  # id -> the ruleset as GitHub returns it
        self.applies = {}  # id -> whether its conditions match the default branch; none match another
        self.pulls = []  # closed pull requests into the default branch
        self.checks = {}  # commit SHA -> names of the check runs on it
        self.statuses = {}  # commit SHA -> contexts of the commit statuses on it
        self.failing = set()  # (method, path) pairs that GitHub refuses
        self.after_save = None  # changes a saved ruleset before it's read back
        self.after_patch = None  # runs once the repository's settings are saved
        self.calls = []
        self.next_id = 1000

    # Setting up

    def add_ruleset(self, name, *, source=None, enforcement="active", applies=True, rules=(), bypass_actors=(), conditions=None):
        ruleset_id = self.next_id
        self.next_id += 1
        self.rulesets[ruleset_id] = {
            "id": ruleset_id,
            "name": name,
            "target": "branch",
            "source_type": "Repository",
            "source": source or self.repo,
            "enforcement": enforcement,
            "conditions": conditions or {"ref_name": {"exclude": [], "include": ["~DEFAULT_BRANCH"]}},
            "rules": copy.deepcopy(list(rules)),
            "node_id": f"RRS_{ruleset_id}",
            "bypass_actors": copy.deepcopy(list(bypass_actors)),
        }
        self.applies[ruleset_id] = applies
        return ruleset_id

    def add_pull(self, number, *, updated_at, merged_at=None, checks=(), statuses=()):
        sha = f"sha{number}"
        self.pulls.append(
            {"number": number, "updated_at": updated_at, "merged_at": merged_at, "head": {"sha": sha}}
        )
        self.checks[sha] = list(checks)
        self.statuses[sha] = list(statuses)

    # The scripts' helpers, replaced

    def detect_api(self, path):
        """detect.py's `api`: (True, data), or (False, the API's message)."""
        try:
            return True, self.answer("GET", path)
        except Refused as error:
            return False, str(error)

    def gh_api(self, method, path, body=None, fields=()):
        """apply.py's `gh_api`: the data, or a RuntimeError with the API's message."""
        try:
            return self.answer(method, path, body, fields)
        except Refused as error:
            raise RuntimeError(f"{method} {path}: {error}") from None

    # Answering

    def answer(self, method, path, body=None, fields=()):
        url = urlsplit(path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        parts = [unquote(part) for part in url.path.strip("/").split("/")]
        self.calls.append((method, path, copy.deepcopy(body)))
        if (method, url.path) in self.failing:
            raise Refused("Server Error")
        if parts == ["user"]:
            return {"login": self.info["owner"]["login"]}
        if parts == ["graphql"]:
            return self.graphql(dict(field.split("=", 1) for field in fields if "=" in field))
        if parts[0] != "repos" or "/".join(parts[1:3]).lower() != self.repo.lower():
            raise Refused("Not Found")
        rest = parts[3:]
        if not rest:
            if method == "PATCH":
                self.info.update(body)
                if self.after_patch is not None:
                    self.after_patch()
            return copy.deepcopy(self.info)
        if rest == ["rulesets"] and method == "GET":
            summaries = [
                {key: ruleset[key] for key in ("id", "name", "target", "source_type", "source", "enforcement", "node_id")}
                for _, ruleset in sorted(self.rulesets.items())
            ]
            return self.page(summaries, query)
        if rest == ["rulesets"] and method == "POST":
            ruleset_id = self.add_ruleset(body["name"], enforcement=body["enforcement"], conditions=body["conditions"])
            return self.save(ruleset_id, body)
        if rest[0] == "rulesets" and len(rest) == 2:
            ruleset_id = int(rest[1])
            if ruleset_id not in self.rulesets:
                raise Refused("Not Found")
            if method == "PUT":
                return self.save(ruleset_id, body)
            return copy.deepcopy(self.rulesets[ruleset_id])
        if rest[:2] == ["rules", "branches"]:
            # GitHub answers for any name, a branch's or not, and no ruleset here matches another.
            on_default_branch = "/".join(rest[2:]) == self.info["default_branch"]
            applied = []
            for ruleset_id, ruleset in sorted(self.rulesets.items()):
                if ruleset["enforcement"] == "active" and self.applies[ruleset_id] and on_default_branch:
                    for rule in ruleset["rules"]:
                        applied.append(dict(rule, ruleset_source_type="Repository", ruleset_source=self.repo, ruleset_id=ruleset_id))
            return self.page(applied, query)
        if rest[:1] == ["branches"] and rest[-1] == "protection":
            if "/".join(rest[1:-1]) != self.info["default_branch"]:
                raise Refused("Branch not found")
            raise Refused("Branch not protected")
        if rest == ["pulls"]:
            # Every pull request kept here is into the default branch.
            into = self.pulls if query.get("base", self.info["default_branch"]) == self.info["default_branch"] else []
            newest_first = sorted(into, key=lambda pull: pull["updated_at"], reverse=True)
            return self.page(newest_first, query)
        # Both are objects that hold one page of their list. The ref is a SHA or a branch's name.
        ref = "/".join(rest[1:-1])
        if rest[:1] == ["commits"] and rest[-1] == "check-runs":
            runs = [{"name": name} for name in self.checks.get(ref, [])]
            return {"total_count": len(runs), "check_runs": self.page(runs, query)}
        if rest[:1] == ["commits"] and rest[-1] == "status":
            statuses = [{"context": context, "state": "success"} for context in self.statuses.get(ref, [])]
            return {"state": "success", "total_count": len(statuses), "statuses": self.page(statuses, query)}
        raise Refused("Not Found")

    def save(self, ruleset_id, body):
        ruleset = self.rulesets[ruleset_id]
        for key in ("name", "enforcement", "conditions", "rules", "bypass_actors"):
            if key in body:
                ruleset[key] = copy.deepcopy(body[key])
        # GitHub fills in parameters of its own that weren't sent.
        for rule in ruleset["rules"]:
            if rule["type"] == "pull_request":
                rule["parameters"].setdefault("required_reviewers", [])
                rule["parameters"].setdefault("allowed_merge_methods", ["merge", "squash", "rebase"])
        if self.after_save is not None:
            self.after_save(ruleset)
        return copy.deepcopy(ruleset)

    def graphql(self, variables):
        def actors(ruleset):
            return {
                "nodes": [
                    {
                        "bypassMode": actor["bypass_mode"].upper(),
                        # Only a role has a role name; an app or a team has none.
                        "repositoryRoleName": None
                        if actor["actor_type"] != "RepositoryRole"
                        else "admin" if actor["actor_id"] == ADMIN_ROLE else "maintain",
                    }
                    for actor in ruleset["bypass_actors"]
                ]
            }

        query = variables["query"]
        if "node(" in query:
            found = next((r for r in self.rulesets.values() if r["node_id"] == variables["id"]), None)
            return {"data": {"node": None if found is None else {"bypassActors": actors(found)}}}
        # repository { rulesets(first: 50) }: only the first 50 come back.
        nodes = [
            {"databaseId": ruleset_id, "bypassActors": actors(ruleset)}
            for ruleset_id, ruleset in sorted(self.rulesets.items())
        ][:50]
        return {"data": {"repository": {"rulesets": {"nodes": nodes}}}}

    @staticmethod
    def page(items, query):
        per_page = int(query.get("per_page", 30))
        start = (int(query.get("page", 1)) - 1) * per_page
        return copy.deepcopy(items[start : start + per_page])


def run(main, argv):
    """Run a script's main(): (its exit code, what it printed, parsed as JSON when it is)."""
    out = io.StringIO()
    code = 0
    with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
        try:
            main()
        except SystemExit as stop:
            code = stop.code if isinstance(stop.code, int) else 1
    text = out.getvalue()
    try:
        return code, json.loads(text)
    except ValueError:
        return code, text


def pull_request_rule(approvals=0, resolve_threads=True):
    return {
        "type": "pull_request",
        "parameters": {
            "required_approving_review_count": approvals,
            "dismiss_stale_reviews_on_push": False,
            "require_code_owner_review": False,
            "require_last_push_approval": False,
            "required_review_thread_resolution": resolve_threads,
        },
    }


def checks_rule(*names):
    return {
        "type": "required_status_checks",
        "parameters": {
            "strict_required_status_checks_policy": False,
            "required_status_checks": [{"context": name} for name in names],
        },
    }


FORCE_PUSH_AND_DELETION = [{"type": "non_fast_forward"}, {"type": "deletion"}]
ADMINS_PULL_REQUEST = [{"actor_id": ADMIN_ROLE, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}]
RELEASE_APP = {"actor_id": 42, "actor_type": "Integration", "bypass_mode": "always"}  # a GitHub App
