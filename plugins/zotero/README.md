# zotero

Adds references to a Zotero library from **PubMed**, via the Zotero Web API.

Give Claude a manuscript, a bibliography or a list of DOIs and ask for them in a
Zotero library. It resolves each reference to a PubMed record, converts it to a
Zotero item, skips anything already present, and creates the rest.

Metadata is taken from PubMed in preference to the publisher, and is post-processed
to match what Zotero's own browser connector stores — so API-added items are
indistinguishable from ones saved with the browser plugin.

## Setup

Two credential files are required. **Neither lives in this repo**; both are read at
runtime from `~/.config/zotero/`.

### 1. API key

Create one at <https://www.zotero.org/settings/keys> → *Create new private key*.

- Tick **Allow write access** for the personal library if you will write there.
- **For a group library, tick write access for that specific group.** This is the
  single most common failure. A key scoped only to your personal library is
  accepted by the API and then silently refuses group writes.

Save it:

```bash
mkdir -p ~/.config/zotero
printf '<your-api-key>' > ~/.config/zotero/api_key
chmod 600 ~/.config/zotero/api_key
```

### 2. Numeric userID

Shown on the same settings page as *"Your userID for use in API calls is 1234567"*.
It is not your username, and it is not secret.

```bash
printf '<your-user-id>' > ~/.config/zotero/user_id
chmod 600 ~/.config/zotero/user_id
```

### 3. Verify

```bash
python3 skills/zotero-refs/scripts/zotero_pubmed.py check
python3 skills/zotero-refs/scripts/zotero_pubmed.py groups          # list group IDs
python3 skills/zotero-refs/scripts/zotero_pubmed.py check --library groups/<id>
```

`check` confirms the key authenticates and that it can actually **write** to the
library you intend to use. Every command that touches a library runs this first and
exits with instructions rather than failing later or prompting.

Requires **Python 3.7+**, standard library only — nothing to `pip install`.

If `python3` is missing: macOS `xcode-select --install`, Linux use your distro package.

## Usage

Just ask, in any repo:

> add the references from `manuscript.md` to my *Reading Group* Zotero library

> add the new citations in `manuscript.qmd` to `references.bib`

Claude loads the skill automatically. Items created through the API appear in the
Zotero desktop app only after a **sync**.

The underlying pipeline, if you want to drive it by hand:

```
resolve  → DOIs/citations to PMIDs
fetch    → PubMed records (XML, plus .nbib for provenance)
convert  → Zotero items, normalised
dedupe   → drop anything already in the target library
create   → write them
sync-bib → report on a .bib against the library; append what is missing with --write
```

## What it handles

- **PubMed vs publisher disagreements** are surfaced, not silently resolved.
  Real examples: a consortium paper PubMed files under only its collective name
  while the journal lists every author; PubMed has `Davey Smith, George` where
  bmj.com has `Smith, George Davey`.
- **Connector-matching metadata** — journal names title-cased, abbreviated page
  ranges expanded (`134-43` → `134-143`), initials given periods.
- **Records PubMed does not have** (methods/stats journals, software, preprints)
  fall back to Crossref, or become a `computerProgram` item for software, with the
  source noted in `Extra`.
- **Duplicates**, by DOI and PMID, against live library state.
- **Existing `.bib` files** are appended to, never rewritten. Keys that differ from
  the library are reported, because a full export would break those citations. Name
  formatting is left to your CSL style; journal abbreviations are added as
  `shortjournal`, since a style cannot create them.

## Known limitation

The rule that journal names beginning with an acronym are left uncapitalised
(`JAMA ophthalmology`) is empirical, inferred from a single observed case. If items
come out cased oddly, diff a few against existing library entries before bulk
loading — the skill documents how.
