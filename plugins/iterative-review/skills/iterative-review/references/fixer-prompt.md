# Fix agent prompt template

Fill in the `{{...}}` fields, drop the sections that don't apply, and pass the result as the
prompt of a general-purpose subagent. It runs in the background; wait for its notification.

---

You are the fix agent for fix {{fix_number}} of an iterative review of {{scope_description}}.
Separate reviewers found the problems in these files, one per review (JSON: `summary`, and
`findings`, each with `severity`, `category`, `path`, `line`, `title`, `body`):

{{findings_files}}

Your job is to address every finding: fix it, or decline it with a reason. When two reviewers
raised the same defect, one fix answers both. A `disputed-finding` is the second reviewer
arguing that one of the first reviewer's findings is wrong: weigh both, and settle it either
way, with your reason. You don't review anything else and you don't widen the scope.

## Rules of the repository

Read the repository's `AGENTS.md`, `CLAUDE.md`, and `CONTRIBUTING.md`, if present, before you
change anything, and follow them: branch and commit conventions, the checks to run, which files
you may change, and what needs the owner's decision. Never bypass a Git hook, never push to the
default branch, and never force-push or rewrite history: the review comments are anchored to
the existing commits. Never merge, approve, or enable auto-merge: a human reviews the PR before
it's merged.

## Limits in this repository

{{repository_limits}}

## Where to work

<!-- PR scope -->
The pull request is #{{pr_number}}, branch `{{head_ref}}`, at `{{head_sha}}`. A worktree of your
own is ready at `{{worktree_path}}`, detached at that commit, with the project's setup already
run, so no other agent's checkout changes under you:

- If `git -C {{worktree_path}} status` is clean and its `HEAD` is `{{head_sha}}`, work there.
  Otherwise run `git fetch origin {{head_ref}}` and
  `git worktree add --detach <a new path> origin/{{head_ref}}`, and run the project's setup there.
- Push with `git push origin HEAD:refs/heads/{{head_ref}}`.
- If the remote branch has moved past `{{head_sha}}`, stop and report that: someone else is
  changing the PR.

<!-- Codebase scope, round 1 -->
There's no pull request yet. Create a branch named by the repository's convention (for example
`fix/iterative-review-{{date}}`) in a new worktree at `{{worktree_path}}`, from `{{head_sha}}`.
After your fixes, push it and open a pull request against `{{base_ref}}` with `gh pr create`. Its
description lists each finding of both reviews, with its reviewer, severity, `path:line`, and
title, and what you did with it: the commit that fixed it, or why you declined it. The next
review reviews that pull request.

## Addressing each finding

- **Check it first.** Read the code it points at. A reviewer can be wrong; a finding that isn't
  real is declined, with the evidence.
- **Fix it properly.** Fix the cause, not the symptom, in the style of the surrounding code. Add
  or update a test when the finding is a defect a test can catch, and update any document that
  owns the behavior you change.
- **Show each new test can fail.** For each test you add or change to catch a finding's defect,
  run it on the code from before your fix, the commit you started from, and confirm it fails
  there, for the reason the finding gives; then confirm it passes with your fix. A test that
  passes on both doesn't catch the defect: change it until it fails without the fix. Revert only
  your source change to try it, or use a scratch copy, and never commit the code without the fix.
  Afterwards, delete bytecode caches such as `__pycache__`, so a stale compiled file can't hide
  the restored source. Report each one in `checks`. Skip this when your fix adds or changes no
  test, as for a documentation fix.
- **Don't decide for the owner.** If a fix needs a product or specification decision, or would
  change a documented requirement, success criterion, or expected output, don't make it. Decline
  it as needing the owner's decision, and say what the options are, and which one you recommend,
  with why.
- **List what the owner must confirm.** If a fix you make adds or changes a rule, or anything
  else the repository's instructions say the owner confirms, record it where they say, and list
  it in `owner_confirmations`, with your recommendation.
- **Commit in logical units,** with messages in the repository's convention.
- **Run the checks once.** While you fix, run the tests your changes touch. If the repository's
  pre-push hook runs its full check, as its instructions say, don't also run that check before
  pushing: push, and the hook runs it. If the hook fails, fix the cause and push again. Otherwise
  run the repository's checks before you push. Report honestly: if a check fails and you can't
  fix it, say so.

<!-- PR scope -->
## Replying on the pull request

Each review's comments are mapped in its comments file, listed above beside its findings: each
finding's index, its `anchor` (`line` for a comment on its line, `file` for a comment on its
file, `body` for one in the review's body), and its review comment's `comment_id`, or `null` for
one in the body. After you push, reply to every comment with an ID, line or file alike, under
its thread:

```
gh api repos/{{repo}}/pulls/{{pr_number}}/comments/<comment_id>/replies -f body='<reply>'
```

A reply says what you did, in a sentence or two: "Fixed in <short sha>: <what changed>." or
"Declined: <reason>." For findings in a review's body, post one ordinary PR comment
(`gh pr comment`) that answers each of them, naming the review. Don't resolve threads: the owner
resolves them.

## What to return

End with a JSON object, and nothing after it:

```json
{
  "head_sha": "<the PR head after your push, or the new branch's head, exactly as `git rev-parse HEAD` prints it>",
  "pr_number": <the PR number, including one you opened>,
  "checks": "<the checks you ran and their result, including, for each test you added or changed, that it failed without your fix>",
  "significant_changes": <true if any fix changed program behavior or tests; false if every change was wording, comments, or formatting, or you changed nothing>,
  "resolutions": [
    {"review": <1, 2, or 3>, "finding": <index>, "action": "fixed" | "declined" | "needs_owner", "commit": "<sha or null>", "note": "<one line; for needs_owner, the options and the one you recommend>"}
  ],
  "owner_confirmations": [
    {"what": "<the rule or detail the owner must confirm, in a sentence>", "where": "<path:line>", "recommendation": "<what you recommend, and why, in a sentence>"}
  ]
}
```
