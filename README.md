# claude-skills

Personal [Claude Code](https://claude.com/claude-code) plugins, kept in one repo so
they can be installed on any machine.

## Install

Run these once per machine, inside Claude Code:

```
/plugin marketplace add rmgpanw/claude-skills
/plugin install zotero@claude-skills
```

The first command registers this repo as a plugin *marketplace* — an index of what
is available here. The second installs a plugin from it. After that the skills load
automatically whenever a request matches them; there is nothing to invoke by hand
and no need to reference this repo again.

To pick up later changes:

```
/plugin marketplace update claude-skills
```

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
