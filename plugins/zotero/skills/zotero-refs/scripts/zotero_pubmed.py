#!/usr/bin/env python3
"""Resolve references to PubMed records and add them to a Zotero library.

Subcommands:
  resolve  --in <file-of-dois-or-pmids>  --out ids.json
  fetch    --ids ids.json --out-xml pm.xml [--out-nbib pm.nbib]
  convert  --xml pm.xml --out items.json
  dedupe   --items items.json --library groups/123 --out todo.json
  create   --items todo.json --library groups/123
  audit    --ids ids.json --library groups/123
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

if sys.version_info < (3, 7):
    sys.exit(f"Needs Python 3.7+, found {sys.version_info[0]}.{sys.version_info[1]}. "
             "Standard library only - no packages to install.")

sys.path.insert(0, str(Path(__file__).parent))
from zot_normalise import normalise

API = "https://api.zotero.org"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


CRED_DIR = Path.home() / ".config/zotero"
SETTINGS = "https://www.zotero.org/settings/keys"


def read_cred(name, what, hint):
    """Read a credential file, failing with actionable instructions - never prompt."""
    f = CRED_DIR / name
    if not f.exists():
        sys.exit(f"Missing {f}\n  {what}\n  Get it from {SETTINGS}{hint}\n"
                 f"  Then:  mkdir -p {CRED_DIR} && printf '<value>' > {f} && chmod 600 {f}")
    v = f.read_text().strip()
    if not v:
        sys.exit(f"{f} exists but is empty.")
    mode = oct(f.stat().st_mode)[-3:]
    if mode != "600":
        print(f"warning: {f} is mode {mode}; run  chmod 600 {f}", file=sys.stderr)
    return v


def key():
    return read_cred("api_key", "Your Zotero API key.", "")


def user_id():
    return read_cred("user_id", "Your numeric Zotero userID.",
                     " (shown as 'Your userID for use in API calls is ...')")


def preflight(lib=None):
    """Verify the key authenticates and can write to `lib` before doing any work.

    A key scoped only to the personal library fails *silently* on group writes,
    so check the specific group up front rather than after fetching everything.
    """
    st, body, _ = http(f"{API}/keys/current", headers={"Zotero-API-Key": key()})
    if st in (403, 404):
        sys.exit(f"Zotero rejected the API key ({st}). Create a new one at {SETTINGS}")
    if st != 200:
        sys.exit(f"Could not verify the API key ({st}): {body[:200]}")
    info = json.loads(body)
    acc = info.get("access", {})
    if lib and lib.startswith("groups/"):
        gid = lib.split("/", 1)[1]
        perm = acc.get("groups", {}).get(gid) or acc.get("groups", {}).get("all") or {}
        if not perm.get("library"):
            sys.exit(f"The API key has no access to group {gid}.\n"
                     f"  Edit the key at {SETTINGS} and grant it access to that group.")
        if not perm.get("write"):
            sys.exit(f"The API key can read group {gid} but not write to it.\n"
                     f"  Edit the key at {SETTINGS} and tick write access for that group.")
    elif lib and lib.startswith("users/"):
        if not acc.get("user", {}).get("write"):
            sys.exit(f"The API key lacks write access to your personal library.\n"
                     f"  Edit it at {SETTINGS}.")
    return info


def http(url, data=None, method=None, headers=None, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, method=method,
                                         headers=headers or {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt); continue
            return e.code, body, dict(e.headers)
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt); continue
            raise


def zget(lib, path, **params):
    url = f"{API}/{lib}/{path}?" + urllib.parse.urlencode(params)
    st, body, _ = http(url, headers={"Zotero-API-Key": key()})
    if st != 200:
        sys.exit(f"Zotero GET {st}: {body[:300]}")
    return json.loads(body)


# ---------- resolve ----------

def esearch(term):
    url = f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&term=" + urllib.parse.quote(term)
    st, body, _ = http(url)
    time.sleep(0.4)                      # NCBI: max 3 req/s without an API key
    if st != 200:
        return []
    return json.loads(body)["esearchresult"].get("idlist", [])


def resolve_ids(entries):
    """entries: list of dicts with optional 'doi', 'pmid', 'title'.

    NOTE: the NCBI ID Converter (idconv) only knows records that have a PMC
    entry, so it silently misses plenty of PubMed-indexed articles. It is used
    only as a fast first pass; esearch is the authority.
    """
    todo = [e for e in entries if not e.get("pmid") and e.get("doi")]
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        url = ("https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
               "?tool=zoteroimport&format=json&ids="
               + urllib.parse.quote(",".join(e["doi"] for e in chunk)))
        st, body, _ = http(url)
        if st == 200:
            m = {r.get("doi", "").lower(): r.get("pmid")
                 for r in json.loads(body).get("records", []) if r.get("pmid")}
            for e in chunk:
                if m.get(e["doi"].lower()):
                    e["pmid"] = str(m[e["doi"].lower()]); e["how"] = "idconv"
        time.sleep(0.5)

    for e in entries:                    # esearch fallback - the reliable path
        if e.get("pmid"):
            continue
        ids = []
        if e.get("doi"):
            ids = esearch(f'"{e["doi"]}"[AID]') or esearch(f'"{e["doi"]}"[DOI]')
        if not ids and e.get("title"):
            ids = esearch(f'"{e["title"][:120]}"[Title]')
        if len(ids) == 1:
            e["pmid"] = str(ids[0]); e["how"] = "esearch"
        elif ids:
            e["ambiguous"] = ids         # needs a human - never guess
    return entries


# ---------- convert ----------

def text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else None


def pm2zot(art):
    a = art.find(".//Article")
    z = {"itemType": "journalArticle", "creators": [], "tags": [],
         "collections": [], "relations": {}}
    t = text(a.find("ArticleTitle"))
    if t:
        z["title"] = t[:-1] if t.endswith(".") and not t.endswith("..") else t
    for au in a.findall(".//AuthorList/Author"):
        coll = text(au.find("CollectiveName"))
        if coll:                          # consortium: Zotero single-field name
            z["creators"].append({"creatorType": "author", "name": coll}); continue
        last, fore = text(au.find("LastName")), text(au.find("ForeName"))
        if last:
            z["creators"].append({"creatorType": "author",
                                  "firstName": fore or "", "lastName": last})
    j = a.find("Journal")
    z["publicationTitle"] = text(j.find("Title"))
    z["journalAbbreviation"] = text(j.find("ISOAbbreviation"))
    if j.find("ISSN") is not None:
        z["ISSN"] = text(j.find("ISSN"))
    ji = j.find("JournalIssue")
    if ji is not None:
        z["volume"] = text(ji.find("Volume")) or ""
        z["issue"] = text(ji.find("Issue")) or ""
        pd = ji.find("PubDate")
        if pd is not None:
            y, mo, d = (text(pd.find(x)) for x in ("Year", "Month", "Day"))
            if y:
                parts = [y]
                if mo:
                    mn = MONTHS.get(mo[:3]) or (int(mo) if mo.isdigit() else None)
                    if mn:
                        parts.append(f"{mn:02d}")
                        if d:
                            parts.append(f"{int(d):02d}")
                z["date"] = "-".join(parts)
            elif text(pd.find("MedlineDate")):
                z["date"] = text(pd.find("MedlineDate"))
    z["pages"] = text(a.find("Pagination/MedlinePgn")) or ""
    ab = a.find("Abstract")
    if ab is not None:
        segs = []
        for p in ab.findall("AbstractText"):
            lab, body = p.get("Label"), text(p)
            segs.append(f"{lab}: {body}" if lab else body)
        z["abstractNote"] = " ".join(s for s in segs if s)
    if text(a.find("Language")):
        z["language"] = text(a.find("Language"))

    # CRITICAL: scope to the article's own IdList. A `.//ArticleIdList` search
    # also matches every *cited reference* at the end of the record, and the
    # last one silently wins - which writes a wrong PMID onto every item.
    idl = art.find("PubmedData/ArticleIdList")
    ids = {i.get("IdType"): (i.text or "").strip()
           for i in idl.findall("ArticleId")} if idl is not None else {}
    if not ids.get("doi"):
        el = a.find("ELocationID[@EIdType='doi']")
        if el is not None and el.text:
            ids["doi"] = el.text.strip()
    if ids.get("doi"):
        z["DOI"] = ids["doi"]
    if ids.get("pubmed"):
        z["PMID"] = ids["pubmed"]
    if ids.get("pmc"):
        z["PMCID"] = ids["pmc"]
    z["libraryCatalog"] = "PubMed"
    return z


# ---------- library ops ----------

def fetch_library(lib):
    out, start = [], 0
    while True:
        page = zget(lib, "items/top", limit=100, start=start, format="json")
        out += page
        if len(page) < 100:
            return out
        start += 100


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("resolve"); p.add_argument("--in", dest="inp", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("fetch");   p.add_argument("--ids", required=True); p.add_argument("--out-xml", required=True); p.add_argument("--out-nbib")
    p = sub.add_parser("convert"); p.add_argument("--xml", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("dedupe");  p.add_argument("--items", required=True); p.add_argument("--library", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("create");  p.add_argument("--items", required=True); p.add_argument("--library", required=True)
    p = sub.add_parser("groups")
    p = sub.add_parser("check"); p.add_argument("--library")
    a = ap.parse_args()

    if a.cmd == "check":
        info = preflight(a.library)
        print(f"key OK - user {info.get('username')} (id {info.get('userID')})")
        print("access:", json.dumps(info.get("access", {})))
        print(f"write access to {a.library}: yes" if a.library else "(no --library given)")

    elif a.cmd == "groups":
        preflight()
        uid = user_id()
        for g in zget(f"users/{uid}", "groups", limit=100):
            print(g["id"], "|", g["data"]["name"])

    elif a.cmd == "resolve":
        entries = json.load(open(a.inp))
        json.dump(resolve_ids(entries), open(a.out, "w"), indent=1, ensure_ascii=False)
        ok = [e for e in entries if e.get("pmid")]
        print(f"resolved {len(ok)}/{len(entries)}")
        for e in entries:
            if not e.get("pmid"):
                print("  UNRESOLVED:", e.get("doi") or e.get("title", "")[:70],
                      "(ambiguous: %s)" % e["ambiguous"] if e.get("ambiguous") else "")

    elif a.cmd == "fetch":
        pmids = [str(e["pmid"]) for e in json.load(open(a.ids)) if e.get("pmid")]
        for rettype, out in (("xml", a.out_xml), ("nbib", a.out_nbib)):
            if not out:
                continue
            q = {"db": "pubmed", "id": ",".join(pmids)}
            q.update({"retmode": "xml"} if rettype == "xml"
                     else {"rettype": "medline", "retmode": "text"})
            st, body, _ = http(f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(q))
            Path(out).write_text(body)
            time.sleep(0.4)
        n = len(ET.parse(a.out_xml).getroot().findall(".//PubmedArticle"))
        print(f"requested {len(pmids)}, got {n} records")
        if n != len(pmids):
            print("  WARNING: count mismatch - inspect before creating")

    elif a.cmd == "convert":
        items = [normalise(pm2zot(x))
                 for x in ET.parse(a.xml).getroot().findall(".//PubmedArticle")]
        json.dump(items, open(a.out, "w"), indent=1, ensure_ascii=False)
        print("converted", len(items))
        for i in items:
            for f in ("title", "publicationTitle", "date", "PMID"):
                if not i.get(f):
                    print(f"  WARNING empty {f}:", i.get("title", "?")[:60])

    elif a.cmd == "dedupe":
        preflight(a.library)
        # Always re-read LIVE library state immediately before creating -
        # a stale snapshot will re-add anything written earlier in the session.
        live = fetch_library(a.library)
        hd = {(i["data"].get("DOI") or "").lower().strip() for i in live} - {""}
        hp = {(i["data"].get("PMID") or "").strip() for i in live} - {""}
        items = json.load(open(a.items))
        new = [i for i in items
               if (i.get("PMID") or "\0") not in hp
               and (i.get("DOI") or "\0").lower() not in hd]
        json.dump(new, open(a.out, "w"), indent=1, ensure_ascii=False)
        print(f"library has {len(live)}; {len(items) - len(new)} already present; {len(new)} to create")

    elif a.cmd == "create":
        preflight(a.library)
        items = json.load(open(a.items))
        tot = {"successful": 0, "failed": 0}
        for i in range(0, len(items), 50):          # API cap: 50 items per POST
            st, body, _ = http(f"{API}/{a.library}/items",
                               data=json.dumps(items[i:i + 50]).encode(),
                               method="POST",
                               headers={"Zotero-API-Key": key(),
                                        "Content-Type": "application/json"})
            if st != 200:
                sys.exit(f"POST {st}: {body[:300]}")
            r = json.loads(body)
            tot["successful"] += len(r.get("successful", {}))
            tot["failed"] += len(r.get("failed", {}))
            for k, v in r.get("failed", {}).items():
                print("  FAIL", k, v)
        print(tot)


if __name__ == "__main__":
    main()
