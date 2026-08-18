#!/usr/bin/env python3
"""Graph ingestion ETL — docs/specs/graph.md v0.2 §9.

Builds data/graph.db (SQLite) from the data/ corpus that exists today.
stdlib only, no network, no LLM.

    python3 pipeline/graph_etl.py [--rebuild]

--rebuild drops and recreates the tables; otherwise INSERT OR IGNORE upserts
into the existing db and reports how many rows were actually added.
"""

import argparse
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA, "graph.db")

ACTS = [
    "itaa-1997", "itaa-1936", "gst-1999", "fbt-1986", "taa-1953",
    "corporations-act-2001", "aml-ctf-2006", "aml-ctf-rules-2007", "sis-1993",
    "sga-1992",  # cited by rulings; no tree yet — label-only section nodes
]
GUIDES = ["master-tax-guide", "master-gst-guide", "master-tax-examples"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id          INTEGER PRIMARY KEY,
  node_type   TEXT NOT NULL,
  key         TEXT NOT NULL UNIQUE,
  label       TEXT NOT NULL,
  meta        TEXT,
  content_ref TEXT,
  created_at  TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS graph_edges (
  id         INTEGER PRIMARY KEY,
  source_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  target_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  edge_type  TEXT NOT NULL,
  weight     REAL DEFAULT 1.0,
  source_doc TEXT,
  method     TEXT,
  UNIQUE (source_id, target_id, edge_type, source_doc)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges (source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges (target_id, edge_type);
"""


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        print(f"  ! missing {name} — skipped")
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- key helpers

def section_key(act, section):
    return f"section:{act}:{section}"


def ruling_label(rid):
    """ATOID_2001_120 -> 'ATOID 2001/120'; PSLA_2005_24 -> 'PS LA 2005/24'."""
    parts = rid.split("_")
    if len(parts) >= 3:
        series = "PS LA" if parts[0] == "PSLA" else parts[0]
        return f"{series} {parts[1]}/{'-'.join(parts[2:])}"
    return rid.replace("_", " ")


# Public-ruling citation forms found inline in private ruling text
# (spec §3 `consistent_with`): TR/TD/PCG/LCG/PS LA/CR/IT/GSTR/ATOID/PR/SGR/TA/MT
# + year/number. IT is the odd one out (no year — "IT 2621").
_PUBLIC_RULING_RE = re.compile(
    r"\b((?:PS LA)|TR|TD|PCG|LCG|CR|GSTR|ATOID|PR|SGR|TA|MT)\s+(\d{4})/(\d+)\b"
    r"|\bIT\s+(\d{3,4})\b"
)


def extract_public_ruling_refs(text: str) -> list[str]:
    """Normalise inline public-ruling citations to node labels.

    'TR 2025/1', 'td 2024/2' -> 'TR 2025/1', 'TD 2024/2'
    'PS LA 2005/24'         -> 'PS LA 2005/24'
    'IT 2621'               -> 'IT 2621'
    """
    if not text:
        return []
    out: list[str] = []
    for m in _PUBLIC_RULING_RE.finditer(text):
        if m.group(1):
            out.append(f"{m.group(1).upper()} {m.group(2)}/{m.group(3)}")
        else:
            out.append(f"IT {m.group(4)}")
    return out


class Graph:
    """Accumulates nodes/edges by canonical key, then bulk-loads."""

    def __init__(self):
        self.nodes = {}   # key -> (node_type, label, meta_json, content_ref)
        self.edges = set()  # (src_key, tgt_key, edge_type, source_doc, method)

    def node(self, key, node_type, label, meta=None, content_ref=None):
        # first writer wins: tree.json (rich label) is loaded before references
        self.nodes.setdefault(
            key, (node_type, label, json.dumps(meta) if meta else None, content_ref))
        return key

    def section(self, act, section):
        key = section_key(act, section)
        self.node(key, "section", f"s {section} {act}", {"act": act, "section": section})
        return key

    def ruling(self, rid):
        key = f"public_ruling:{ruling_label(rid)}"
        self.node(key, "public_ruling", ruling_label(rid), {"id": rid})
        return key

    def case(self, citation):
        key = f"case:{citation}"
        m = re.match(r"\[(\d{4})\]\s*([A-Z]+)", citation)
        meta = {"year": int(m.group(1)), "court": m.group(2)} if m else None
        self.node(key, "case", citation, meta)
        return key

    def edge(self, src, tgt, edge_type, source_doc, method="regex"):
        if src and tgt:
            self.edges.add((src, tgt, edge_type, source_doc, method))


# ------------------------------------------------------------------- sources

def load_acts(g):
    """§9 base node set: every section leaf of every act tree."""
    n = 0
    for act in ACTS:
        tree = load(f"{act}/tree.json")
        if not tree:
            continue
        stack = [tree]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "path" in item and "id" in item:  # section leaf
                    key = section_key(act, item["id"])
                    g.nodes[key] = (
                        "section",
                        f"s {item['id']} {act} — {item.get('title', '')}".strip(" —"),
                        json.dumps({"act": act, "section": item["id"],
                                    "title": item.get("title")}),
                        f"data/{act}/sections/{item['path']}",
                    )
                    n += 1
                else:
                    stack.extend(v for v in item.values() if isinstance(v, (list, dict)))
    print(f"  act trees: {n} section nodes")


def load_public_rulings(g):
    """ruling_section_index.json: ruling -> act/section pairs."""
    idx = load("ruling_section_index.json") or {}
    for rid, refs in idx.items():
        rk = g.ruling(rid)
        for ref in refs:
            sk = g.section(ref["act"], ref["section"])
            g.edge(rk, sk, "applies", rid)
            g.edge(sk, rk, "interpreted_by", rid)
    print(f"  ruling_section_index: {len(idx)} rulings")


def load_cases(g):
    """case_section_refs.json + section_case_index.json -> section considered_in case."""
    refs = load("case_section_refs.json") or {}
    for citation, secs in refs.items():
        ck = g.case(citation)
        for ref in secs:
            g.edge(g.section(ref["act"], ref["section"]), ck, "considered_in", citation)

    idx = load("section_case_index.json") or {}
    for sec_id, cases in idx.items():
        act, _, section = sec_id.partition(":")
        if not section:
            continue
        sk = g.section(act, section)
        for c in cases:
            g.edge(sk, g.case(c["citation"]), "considered_in", sec_id)
    print(f"  cases: {len(refs)} case_section_refs, {len(idx)} section_case_index keys")


def load_citation_index(g):
    """citation_index.json: {act: {section: [{type: ruling|case, citation}]}}."""
    idx = load("citation_index.json") or {}
    n = 0
    for act, sections in idx.items():
        for section, items in sections.items():
            sk = g.section(act, section)
            for item in items:
                n += 1
                if item["type"] == "ruling":
                    rk = g.ruling(item["citation"])
                    g.edge(rk, sk, "applies", "citation_index")
                    g.edge(sk, rk, "interpreted_by", "citation_index")
                else:
                    g.edge(sk, g.case(item["citation"]), "considered_in", "citation_index")
    print(f"  citation_index: {n} references")


def load_definitions(g):
    """definitions_all.json: {act: {section, terms: {term: {anchor, section}}}}."""
    idx = load("definitions_all.json") or {}
    n = 0
    for act, block in idx.items():
        for term, info in (block.get("terms") or {}).items():
            section = info.get("section") or block.get("section")
            if not section:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", term.lower()).strip("-")
            dk = g.node(f"definition:{act}:{slug}", "definition", term,
                        {"act": act, "term": term, "anchor": info.get("anchor")})
            g.edge(dk, g.section(act, section), "defines", f"definitions_all:{act}")
            n += 1
    print(f"  definitions_all: {n} definitions")


# commentary body refs: "ITAA97 s 8-1", "ITAA 1936 s 25", "GST Act s 9-5", "s 118-110"
ACT_ALIASES = {
    "itaa97": "itaa-1997", "itaa 1997": "itaa-1997", "ita 1997": "itaa-1997",
    "itaa36": "itaa-1936", "itaa 1936": "itaa-1936", "ita 1936": "itaa-1936",
    "gst act": "gst-1999", "gstact": "gst-1999",
    "fbtaa": "fbt-1986", "fbt act": "fbt-1986",
    "taa": "taa-1953", "taa 1953": "taa-1953",
}
REF_RE = re.compile(
    r"\b(ITAA\s?97|ITAA\s?1997|ITA\s?1997|ITAA\s?36|ITAA\s?1936|ITA\s?1936|"
    r"GST\s?Act|FBTAA|FBT\s?Act|TAA\s?1953|TAA)\s+"
    r"(?:ss?|sec(?:tion)?s?)\.?\s*([0-9]+[A-Z]*(?:-[0-9]+[A-Z]*)?)",
    re.I,
)


def load_commentary(g, known_sections):
    """Commentary nodes per guide chapter-section + explained_in edges.

    ponytail: act-qualified regex over the markdown body only, and the edge is
    dropped unless the section already exists as a node — self-validating, no
    fuzzy matching, no LLM. Bare "s 8-1" refs (act implied by context) are
    deliberately skipped: too ambiguous without an act token.
    """
    nodes = edges = 0
    for guide in GUIDES:
        tree = load(f"{guide}/tree.json")
        if not tree:
            continue
        for part in tree.get("parts", []):
            for sec in part.get("sections", []):
                key = f"commentary:{guide}:{part['id']}/{sec['id']}"
                path = os.path.join(DATA, guide, "sections", sec["path"])
                g.node(key, "commentary", f"{guide} {part['id']}: {sec.get('title', '')}",
                       {"guide": guide, "chapter": part["id"], "title": sec.get("title")},
                       os.path.relpath(path, ROOT))
                nodes += 1
                try:
                    with open(path, encoding="utf-8") as fh:
                        body = fh.read()
                except OSError:
                    continue
                for alias, section in set(REF_RE.findall(body)):
                    act = ACT_ALIASES.get(re.sub(r"\s+", " ", alias.lower()).strip())
                    sk = section_key(act, section) if act else None
                    if sk in known_sections:
                        g.edge(sk, key, "explained_in", key)
                        edges += 1

    # Regulatory guides: rg_section_index.json is the ready-made mapping.
    rg = load("rg_section_index.json") or {}
    raw_manifest = load("regulatory-guides/rg_manifest.json")
    manifest = {m.get("id") or m.get("rg_id"): m for m in raw_manifest} \
        if isinstance(raw_manifest, list) else (raw_manifest or {})
    for rg_id, refs in rg.items():
        key = f"commentary:regulatory-guides:{rg_id}"
        g.node(key, "commentary", (manifest.get(rg_id) or {}).get("title", rg_id),
               {"guide": "regulatory-guides", "chapter": rg_id})
        nodes += 1
        for ref in refs:
            g.edge(g.section(ref["act"], ref["section"]), key, "explained_in", rg_id)
            edges += 1
    print(f"  commentary: {nodes} nodes, {edges} explained_in edges")


# ------------------------------------------------------- private rulings (mop-up)

# Act alias -> canonical act dir, longest-first so full names win over abbreviations.
_ACT_ALIASES = [
    ("anti-money laundering and counter-terrorism financing rules 2007", "aml-ctf-rules-2007"),
    ("anti-money laundering and counter-terrorism financing act 2006", "aml-ctf-2006"),
    ("superannuation industry (supervision) act 1993", "sis-1993"),
    ("superannuation guarantee (administration) act 1992", "sga-1992"),
    ("income tax assessment act 1997", "itaa-1997"),
    ("income tax assessment act 1936", "itaa-1936"),
    ("a new tax system (goods and services tax) act 1999", "gst-1999"),
    ("a new tax system (gods and services tax) act 1999", "gst-1999"),  # LLM typo
    ("goods and services tax act 1999", "gst-1999"),
    ("fringe benefits tax assessment act 1986", "fbt-1986"),
    ("fringe benefits tax act 1986", "fbt-1986"),
    ("taxation administration act 1953", "taa-1953"),
    ("corporations act 2001", "corporations-act-2001"),
    ("itaa 1997", "itaa-1997"), ("itaa97", "itaa-1997"), ("itaa 1936", "itaa-1936"),
    ("itaa36", "itaa-1936"), ("gst act 1999", "gst-1999"), ("taa 1953", "taa-1953"),
    ("fbt act 1986", "fbt-1986"), ("fbt act", "fbt-1986"), ("corporations act", "corporations-act-2001"),
    ("sis act 1993", "sis-1993"), ("gst act", "gst-1999"),
]
_ACT_ALIASES.sort(key=lambda a: len(a[0]), reverse=True)

_SECTION_RE = re.compile(r"(?:sub)?sec(?:tion)?\s+([0-9]+(?:-[0-9]+)?[A-Za-z]?)(?:\([^)]*\))?", re.IGNORECASE)
_RANGE_RE = re.compile(r"sections\s+([0-9]+(?:-[0-9]+)?[A-Za-z]?)\s+to\s+([0-9]+(?:-[0-9]+)?[A-Za-z]?)", re.IGNORECASE)
_SCHED_SECTION_RE = re.compile(r"schedule\s+\d+\s+(?:sub)?section\s+([0-9]+(?:-[0-9]+)?[A-Za-z]?)", re.IGNORECASE)
_NON_SECTION_RE = re.compile(r"^\s*(?:division|subdivision|part|schedule|chapter)\b", re.IGNORECASE)
_NEUTRAL_CASE_RE = re.compile(r"\[\d{4}\]\s*[A-Z]+\s+\d+")
_REPORTER_CASE_RE = re.compile(r"\(\d{4}\)\s+\d+\s+[A-Z]+(?:\s+[A-Z]+)?\s+\d+")


def _parse_leg_ref(ref: str):
    """Parse a canonical legislation ref -> (act_dir, section_id) or None.

    Handles 'Income Tax Assessment Act 1997 section 118-145',
    'ITAA 1997 subsection 115-25(1)', 'GST Act 1999 sections 135-55 to 135-75',
    'Taxation Administration Act 1953 schedule 1 section 12-140'.
    Non-section refs (Division/Part/Subdivision) return None — the graph schema
    has no division nodes; they are counted and skipped.
    """
    s = ref.strip()
    act_dir = None
    rest = ""
    for alias, adir in _ACT_ALIASES:
        if s.lower().startswith(alias):
            act_dir = adir
            rest = s[len(alias):]
            break
    if act_dir is None:
        return None
    m = _RANGE_RE.search(rest)
    if m:
        return [(act_dir, m.group(1)), (act_dir, m.group(2))]
    m = _SCHED_SECTION_RE.search(rest)
    if m:
        return [(act_dir, m.group(1))]
    m = _SECTION_RE.search(rest)
    if m:
        return [(act_dir, m.group(1))]
    if _NON_SECTION_RE.match(rest):
        return "non-section"  # Division/Part etc — counted, not edges
    return None


def _case_key(citation: str) -> str | None:
    """Normalise a case citation to a stable node key.

    Prefers the neutral citation ('[YYYY] COURT N' — matches the existing case
    corpus), falls back to reporter citation ('(YYYY) VOL REP N'), else the raw
    string. Un-cited fragments ('Steele v. FC of T', garbage) are dropped.
    """
    c = citation.strip().rstrip(".")
    m = _NEUTRAL_CASE_RE.search(c)
    if m:
        return m.group(0)
    m = _REPORTER_CASE_RE.search(c)
    if m:
        return m.group(0)
    return None


def _load_private_rulings():
    """Yield parsed private rulings from the LLM mop-up output (~57.6k files).

    Each yield: {authnum, applies: [(act, section, method)], cites: [(key, method)]}.
    Streams file-by-file — never holds the whole corpus in memory.
    """
    import glob as _glob
    rulings_dir = os.environ.get(
        "HERMES_RULINGS_DIR", os.path.expanduser("~/.hermes/private_rulings"))
    llm_dir = os.path.join(rulings_dir, "data", "json_llm")
    files = sorted(_glob.glob(os.path.join(llm_dir, "*.json")))
    stats = {"files": 0, "ok": 0, "err": 0, "leg": 0, "leg_skip_div": 0,
             "leg_unparsed": 0, "case": 0, "case_dropped": 0}
    for path in files:
        stats["files"] += 1
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            stats["err"] += 1
            continue
        is_ok = d.get("mop_status") == "ok"
        if is_ok:
            stats["ok"] += 1
        else:
            stats["err"] += 1
        authnum = str(d.get("authorisation_number", ""))
        if not authnum:
            continue
        applies = []
        cites = []
        consistent_with: list[str] = []
        if is_ok:
            for ref in d.get("legislation_refs_llm", []) or []:
                r = _parse_leg_ref(ref)
                if r == "non-section":
                    stats["leg_skip_div"] += 1
                elif r:
                    for act, sec in r:
                        applies.append((act, sec, "llm"))
                        stats["leg"] += 1
                else:
                    stats["leg_unparsed"] += 1
            for cit in d.get("case_refs_llm", []) or []:
                k = _case_key(cit)
                if k:
                    cites.append((k, "llm"))
                    stats["case"] += 1
                else:
                    stats["case_dropped"] += 1
            # inline public-ruling citations → consistent_with (spec §3):
            # private ruling text references a public ruling it aligns with.
            for field in ("formatted_text", "reasons_for_decision", "facts"):
                for label in extract_public_ruling_refs(str(d.get(field) or "")):
                    if label not in consistent_with:
                        consistent_with.append(label)
        # regex refs are deterministic — use them even when the LLM pass failed
        for ref in d.get("relevant_legislation", []) or []:
            r = _parse_leg_ref(ref)
            if r == "non-section":
                stats["leg_skip_div"] += 1
            elif r:
                for act, sec in r:
                    applies.append((act, sec, "regex"))
                    stats["leg"] += 1
            else:
                stats["leg_unparsed"] += 1
        for cit in d.get("case_references", []) or []:
            k = _case_key(cit)
            if k:
                cites.append((k, "regex"))
                stats["case"] += 1
            else:
                stats["case_dropped"] += 1
        yield {"authnum": authnum, "applies": applies, "cites": cites,
               "consistent_with": consistent_with}
    print(f"  private rulings: {stats['ok']}/{stats['files']} ok, {stats['err']} err "
          f"| leg edges {stats['leg']} (skip div {stats['leg_skip_div']}, unparsed {stats['leg_unparsed']}) "
          f"| case edges {stats['case']} (dropped {stats['case_dropped']})")


def load_private_rulings(g):
    n = 0
    cw_edges = 0
    for r in _load_private_rulings():
        authnum = r["authnum"]
        pk = g.node(f"private_ruling:EV/{authnum}", "private_ruling", f"EV/{authnum}",
                    {"authnum": authnum})
        for act, sec, method in r["applies"]:
            g.edge(pk, g.section(act, sec), "applies", authnum, method)
        for ck, method in r["cites"]:
            g.edge(pk, g.case(ck), "cites", authnum, method)
        # consistent_with targets must already exist as public ruling nodes
        # (g.ruling() would create phantoms for out-of-corpus citations)
        for label in r["consistent_with"]:
            rk = f"public_ruling:{label}"
            if rk in g.nodes:
                g.edge(pk, rk, "consistent_with", authnum, "regex")
                cw_edges += 1
        n += 1
    print(f"  private ruling nodes: {n}, consistent_with edges: {cw_edges}")


# ---------------------------------------------------------------------- load

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true", help="drop and recreate tables")
    ap.add_argument("--selftest", action="store_true", help="check the key/ref parsers")
    args = ap.parse_args()

    if args.selftest:
        assert ruling_label("ATOID_2001_120") == "ATOID 2001/120"
        assert ruling_label("PSLA_2005_24") == "PS LA 2005/24"
        assert ruling_label("TR 2025/1") == "TR 2025/1"
        assert REF_RE.findall("under ITAA97 s 8-1 and ITAA 1936 sec 25") == \
            [("ITAA97", "8-1"), ("ITAA 1936", "25")]
        assert not REF_RE.findall("deductible under s 8-1")  # bare ref: skipped
        print("selftest ok")
        return 0

    print("Extracting…")
    g = Graph()
    load_acts(g)
    known_sections = set(g.nodes)  # only tree-backed sections anchor explained_in
    load_public_rulings(g)
    load_cases(g)
    load_citation_index(g)
    load_definitions(g)
    load_commentary(g, known_sections)
    load_private_rulings(g)

    fresh = args.rebuild or not os.path.exists(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    if args.rebuild:
        db.executescript("DROP TABLE IF EXISTS graph_edges; DROP TABLE IF EXISTS nodes;")
    db.executescript(SCHEMA)

    print(f"Loading into {os.path.relpath(DB_PATH, ROOT)} ({'rebuild' if fresh else 'upsert'})…")
    before_n = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    db.executemany(
        "INSERT OR IGNORE INTO nodes (key, node_type, label, meta, content_ref)"
        " VALUES (?, ?, ?, ?, ?)",
        [(k, *v) for k, v in g.nodes.items()])
    ids = dict(db.execute("SELECT key, id FROM nodes"))
    before_e = db.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    db.executemany(
        "INSERT OR IGNORE INTO graph_edges (source_id, target_id, edge_type, source_doc, method)"
        " VALUES (?, ?, ?, ?, ?)",
        [(ids[s], ids[t], et, doc, m) for s, t, et, doc, m in g.edges])
    db.commit()

    # §9 step 7 — validate every edge endpoint resolves
    orphans = db.execute(
        "SELECT COUNT(*) FROM graph_edges e"
        " LEFT JOIN nodes s ON e.source_id = s.id LEFT JOIN nodes t ON e.target_id = t.id"
        " WHERE s.id IS NULL OR t.id IS NULL").fetchone()[0]

    total_n = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    total_e = db.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]
    print("\nnodes:")
    for t, c in db.execute("SELECT node_type, COUNT(*) FROM nodes GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {t:<15} {c:>7}")
    print("edges:")
    for t, c in db.execute("SELECT edge_type, COUNT(*) FROM graph_edges GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {t:<15} {c:>7}")
    print(f"total: {total_n} nodes (+{total_n - before_n}), "
          f"{total_e} edges (+{total_e - before_e}), orphans: {orphans}")
    db.close()
    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
