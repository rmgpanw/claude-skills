"""Add Zotero entries to an existing .bib without rewriting it.

Pure functions only; zotero_pubmed.py does the fetching. A .bib is usually not
a plain export of a library: it may be a subset, and keys or fields may have
been edited since. So entries are appended, never replaced.
"""
import re

# Crossref labels share the citation syntax: @fig-x, @tbl-x, @sec-x.
CROSSREF = re.compile(r"^[a-z]+-")
CITE = re.compile(r"(?<![\w.])@([A-Za-z0-9_][\w:.#$%&+?<>~/-]*)")
SKIP_TYPES = {"comment", "string", "preamble"}

DROP_FIELDS = {"abstract", "issn", "language", "month", "urldate", "keywords",
               "file", "note", "shorttitle"}


def norm_title(t):
    return re.sub(r"[\W_]", "", (t or "").lower())[:60]


def split_entries(text):
    return re.findall(r"^@\w+\s*\{.*?(?=^@\w+\s*\{|\Z)", text, re.S | re.M)


def parse_fields(raw):
    """Return (type, key, [(name, value), ...]); value keeps its delimiters."""
    head = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", raw)
    if not head:
        return None
    i, fields = head.end(), []
    while True:
        m = re.compile(r"\s*(\w+)\s*=\s*").match(raw, i)
        if not m:
            break
        i = m.end()
        if raw[i] == "{":                   # balanced: values nest braces
            depth, j = 0, i
            while j < len(raw):
                depth += (raw[j] == "{") - (raw[j] == "}")
                j += 1
                if depth == 0:
                    break
        else:
            j = i
            while j < len(raw) and raw[j] not in ",\n}":
                j += 1
        fields.append((m.group(1).lower(), raw[i:j].strip()))
        i = j
        c = re.compile(r"\s*,").match(raw, i)
        if not c:
            break
        i = c.end()
    return head.group(1).lower(), head.group(2), fields


def parse_bib(text):
    out = []
    for raw in split_entries(text):
        p = parse_fields(raw)
        if not p or p[0] in SKIP_TYPES:
            continue
        f = dict(p[2])
        out.append({"key": p[1], "type": p[0], "fields": p[2],
                    "doi": f.get("doi", "").strip("{}").lower(),
                    "title": norm_title(f.get("title"))})
    return out


def split_names(value):
    """Split on ' and ' outside braces, so {Smith and Wesson} stays whole."""
    names, depth, cur, i = [], 0, "", 0
    while i < len(value):
        if value[i] in "{}":
            depth += 1 if value[i] == "{" else -1
        if depth == 0 and value.startswith(" and ", i):
            names.append(cur); cur = ""; i += 5; continue
        cur += value[i]; i += 1
    return names + [cur]


def format_name(name, initials=False):
    if "," not in name or name.startswith("{"):
        return name                         # consortium, or already protected
    fam, giv = [x.strip() for x in name.split(",", 1)]
    if " " in fam and fam[0].islower():     # `van Norren`: keep the particle
        fam = "{" + fam + "}"               # on the family name in citeproc
    if initials:
        giv = "".join(p[0].upper() for p in re.split(r"[\s.\-]+", giv) if p)
    return f"{fam}, {giv}"


def format_entry(e, short=None, initials=False, keep=()):
    names = [n for n, _ in e["fields"]]
    lines = []
    for n, v in e["fields"]:
        if n in DROP_FIELDS and n not in keep:
            continue
        if n == "url" and "doi" in names and n not in keep:
            continue
        if n == "author":
            inner = " and ".join(format_name(x, initials)
                                 for x in split_names(v[1:-1]))
            v = "{" + inner + "}"
        lines.append(f"\t{n} = {v},")
    if short and "journal" in names and "shortjournal" not in names:
        lines.append("\tshortjournal = {" + short + "},")
    return "@%s{%s,\n%s\n}\n" % (e["type"], e["key"], "\n".join(lines))


def cited_keys(text):
    return {k.rstrip(".:,;") for k in CITE.findall(text)}


def uses_bare_initials(entries, threshold=0.5):
    """True if the file stores given names as `NM`, not `Neil M.`."""
    giv = []
    for e in entries:
        a = dict(e["fields"]).get("author", "")
        for n in split_names(a[1:-1]):
            if "," in n and not n.startswith("{"):
                giv.append(n.split(",", 1)[1].strip())
    return bool(giv) and sum(bool(re.fullmatch(r"[A-Z]{1,5}", g))
                             for g in giv) / len(giv) >= threshold


def plan(bib, zot, cited):
    """Compare a .bib with a library. Nothing here touches the file."""
    in_bib = {e["key"] for e in bib}
    counts = {}
    for z in zot:
        counts[z["key"]] = counts.get(z["key"], 0) + 1
    by_key = {z["key"]: z for z in zot}
    by_doi = {z["doi"]: z for z in zot if z["doi"]}
    by_title = {z["title"]: z for z in zot if z["title"]}
    bib_doi = {e["doi"]: e["key"] for e in bib if e["doi"]}

    def match(e):
        return by_doi.get(e["doi"]) or by_title.get(e["title"])

    r = {"add": [], "blocked": [], "unknown": [], "renamed": [], "not_in_library": []}
    for k in sorted(cited - in_bib):
        z = by_key.get(k)
        if z is None:
            if not CROSSREF.match(k):
                r["unknown"].append(k)
        elif counts[k] > 1:
            r["blocked"].append((k, "key is on several library items"))
        elif z["doi"] and z["doi"] in bib_doi:
            r["blocked"].append((k, f"same DOI already in .bib as {bib_doi[z['doi']]}"))
        else:
            r["add"].append(z)
    for e in bib:
        z = match(e)
        if z is None:
            r["not_in_library"].append(e["key"])
        elif z["key"] != e["key"]:
            r["renamed"].append((e["key"], z["key"]))
    return r
