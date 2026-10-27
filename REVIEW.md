# Review

What reviewers of this repository look for, and which changes the owner reads. The agent-pr-review mod reads this file from the default branch, so a pull request can't change the rules it is held to.

## What failure looks like here

These plugins run in a developer's own Claude Code session, on their own repositories, with their own GitHub account. A change goes wrong here in four ways:

- **A skill acts without the person:** it tells an agent to merge, approve, push to a default branch, force-push, change repository settings or post to GitHub when the person didn't ask, or to spend their usage on another service.
- **The docs lie:** a SKILL.md names a step, flag, path or script output that the scripts don't have, so the agent following it fails or improvises.
- **An install breaks:** the marketplace or a plugin manifest names a plugin, path or version wrongly, and installing fails for everyone.
- **Something private is published:** the repository is public, so a token, an email address, a local path such as `/Users/<name>/`, or material from a private repository must never land in it.

## Highest risk

- `plugins/*/skills/*/scripts/`
- `plugins/*/hooks/`

## Always needs the owner

- `.claude-plugin/marketplace.json`
- `plugins/*/.claude-plugin/plugin.json`
- `REVIEW.md`
- `LICENSE`

## Skip

Nothing yet: the repository has no generated or vendored files.

## Findings

- Every finding cites a file and a line, and says what goes wrong there.
- At most 3 nits in a review.
- A review's summary starts with how many findings it has, and says plainly when nothing needs fixing.
- Check every step, flag, path and output a SKILL.md names against the scripts and files it refers to.
- Judge a failure by how these plugins are used: one person, in their own session, on their own repositories. Don't ask for hardening against inputs that use won't produce.
