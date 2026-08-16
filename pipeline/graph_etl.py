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


def _load_private_rulings():
    """Plug-in point — §9 step 1. Returns [] until the enrichment output lands.

    TODO: read ~/.hermes/private_rulings/data/json_llm/*.json (~57.6k files,
    shape {authorisation_number, relevant_legislation, case_references, ...}).
    Each becomes a node `private_ruling:EV/{authorisation_number}` with
    `applies` edges to relevant_legislation sections, `cites` to case_references
    and `consistent_with` to inline public-ruling refs (method=llm).
    """
    return []


def load_private_rulings(g):
    rulings = _load_private_rulings()
    for r in rulings:  # shape per the TODO above
        authnum = r["authorisation_number"]
        pk = g.node(f"private_ruling:EV/{authnum}", "private_ruling", f"EV/{authnum}",
                    {"authnum": authnum})
        for ref in r.get("relevant_legislation", []):
            g.edge(pk, g.section(ref["act"], ref["section"]), "applies", authnum, "llm")
        for citation in r.get("case_references", []):
            g.edge(pk, g.case(citation), "cites", authnum, "llm")
    print(f"  private rulings: {len(rulings)} (plug-in point — see _load_private_rulings)")


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
