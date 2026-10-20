---
name: iterative-review
description: Run an iterative review loop on a pull request, in a fixed sequence. An OpenAI Codex reviewer and a fresh Claude reviewer review the change at the same time and hand their findings back, and the orchestrator posts each one as a comment-only review comment where its problem is; the reviewers never post or fix anything. A Claude fix agent addresses both reviews and replies under each comment; Codex reviews the fixes; Claude fixes again. It stops early when a review finds nothing. Defaults to the repository's only open PR. Takes a PR number when several are open, --codebase to review the whole checked-out code, and --review-only to report the first two reviews to the user without posting anything. Use whenever the user asks for an iterative review, a review/fix loop or cycle, several review rounds, or a Codex/OpenAI review of a PR with fixes in between. For a single review with no fix rounds, the code-review skill fits better.
argument-hint: "[PR number] [--codebase] [--review-only]"
---

# Iterative review

Arguments: $ARGUMENTS

The user's sequence, with at most three reviews and two fixes:

1. **Reviews 1 and 2, at the same time:** Codex reviews the change, and so does a fresh Claude
   reviewer. When both are back, the Claude reviewer reconciles its findings with Codex's.
2. **Fix 1:** a Claude fix agent addresses the findings of reviews 1 and 2.
3. **Review 3:** Codex reviews the change again, with the fixes.
4. **Fix 2:** a Claude fix agent addresses review 3's findings. The loop ends there.

Two reviewers from different models catch more on the first look at the whole change, where most
defects are. Codex then checks the fixes, which Claude wrote. The roles stay apart:

- **The reviewers** find problems and hand them back to you. They never post, edit, or fix
  anything. Codex runs in a read-only sandbox, so it can't change anything even by accident. The
  Claude reviewer is a new general-purpose subagent, never a fork of a session that wrote or
  fixed the code, so it comes to the change fresh.
- **The fix agent** is a separate Claude subagent. It fixes each finding or declines it with a
  reason, pushes, and replies under each comment.
- **You** orchestrate. You pick the target, prepare the worktrees, run the reviewers, post every
  review yourself, dispatch the fix agent, decide whether to go on, and report. Don't review or
  fix code yourself, even when a fix looks trivial: the user's process depends on the separation.

**Every finding is posted where its problem is.** Each review is one GitHub review with event
`COMMENT`. A finding on a line the diff shows is an inline comment on that line. One on another
line of a file the PR changes is a comment on that file, headed by the line it names, because
GitHub takes line comments only on diff lines. Only a finding in a file the PR doesn't touch goes
in the review's body. A review never approves, requests changes, or resolves threads.

**Nothing this skill touches is ever merged without a human's review.** Not by you, not by the fix
agent, and not by enabling auto-merge, however clean the last review was. A finished loop means
the PR is ready for the user's review, not that it's approved. The user reviews, resolves the
threads, and merges.

## Requirements

- **`gh`,** signed in, for everything but `--codebase --review-only`.
- **Python 3,** for `scripts/post_review.py`. It needs only the standard library.
- **The OpenAI `codex` CLI, optional.** Without it, or when it isn't logged in, a fresh Claude
  reviewer takes reviews 1 and 3 (see Preflight).

## Arguments

- **A PR number:** `13`, `#13`, or the PR's URL. Needed when more than one PR is open.
- **`--codebase`:** review the whole checked-out code instead of a PR. "The whole codebase", "all
  the code", or "the checked-out code" mean the same.
- **`--review-only`:** run reviews 1 and 2, post nothing anywhere, and give the user an account of
  their findings. No fix runs, and so no review 3: a review of unchanged code would find the same
  things.

With no flags, the mode is the full sequence, with comment-only reviews posted. A PR number
together with `--codebase` contradicts itself: ask which one is meant.

## 1. Preflight

1. **GitHub.** `gh auth status` must pass, unless the run is `--codebase --review-only`, which
   needs no GitHub at all. Find the repository with
   `gh repo view --json nameWithOwner,defaultBranchRef`, and `git fetch origin`.
2. **Codex.** `codex --version` and `codex login status` must both succeed. If either fails, tell
   the user, and use a fresh Claude reviewer for reviews 1 and 3 instead, still running reviews 1
   and 2 at the same time. The loop then has only one model, so say so in the report.
3. **A run directory** for prompts, findings, and state: the session's scratchpad directory if it
   has one, otherwise `mktemp -d`. Keep `state.json` there, updated after every step: the target,
   each review's head SHA, files, and status, and each fix's result. If the session is
   interrupted, a later run can pick up from it.
4. **The repository's limits.** Read its `AGENTS.md`, `CLAUDE.md`, and `CONTRIBUTING.md`, and what
   you know of the user's rules for it, for anything an agent mustn't do while reviewing or
   fixing: tests that cost money or need credentials, folders of private or account data, a
   secret manager. Write them as a short list; both prompt templates carry it.

## 2. Choose the target

- **A PR number was given:** use it.
- **`--codebase`:** the checked-out `HEAD`. If the working tree has uncommitted changes, ask
  whether to wait until they're committed. The reviewers see only committed code, and fixes
  branch from `HEAD`.
- **Neither:** `gh pr list --state open --json number,title,headRefName,author`.
  - One open PR: use it.
  - None: say so and stop. Suggest `--codebase`.
  - Several: ask the user which one with AskUserQuestion, listing each one's number, title, and
    branch. Don't guess.

For a PR, read `gh pr view <n> --json number,title,body,url,headRefName,headRefOid,baseRefName,isCrossRepository,author`.
If it comes from a fork (`isCrossRepository`), or someone other than the user wrote it, the fix
agent shouldn't push to it. Ask whether to run `--review-only` instead, or the reviews with no
fixes.

## 3. Prepare the worktrees

Before any review starts, so no agent waits for a checkout or an install. `git fetch origin
<headRefName>` first. For `--codebase`, use `HEAD` wherever these say the head.

- **`<run>/codex-wt`:** `git worktree add --detach <run>/codex-wt <head sha>`, for Codex. Codex's
  sandbox can't install anything, so this one needs no setup.
- **`<run>/claude-wt`:** the same, at the head, for the Claude reviewer. Run the project's setup in
  it, as its instructions give it (for example `uv sync`, `npm ci`), so the reviewer can run the
  tests straight away. It's a disposable copy, so caches its tests write don't matter.
- **`<run>/fix-wt`:** the same, at the head, with the setup run, for the fix agents. Skip it for
  `--review-only`, and for `--codebase`, where fix 1 creates its own branch.

Run the setups in the background while you write the prompts. They're ready long before the
reviews finish.

## 4. Running a review

`<N>` is the review's number, 1 to 3.

1. **The base:** `git merge-base origin/<baseRefName> <head sha>`.
2. **Write the prompt:** fill in [references/reviewer-prompt.md](references/reviewer-prompt.md),
   keeping the sections for this scope and this review, and write it to
   `<run>/review-<N>-prompt.md`. **Review 3** keeps the earlier-reviews section, with every
   finding of reviews 1 and 2 and the fix agent's resolution of each, so it checks the fixes and
   doesn't raise a declined finding again without new evidence.
3. **Run the reviewer.** A review can take many minutes.
   - **Codex** (reviews 1 and 3), in the background:

     ```bash
     codex exec --sandbox read-only --ephemeral -C <run>/codex-wt \
       --output-schema ${CLAUDE_SKILL_DIR}/references/findings.schema.json \
       -o <run>/review-<N>.json - < <run>/review-<N>-prompt.md
     ```

     For review 3, first `git -C <run>/codex-wt fetch origin <headRefName>` and
     `git -C <run>/codex-wt checkout --detach <new head sha>`.
   - **Claude** (review 2): a new general-purpose subagent, never `fork`, whose prompt is the
     contents of `review-2-prompt.md`, then the output schema from
     [references/findings.schema.json](references/findings.schema.json), which nothing enforces
     for it as `--output-schema` does for Codex, then: "Work in `<run>/claude-wt`, where the
     project's setup has run. Don't edit any file, except to run the mutation checks your
     prompt describes, which you undo. Running the tests there is fine: it's a disposable copy.
     Start any slow test run in the background first, and read the change while it runs. End
     your reply with the JSON object, alone in a json code block." Its prompt keeps the template's
     `<!-- Claude reviewer only -->` section, and Codex's doesn't. The Claude reviewer can run
     tests Codex's sandbox blocks, such as ones that install packages or open a local server,
     and it checks that each new test fails when the behavior it covers is broken: that's what
     it adds. When it's done, check that `git -C <run>/claude-wt status --short` is empty; if a
     mutation was left behind, say so in the report. Keep its agent ID: you send it review 1's
     findings to reconcile.
4. **Check the output** parses as JSON with `summary` and `findings`, and that each finding's
   `path` exists in the worktree. If it fails, run that review once more. If it fails again, use
   a fresh Claude reviewer for it, and say so in the report.
5. **Post it,** unless the mode posts nothing. You post every review; no reviewer posts its own.
   - **Default mode, PR scope:**

     ```bash
     python3 ${CLAUDE_SKILL_DIR}/scripts/post_review.py --pr <n> \
       --commit <head sha> --review <N> --findings <run>/review-<N>.json \
       --out <run>/comments-<N>.json --source <the reviewer's worktree>
     ```

     It posts each finding inline on its line when the diff shows that line, as a comment on its
     file, quoting the line, when the file is in the PR but the line isn't in the diff, and in the
     review's body only when the PR doesn't touch the file. Run it with `--dry-run` first if a
     review has many findings outside the diff, and check each is anchored where its problem is.
     It writes each finding's comment ID and anchor to `comments-<N>.json`, for the fix agent's
     replies. A review with no findings is posted too, as a short review that says so, so the PR
     records it. Posted text names no tool or model: the comments appear under the user's name.
   - **`--review-only`:** post nothing.
   - **`--codebase`, reviews 1 and 2:** there's no PR to comment on yet. Fix 1 opens one, and its
     description records both reviews' findings and their resolutions. Review 3 reviews that PR,
     and everything from then on is as for PR scope.

## 5. The sequence

1. **Start reviews 1 and 2 together:** Codex in the background, and the Claude reviewer as a
   background subagent, with the same head and base. Neither sees the other's findings while it
   reviews.
2. **Post review 1 as soon as it's back** and checked, without waiting for review 2.
3. **Reconcile, once both are back.** If review 1 found anything, send its findings to the Claude
   reviewer that did review 2, with SendMessage to its agent ID, so it keeps its context:

   > Review 1, by a reviewer from a different model, is in `<run>/review-1.json`. Read it now and
   > reconcile your findings with it. Drop any finding of yours that repeats one of theirs: the
   > same defect, even if worded or anchored differently. If you believe one of their findings is
   > wrong, add a finding of your own, anchored where theirs is, with the category
   > `disputed-finding`; its title names their finding by number (1-based, in their order), and
   > its body gives your evidence. Keep everything else. End with your full, updated JSON object,
   > alone in a json code block.

   Write its answer to `<run>/review-2.json`, check it, and post it. If review 1 found nothing,
   post review 2 as it came.
4. **`--review-only`** stops here, and goes to the report.
5. **If neither review found anything,** the loop ends: the change is clean.
6. **Fix 1** addresses both reviews' findings. See below.
7. **Go on to review 3** only if reviews 1 or 2 had a significant finding, one of high or medium
   severity, or fix 1 reports `significant_changes`, and fix 1 pushed at least one commit.
   Otherwise the loop ends: minor fixes don't need another review.
8. **Review 3.** If it found nothing, the loop ends.
9. **Fix 2** addresses review 3's findings. The loop ends. Fix 2's commits reach the user's review
   without another automated review, so the report lists them first among what to look at.

### Running a fix

1. **Dispatch the fix agent:** a new general-purpose subagent, with
   [references/fixer-prompt.md](references/fixer-prompt.md) filled in for this scope and fix.
   Give it each review's findings file and comment map, and `<run>/fix-wt`, which is ready.
   Wait for its notification.
2. **Read the JSON** it ends with. Check the PR's head yourself (`gh pr view <n> --json
   headRefOid`) rather than trusting the SHA it reports, and that its claims match: replies
   posted under each thread, and checks run, including, for each test it added or changed, that
   the test failed without its fix. Note any gap for the report, rather than fixing it
   yourself.

## 6. Report

End with an account the user can act on without opening the PR. The user reads the PR in
another pane and answers here, so the report says plainly what needs them.

**Decisions for you** comes right after the table, and is never left out: when there's nothing,
it says "None: nothing in this PR awaits your decision." It numbers everything that needs the
owner's decision or sign-off:

- each finding a fix agent left as `needs_owner`;
- each item in a fix agent's `owner_confirmations`;
- anything the PR still asks the owner to confirm. Read its description again, and the documents
  on its branch where, by the repository's instructions, items await the owner, such as a list
  of changes awaiting confirmation. Include items from earlier work that those documents still
  mark as awaiting the owner, though this PR didn't start them.

Each item says what's being decided and where (a thread's link, or `path:line`), the options,
and the one you recommend, with why. A declined finding isn't a decision, unless the fix agent's
reason turns on one: it stays under Declined, where the user can overrule it.

**After the full sequence:**

```markdown
## Iterative review of #<n>: <title>

<url> · ended: <clean after review N | no significant changes after fix 1 | after fix 2 | stopped: why>

| Step | Reviewer or agent | Findings (high/medium/low) | Fixed | Declined | Needs owner | Commits |
|---|---|---|---|---|---|---|
| Review 1 | Codex | 2/3/1 | | | | |
| Review 2 | Claude | 0/2/2 | | | | |
| Fix 1 | Claude | | 8 | 1 | 1 | abc1234, def5678 |
| Review 3 | Codex | 0/1/0 | | | | |
| Fix 2 | Claude | | 1 | 0 | 0 | 9876fed |

### Decisions for you

1. **<short name>** (<thread link, or path:line>): <what's being decided, in a sentence>.
   Options: <a>; <b>. **I recommend** <one of them>, because <why>.
2. ...

Reply "confirm all", or give an item's number and your change. I'll record your decisions in the PR.

**Not reviewed again:** fix 2's commits, with what each changed.
**Declined:** each finding declined, with the fix agent's reason, so you can overrule it.
**Disputed:** any review 1 finding that review 2 argued was wrong, and how fix 1 settled it.
**Checks:** what the last fix agent ran, and the result, and which new tests were shown to fail
without the behavior they cover: by the Claude reviewer, or by a fix agent without its fix.

The threads are left for you to resolve. Nothing was merged: the PR waits for your review.
```

**After `--review-only`:** an account of each finding of reviews 1 and 2, grouped by severity: which
reviewer found it, its `path:line`, its title, what's wrong and why it matters, and the fix the
reviewer suggests. Note the findings both reviewers raised, and any review 1 finding review 2
disputed. Then each reviewer's summary. Mention that nothing was posted. If anything needs the
user's decision, end with **Decisions for you**, as above.

## 7. Recording the owner's decisions

When the user answers the decisions, confirming or changing them, record their answer in the PR
in the next turn, so it shows the owner made each decision:

1. **A worktree** at the PR's head: `git fetch origin <headRefName>`, then
   `git worktree add <run>/decide-wt <headRefName>`.
2. **A changed decision that needs code,** tests, or a requirement rewritten goes to a fix agent,
   with the decision as its finding. You don't write the code.
3. **Record each decision** where the repository's instructions say the owner's decisions are
   recorded, for example "confirmed by the owner on <date>" in place of "awaiting the owner's
   confirmation", and in any status the documents keep. Commit in the repository's convention,
   and push.
4. **Update the PR description:** an "Owner sign-off" section that names each decision, what the
   owner chose, the date, and the commit that records it. Reply under any thread a decision
   settles.
5. **Report** what you recorded, with the commit, and that nothing was merged. Remove the
   worktree once it's pushed.

## Ground rules

- **The repository's rules come first.** Its `AGENTS.md`, `CLAUDE.md`, and `CONTRIBUTING.md` govern
  branches, commits, checks, and what needs the owner. Pass them on to the fix agent; the
  template tells it to read them. Pass the limits from preflight to every agent.
- **Reviewers only hand back findings.** You post every review and comment; no reviewer posts.
- **History stays as it is.** No force-push, rebase, or amend during the loop: inline comments are
  anchored to commits.
- **No hooks bypassed.** Never pass `--no-verify`.
- **No pushing to the default branch, and no merging.** Never merge, approve, or enable
  auto-merge on a PR this skill worked on, and don't offer to: a human reviews it first.
- **Cost.** Each Codex review uses the user's OpenAI quota, and each Claude review and fix the
  user's Anthropic usage. That's one reason the sequence stops at three reviews.
- **Clean up.** When the loop ends, remove `<run>/codex-wt` and `<run>/claude-wt` with
  `git worktree remove --force` (the Claude reviewer's has its setup's files), and `<run>/fix-wt`
  if it's clean and pushed. Keep the run directory's files, which are the record, and say where
  they are.
