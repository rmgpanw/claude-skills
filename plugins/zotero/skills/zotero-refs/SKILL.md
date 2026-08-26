---
name: zotero-refs
description: Add references to a Zotero library from PubMed via the Zotero Web API - resolve DOIs/citations to PMIDs, convert PubMed records to Zotero items matching what the browser connector produces, dedupe against the target library, and create them. Use when asked to add, import, or sync references or a bibliography into Zotero, or to get a manuscript's reference list into a Zotero group/collection.
---

# Adding references to Zotero from PubMed

Loads a reference list (usually a manuscript bibliography) into a Zotero library,
preferring PubMed metadata over publisher metadata.

## Requirements

Python 3.7+, standard library only - nothing to `pip install`. If `python3` is
missing, that is an environment problem, not a skill problem: on macOS it arrives
with `xcode-select --install`; on Linux use the distro package. Do not attempt to
work around a missing interpreter.

## Credentials

- API key: `~/.config/zotero/api_key` (mode 600), numeric user ID: `~/.config/zotero/user_id`.
- Always pass the key by substitution so it never appears in a command or transcript:
  `-H "Zotero-API-Key: $(cat ~/.config/zotero/api_key)"`.
- If the key file is missing, ask the user to create one at
  https://www.zotero.org/settings/keys. **Group libraries need write access
  granted to that specific group** - a personal-library-only key silently
  cannot write to groups.
- Run `check` first; it verifies the key authenticates *and* can write to the
  intended library, and exits with the fix if not. Never prompt interactively -
  these scripts may run non-interactively.

      python3 scripts/zotero_pubmed.py check --library groups/<id>

## Library targets

`users/<id>` or `groups/<id>`. List the user's groups with:

    python3 scripts/zotero_pubmed.py groups

## Pipeline

    python3 scripts/zotero_pubmed.py check   --library groups/123
    python3 scripts/zotero_pubmed.py resolve --in refs.json --out ids.json
    python3 scripts/zotero_pubmed.py fetch   --ids ids.json --out-xml pm.xml --out-nbib pm.nbib
    python3 scripts/zotero_pubmed.py convert --xml pm.xml --out items.json
    python3 scripts/zotero_pubmed.py dedupe  --items items.json --library groups/123 --out todo.json
    python3 scripts/zotero_pubmed.py create  --items todo.json --library groups/123

`refs.json` is a list of `{"doi":…, "pmid":…, "title":…}` (any subset). Parse it
out of the manuscript first; take the PMID from the citation when it is printed
there, since that is more reliable than any lookup.

## Hard-won gotchas

These each caused a real, silent failure. Do not remove the guards.

1. **Scope the ArticleId lookup.** `.//ArticleIdList/ArticleId` also matches the
   *cited references* embedded at the end of a PubMed record, and the last match
   wins - stamping a wrong PMID on every item. Use `PubmedData/ArticleIdList`.
2. **The NCBI ID Converter (idconv) only covers PMC-indexed records.** It reported
   12/49 refs as "not in PubMed" when 10 of them were. Use it only as a fast first
   pass; `esearch` on `[AID]` then `[DOI]` is the authority, with a `[Title]`
   search as last resort.
3. **Modern Zotero has native `PMID`/`PMCID` fields** - use them rather than
   `Extra: "PMID: …"`. Confirm by POSTing one item and looking for empty-string
   `PMID`/`PMCID` keys in the response. If absent, fall back to `Extra`.
4. **Re-read live library state immediately before creating.** A dedupe snapshot
   taken before a test item was written will happily re-add that test item.
5. **50 items per POST**, and NCBI allows 3 requests/sec without an API key.
6. **Consortium authors** ("GBD 2021 Collaborators") come through as
   `CollectiveName` and must become a single-field Zotero creator (`name`),
   not firstName/lastName.
7. `PATCH` only touches the fields you send, so a bad value written earlier
   survives unless explicitly overwritten (send `""` to clear).

## Matching the browser connector's output

Raw PubMed data does not equal what Zotero's PubMed translator stores.
`scripts/zot_normalise.py` reproduces the differences, verified by diffing
against connector-added items in a real library (7/7 exact match):

- **Journal names are title-cased**: `Nature genetics` -> `Nature Genetics`.
  Acronyms, mixed-case and digit-bearing words are left alone, and a name led by
  an acronym is left entirely alone (`JAMA ophthalmology` stays lowercase - this
  rule is empirical, from a single observation).
- **Page ranges are expanded**: `134-43` -> `134-143`.
- **Initials get periods**: `Lars G` -> `Lars G.`.
- Whitespace before a colon is closed up: `Ill. : 1960` -> `Ill.: 1960`.

`convert` applies this automatically. If a library's existing items look
different, diff a few before bulk-loading and adjust rather than assuming.

## Verifying

Before creating, cross-check every converted record's DOI against the DOI in the
manuscript - a mis-resolved PMID otherwise imports a plausible wrong paper. After
creating, re-fetch the library and confirm each reference appears exactly once
and no DOI is duplicated.

**Validate the whole approach** by re-deriving a few references the library
*already* contains and diffing against them. This is what surfaced the
normalisation rules above; do it whenever working against an unfamiliar library.

## Things PubMed cannot supply

- Not everything is indexed (stats/methods journals, software, preprints).
  Fall back to Crossref (`https://api.crossref.org/works/<doi>`) and note the
  source in `Extra`.
- Software belongs in a `computerProgram` item (creatorType `programmer`), not
  `journalArticle`.
- **Flag PubMed/publisher disagreements to the user** rather than silently
  choosing. Real examples: PubMed lists a consortium paper under only its
  collective name while the journal names all authors; PubMed has
  `Davey Smith, George` where bmj.com has `Smith, George Davey`.

## What the Web API cannot do

It accepts **Zotero JSON only** - not BibTeX, RIS, or `.nbib`. Those import only
through the desktop client (File > Import), which targets whatever library is
selected in the UI and cannot be aimed at a group programmatically, and skips no
duplicates. Convert in the script instead. Saving the `.nbib` alongside is still
worthwhile as a provenance record.

Items created via the API appear in the desktop app only after a **sync**.
