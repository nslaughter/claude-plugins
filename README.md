# claude-plugins

The owner's Claude Code plugin marketplace, named `nslaughter`. The plugins cover writing, reading, and reviewing code, infrastructure as code, and config. Skills and hooks ship inside plugins, and each plugin lives under `plugins/`.

## Install

```
/plugin marketplace add nslaughter/claude-plugins
/plugin install <plugin>@nslaughter
```

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
