# claude-plugins

The owner's Claude Code plugin marketplace, named `nslaughter`. The plugins cover writing, reading, and reviewing code, infrastructure as code, and config. Skills and hooks ship inside plugins, and each plugin lives under `plugins/`.

## Install

```
/plugin marketplace add nslaughter/claude-plugins
/plugin install <plugin>@nslaughter
```

## Plugins

- **go-errors**: finds error-handling mistakes in Go code that errcheck misses, such as swallowed errors, unchecked `Close` calls, shadowed errors and misused `errors.Is` and `errors.As`, and wraps bare `return err` statements with context.
- **go-test**: writes Go tests of eight kinds (table-driven, adversarial, fuzz, property, txtar script tests, mocks, benchmarks) and finds coverage gaps. Each skill checks that its kind of test fits the code and points to a better one when it doesn't. `compare-benchmarks` runs benchmarks on two git states and compares them with `benchstat`.
- **iterative-review**: a review-and-fix loop on a pull request. Codex and a fresh Claude reviewer review in parallel, a Claude fix agent addresses the findings, Codex reviews the fixes, and Claude fixes again. Needs `gh`; the Codex CLI is optional.
- **next-item**: does the next item of a repository's implementation plan by following the "Doing the next item" section of its `AGENTS.md`.

## Layout

```
.claude-plugin/marketplace.json     marketplace manifest; lists every plugin
plugins/<plugin>/
  .claude-plugin/plugin.json        plugin manifest
  skills/<skill>/SKILL.md
  hooks/hooks.json
```

## Adding a plugin

1. Create `plugins/<plugin>/` with its `.claude-plugin/plugin.json`.
2. Add an entry to `plugins` in `.claude-plugin/marketplace.json`:
   `{ "name": "<plugin>", "source": "./plugins/<plugin>", "description": "..." }`
3. Run `claude plugin validate .` before pushing.
4. Bump `version` in a plugin's `plugin.json` whenever it changes. Installed copies update only when the version changes.
