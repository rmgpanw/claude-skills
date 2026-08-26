#!/usr/bin/env python3
"""Post-processing that Zotero's own PubMed translator applies to raw PubMed data.

Derived by diffing script output against library items added via the Zotero
browser connector. Without these, API-added items look subtly different from
plugin-added ones in the same library (journal case, page ranges, initials).
"""
import re

# lowercase inside a title unless first/last word
SMALL = {"a","an","and","as","at","but","by","for","from","in","into","nor","of",
         "on","onto","or","over","per","the","to","v","v.","versus","vs","vs.","with"}


def capitalize_title(s):
    """Title-case a journal name, leaving acronyms and numbers alone."""
    if not s:
        return s
    s = re.sub(r"\s+:", ":", s)             # "Ill. : 1960" -> "Ill.: 1960"
    words = s.split(" ")
    # Empirical: Zotero leaves names led by an acronym alone ("JAMA ophthalmology",
    # "BMJ (Clinical research ed.)") but title-cases the rest ("Nature Genetics").
    if words and len(words[0]) > 1 and words[0].isupper() and words[0].isalpha():
        return s
    out = []
    for i, w in enumerate(words):
        core = w.strip("([{)]}")
        if not core:
            out.append(w); continue
        # leave acronyms (BMJ), mixed-case (PLoS) and anything with a digit
        if core.isupper() or any(ch.isdigit() for ch in core) or \
           (any(c.isupper() for c in core[1:]) and not core.istitle()):
            out.append(w); continue
        low = core.lower()
        if i not in (0, len(words) - 1) and low in SMALL:
            out.append(w.replace(core, low))
        else:
            out.append(w.replace(core, core[0].upper() + core[1:]))
    return " ".join(out)


def expand_pages(p):
    """PubMed abbreviates ranges: 134-43 -> 134-143, 512-25 -> 512-525."""
    if not p:
        return p
    m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", p.strip())
    if not m:
        return p
    a, b = m.groups()
    if len(b) < len(a):
        b = a[:len(a) - len(b)] + b
    return f"{a}-{b}"


def punctuate_initials(name):
    """PubMed strips periods: 'Lars G' -> 'Lars G.', 'Jessica N Cooke' -> 'Jessica N. Cooke'."""
    if not name:
        return name
    return " ".join(w + "." if len(w) == 1 and w.isalpha() and w.isupper() else w
                    for w in name.split(" "))


def normalise(item):
    if item.get("publicationTitle"):
        item["publicationTitle"] = capitalize_title(item["publicationTitle"])
    if item.get("pages"):
        item["pages"] = expand_pages(item["pages"])
    for c in item.get("creators", []):
        if "firstName" in c:
            c["firstName"] = punctuate_initials(c["firstName"])
    return item


if __name__ == "__main__":
    import json, sys
    items = json.load(open(sys.argv[1]))
    json.dump([normalise(i) for i in items], open(sys.argv[2], "w"),
              indent=1, ensure_ascii=False)
    print("normalised", len(items))
