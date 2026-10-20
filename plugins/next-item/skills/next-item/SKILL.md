---
name: next-item
description: Do the next item of the current repository's implementation plan by following the "Doing the next item" section of its AGENTS.md. Use when the user runs /next-item or asks to do, start, or pick up the next item or next step of the plan. The procedure lives in each repository; this skill only finds it and follows it.
---

# Next item

The procedure is not here. Each repository that supports this keeps it in the
**Doing the next item** section of its `AGENTS.md`, beside the rules, checks,
and pull request conventions it refers to. That section is the only source of
truth: this skill adds no steps, and where the two seem to differ, `AGENTS.md`
wins.

1. Find the repository root with `git rev-parse --show-toplevel`, and read
   `AGENTS.md` there in full.
2. If there is no `AGENTS.md`, or it has no section headed "Doing the next
   item", stop and tell the user. Do not borrow the procedure from another
   repository or improvise one.
3. Follow the section exactly, together with the parts of `AGENTS.md` it
   refers to, such as the rules and the conventions for commits and pull
   requests.
4. The section's first step updates `main`. Re-read `AGENTS.md` and the
   implementation plan after that pull, because it may have changed them.
5. Finish with the report the section asks for.

If the user passed text with the command, treat it as extra instructions for
this run: $ARGUMENTS
