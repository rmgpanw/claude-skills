# claude-skills

Personal [Claude Code](https://claude.com/claude-code) plugins, kept in one repo so
they can be installed on any machine.

## Install

Run these once per machine. The `claude` CLI form works everywhere:

```bash
claude plugin marketplace add rmgpanw/claude-skills
claude plugin install zotero@claude-skills --scope user
```

Inside an interactive Claude Code terminal session you can instead use the slash
commands `/plugin marketplace add rmgpanw/claude-skills` and
`/plugin install zotero@claude-skills`. **These are not available in every
environment** — the VS Code extension, for one, reports `/plugin isn't available
in this environment`. Use the CLI form if in doubt.

The first command registers this repo as a plugin *marketplace* — an index of what
is available here. The second installs a plugin from it. Restart Claude Code
afterwards; plugins load at session start.

After that the skills load automatically whenever a request matches them. There is
nothing to invoke by hand and no need to reference this repo again.

## Updating

Two separate steps — refreshing the marketplace index does **not** upgrade an
already-installed plugin:

```bash
claude plugin marketplace update claude-skills     # refresh the index
claude plugin update zotero@claude-skills          # upgrade the plugin itself
```

The plugin name must be fully qualified as `plugin@marketplace`; the bare name
fails with `Plugin "zotero" not found`. Restart Claude Code to apply.

Check what is installed with `claude plugin list`.

## Plugins

| Plugin | What it does | Setup required |
|---|---|---|
| [`zotero`](plugins/zotero) | Adds references to a Zotero library from PubMed, matching the metadata Zotero's own browser connector produces | Yes — a Zotero API key and userID, see [its README](plugins/zotero/README.md) |

## Layout

```
.claude-plugin/marketplace.json     index of the plugins below
plugins/<plugin>/
  .claude-plugin/plugin.json        name, version, description
  skills/<skill>/SKILL.md           the skill itself
  skills/<skill>/scripts/           anything the skill shells out to
  README.md                         human-facing setup notes
```

## Adding another plugin

1. Create `plugins/<name>/` with a `.claude-plugin/plugin.json` and a
   `skills/<skill>/SKILL.md`.
2. Add an entry to the `plugins` array in `.claude-plugin/marketplace.json`.
3. Commit and push. Other machines get it via `/plugin marketplace update`.

Bump the `version` in a plugin's `plugin.json` when you change it — Claude Code uses
that to decide whether to auto-update. Without a version it pins to the commit SHA.

## Notes

Skills are invoked as `plugin-name:skill-name` when named explicitly, so plugin and
skill names deliberately differ (`zotero:zotero-refs`, not `zotero-refs:zotero-refs`).

No credentials live in this repo. Anything secret is read at runtime from
`~/.config/zotero/`, which is never committed.
