---
name: repo-setup
description: Set up a GitHub repository's merge settings and default-branch protection. Squash merges only, with the pull request's title and description as the commit; branches deleted after merging; auto-merge off; and a ruleset on the default branch that requires pull requests, passing checks and resolved review threads, blocks force pushes and deletion, and sets required approvals with an optional bypass for the repository's admins. It checks which settings the repository's plan and the user's access allow, asks which to apply, applies them with gh, and reads them back. Use when the user asks to set up, configure, harden or protect a repository or its main branch, to set squash-merge or other merge settings, to add branch protection or a ruleset, or to require checks or approvals.
argument-hint: "[owner/repo]"
---

# Repo setup

Arguments: $ARGUMENTS

Two scripts do the work, so every API call is fixed code: `detect.py` reads what the repository
can have and has, and `apply.py` makes exactly the chosen changes and reads them back. You find
out, ask, apply, and report. Never change a setting the user didn't choose, and never delete or
edit a ruleset or branch protection this skill didn't make.

## 1. Find out what the repository can have

The repository is the one the arguments name (`owner/repo`, or its URL), else the current
directory's. Run:

```bash
python3 -I ${CLAUDE_SKILL_DIR}/scripts/detect.py <owner/repo>
```

It prints JSON. `options` lists every setting with `available`, the API's own `reason` when it
isn't, `current`, and `default`. Availability comes from asking the API, not from the plan's name:
on GitHub Free a private repository's rulesets call refuses, and the reason says so.

- If `is_admin` is false, stop: say that changing the settings needs admin access, and show the
  current settings from `merge`.
- If `rulesets.available` is false, only the merge settings can be applied. Say why, in the
  API's words, and that a public repository, or a paid plan, would allow the rest.
- `checks` are the checks that ran on the pull request merged last, or on the default branch's
  latest commit when none has merged (`checks_source` says which). If GitHub refused a request
  while finding them, `checks` is empty and `required_checks` isn't available: say so, with its
  `reason`. The default branch's checks never stand in for checks that couldn't be read.
- Mention any other ruleset in `rulesets.existing` whose `targets_default_branch` is true, and
  `classic_protection` when true: this skill leaves both as they are, and their rules apply
  alongside its own. `targets_default_branch` is GitHub's own answer: the ruleset is enforced
  and its conditions match the default branch.
- If `rulesets.ours` names this skill's ruleset but its entry's `targets_default_branch` is
  false, say so, with its `enforcement` when that isn't `active`: none of its rules is in
  force, so `current` counts them as not set, and applying starts it over with only the rules
  chosen.

## 2. Ask

One AskUserQuestion call, with a question for each group that has an available option. Leave
out options that aren't available. Mark each option's default by ending its label with
"(default)"; in its description, say "already set" when `current` already matches it.
Multi-select questions start with nothing ticked, so say in the first question that answering
"defaults" (through Other) takes every default.

1. **Merge settings** (multi-select): `squash_only`, `squash_message`, `delete_branch`,
   `auto_merge_off`. Describe `squash_message` plainly: the pull request's description becomes
   the commit's body, so the decisions it records land in git history.
2. **Rules for the default branch** (multi-select): `require_pull_request`, `required_checks`
   (name the checks and `checks_source`; when there are more than four, the user may name a
   subset through Other), `resolve_threads`, `block_force_push_and_deletion`.
3. **Required approvals** (single choice): 0 (default), 1, 2. Say that GitHub doesn't let anyone
   approve their own pull request, so on a repository where one person opens and merges pull
   requests, 1 or more blocks every merge unless that person may bypass it (question 4).
4. **Who may bypass the ruleset** (single choice), with `admin_holders` in the question:
   - **Admins, when merging a pull request (default):** an admin can merge a pull request that
     lacks approvals or checks by choosing to bypass at merge time (`gh pr merge --admin`), but
     can't push to the default branch directly.
   - **Nobody:** every rule binds everyone.
   - **Admins, always:** admins can also push to the default branch directly.

   Say that rulesets grant a bypass to a role, not to one person, which on a personal
   repository is the owner alone.

`resolve_threads` and approvals belong to the pull request rule, so the plan carries `approvals`
only with `require_pull_request`, and `apply.py` refuses it otherwise, even 0. If the user picks
`resolve_threads` without `require_pull_request`, or an approvals answer that would change
something (one other than `approvals.current`, or above 0 when that is null), say so and ask
whether to add the rule; otherwise leave `approvals` out of the plan. Questions 3 and 4 matter
only with a ruleset; skip them when no rule from question 2 is chosen.

When `rulesets.ours` is set, its rules are in force, and the user ticks only some of them,
say that a rule left unticked stays as it is: a later run adds rules and sets what the plan
names, but never removes a rule or turns off thread resolution. To drop one, the user edits
the ruleset on GitHub. The chosen checks do replace the required ones: when
`required_checks.current` names a check the choice leaves out, say it will no longer be
required.

## 3. Apply

Write the plan to a file in the scratchpad (or `mktemp -d`), using only what was chosen:

```json
{
  "repo": "owner/name",
  "merge": ["squash_only", "squash_message"],
  "ruleset": {
    "require_pull_request": true,
    "approvals": 0,
    "resolve_threads": true,
    "checks": ["test"],
    "block_force_push_and_deletion": true,
    "bypass": "admins_pull_request"
  }
}
```

`"ruleset": null` when no rule was chosen. On a later run, a plan without `approvals` keeps the
pull request rule's count, and one without `bypass` keeps the bypass list. Then:

```bash
python3 -I ${CLAUDE_SKILL_DIR}/scripts/apply.py --plan <plan file>
```

It creates the ruleset "repo-setup: default branch", or updates it in place on a later run,
keeping the rules and parameters the plan doesn't choose. A ruleset that GitHub doesn't enforce
on the default branch (`targets_default_branch` false: it isn't active, or its conditions were
changed to other branches) keeps none of its rules or bypass list, and becomes active on the
default branch with only the rules chosen. It
prints a report and exits 1 if any change failed or reads back differently: for the ruleset,
every value it saved is compared, from its name and target down to each rule's parameters
and the bypass mode.
`--dry-run` prints the calls instead; use it when the user asks what would change.

## 4. Report

- A table of each setting: before, after, and whether it reads back as asked. A setting whose
  `after` is null couldn't be read back: say whether it was saved (`saved`), and that it needs
  checking on GitHub.
- The ruleset's link (`ruleset.url`), its rules, and its bypass as GitHub names it
  (`ruleset.bypass`, for example the role `admin`, pull requests only). When `ruleset.ok` is
  false, each of `ruleset.mismatches`, word for word. A ruleset that was saved but couldn't be
  read back still has its link and `ruleset.action`: say it was created or updated, and that
  it needs checking on GitHub.
- What wasn't available, and why.
- Other rulesets and branch protection left as they were.
- With approvals above 0 and an admin bypass: merging one's own pull request takes the bypass,
  `gh pr merge --admin` or GitHub's "bypass rules" checkbox.
- Any error from the report, word for word.
