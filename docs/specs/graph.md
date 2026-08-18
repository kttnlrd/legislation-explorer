# Graph Specification — v0.2
# Knowledge graph for Australian tax: sections, cases, public rulings,
# private rulings, commentary. Typed edges + embedding soft edges.
# Companion spec: docs/specs/procedural-knowledge.md
#
# v0.2 — reviewed by Claude Code (opus) audit, 2026-08-16. Fixed:
#   - edge vocabulary consistency (applies/applied_in, explained_in, defines)
#   - removed false "applies == interpreted_by reversed" claim
#   - embedding model/cost reconciled with shipped code (3-small, measured costs)
#   - storage decision: SQLite for v1, Postgres/pgvector as documented upgrade
#   - ingestion re-pointed at ruling_section_index.json (citation_index.json empty)
#   - SQL fixes: FK truncate order, cycle guard, provenance in UNIQUE, key prefix
#   - scale figures corrected (~100k nodes, public rulings 11,932)
#   - Leiden/community detection deferred to v2 (degree ranking serves v1)

## 1. Purpose

Give an LLM structured pathways through the tax corpus. The graph is the
*knowledge* layer: what cites what, what interprets what, what applies
what. The LLM reads token-lean graph context and traverses typed edges
instead of receiving flat chunk lists.

## 2. Node types

| type          | canonical key                | example                          | source                          |
|---------------|------------------------------|----------------------------------|---------------------------------|
| section       | section:{act}:{section}      | section:itaa-1997:118-110        | legislation-explorer acts data  |
| case          | case:[year] court no         | case:[2015] HCA 48               | case_texts, hca/fca/aata json   |
| public_ruling | public_ruling:{series} {year}/{no} | public_ruling:TR 2025/1     | ruling manifest + txt corpus    |
| private_ruling| private_ruling:EV/{authnum}  | private_ruling:EV/1052514149928  | private-rulings scrape (~57.6k) |
| commentary    | commentary:{guide}:{chapter} | commentary:master-tax-guide:ch12 | master guides, regulatory guides|
| definition    | definition:{act}:{term}      | definition:itaa-1997:net-capital-gain | definitions_all.json      |

Node type is part of the canonical key (matches graph.py) so sections and
definitions — which share an `{act}:{x}` shape — cannot collide. All
aliases resolve to canonical keys at ingestion time (entity resolution,
§7).

Private ruling count drifts with each scrape; treat as "~57.6k" (57,608 at
last scrape), not a fixed figure.

## 3. Edge types

Explicit edges (ground truth, extracted, never hallucinated):

| edge_type        | direction         | semantics                              | source                      |
|------------------|-------------------|----------------------------------------|-----------------------------|
| interpreted_by   | section -> ruling | ruling interprets (construes) the section | citation_index, private  |
| applies          | ruling -> section | ruling invokes/applies the section     | private scrape leg refs     |
| considered_in    | section/case -> case | case considers the section/issue    | case_section_refs           |
| cites            | doc -> doc        | document cites another document        | case refs, ruling refs      |
| follows          | case -> case      | later case follows earlier             | case texts (LLM pass, v2)   |
| distinguishes    | case -> case      | later case distinguishes earlier       | case texts (LLM pass, v2)   |
| consistent_with  | ruling -> ruling  | ruling consistent with public ruling   | private scrape inline refs  |
| explained_in     | section -> commentary | commentary explains the section    | smartlink_index + section refs |
| defines          | definition -> section | definition defines a term used in the section | definitions_all.json |
| related_to       | any -> any        | embedding soft edge (similarity)       | similarity_index, §5 (v1: not materialised) |

`interpreted_by` and `applies` are DISTINCT legal relations — "this ruling
construes s 8-1" ≠ "this ruling merely invokes s 8-1" — and come from
different extraction sources. They must not be merged or treated as
reverses. The serializer may emit either traversal direction (walking an
edge backwards) without renaming the edge type.

Every explicit edge stores `source_doc` (which document the extraction
came from) and `method` (regex | llm | manual) so edges can be re-derived
and audited when the corpus updates.

## 4. Storage

SQLite for v1. The project has no Postgres today (the "issues" table is
SQLite; the only psycopg2 use targets the sibling Cadena MCP database) and
~100k nodes / ~250k explicit edges fits SQLite trivially. The existing
`embeddings.db` pattern already holds 1M+ similarity rows. Postgres +
pgvector is the documented upgrade path if scale (~10x) or multi-user
concurrency demands it — revisit then, not now.

```
nodes (
  id            INTEGER PRIMARY KEY,
  node_type     TEXT NOT NULL,          -- section|case|public_ruling|...
  key           TEXT NOT NULL UNIQUE,   -- canonical key, type-prefixed
  label         TEXT NOT NULL,          -- display label
  meta          TEXT,                   -- JSON: year, court, act, etc
  content_ref   TEXT,                   -- path/pointer to full text
  created_at    TEXT DEFAULT (datetime('now'))
)

graph_edges (
  id            INTEGER PRIMARY KEY,
  source_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  target_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  edge_type     TEXT NOT NULL,
  weight        REAL DEFAULT 1.0,       -- cosine for related_to, else 1.0
  source_doc    TEXT,                   -- provenance (part of uniqueness)
  method        TEXT,                   -- regex|llm|manual
  UNIQUE (source_id, target_id, edge_type, source_doc)
)

CREATE INDEX IF NOT EXISTS idx_edges_source ON graph_edges (source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges (target_id, edge_type);
```

Notes:
- `source_doc` is in the UNIQUE key so the same relation derived from two
  provenances (regex in doc X, llm in doc Y) is kept, not silently
  discarded. Rebuild uses `INSERT OR IGNORE`.
- No index on `nodes(node_type)` — ~6 distinct values over 100k rows is a
  seq scan regardless.
- No separate `graph_edges(source_id, target_id)` index — the UNIQUE
  constraint's btree already serves that prefix.
- Idempotent rebuild: `DELETE FROM graph_edges; DELETE FROM nodes;` (in
  that order) or `TRUNCATE nodes, graph_edges` in one statement on
  Postgres — a FK-referenced table cannot be truncated alone.
- Traversal MUST guard against cycles (a visited-set; Postgres `CYCLE`
  clause) — `cites`/`follows` graphs are cyclic, and a naive recursive
  CTE loops until memory exhaustion.
- Hub nodes (e.g. s 8-1 with tens of thousands of inbound `applies` edges)
  blow up hop-2+ combinatorially. Per-hop `LIMIT`/weight cutoff is
  required; "single-digit ms" only holds for non-hub neighbourhoods.

## 5. Embedding layer

- Embedding model: text-embedding-3-small (1536-dim) — matches the shipped
  pipeline (`scripts/openai_embed.py`, `vector_search_service.py`) and the
  43,231 existing rows in `data/embeddings.db`. Switching to 3-large means
  re-embedding the entire corpus for a marginal retrieval gain on
  exact-text legal material; not worth it.
- Chunks stay in the existing `embeddings.db` for v1. If Postgres is ever
  adopted, unify via pgvector (`chunks (id, node_id FK, chunk_index, text,
  embedding vector(1536))`).
- Measured cost (2026-08-16): 43,231 chunks = 13.67M tokens = $0.27.
  Private rulings corpus (raw JSON): 57,608 rulings × ~2,844 tokens ≈
  164M tokens ≈ $3.30 at 3-small (~$21 at 3-large). Cleaned embedding
  text will be cheaper than raw JSON. One-off, not per-query.
- Chunking rules per node type:
  - section: one chunk per section (sections are short)
  - private_ruling: one chunk per Q&A pair + one per reasons paragraph
    (already structured by the scraper)
  - public_ruling / case: one per paragraph or per numbered para
  - commentary: one per chapter (chapters are the natural unit)
- Soft edges: v1 does NOT materialise `related_to` rows. `similarity_index`
  in `embeddings.db` already stores exactly this (979,669 rows, k-NN by
  cosine, threshold 0.75) and graph.py's `_add_similarity_edges` already
  serves it. Materialising a second copy doubles ETL + storage for a query
  path that works. Revisit only if the Postgres upgrade happens.

## 6. Query API + serialization

### 6.1 Endpoint

`GET /api/search?q=...&depth=1|2` — existing search, extended:

Response items carry a `graph` field — the token-lean neighborhood map:

```
graph: {
  node: "section:itaa-1997:118-110",
  label: "Main residence exemption",
  edges: {
    interpreted_by: { count: 4, top: ["TR 2025/1", "TD 2024/2"] },
    applies:        { count: 57, top: ["EV/1052514149928", ...] },
    considered_in:  { count: 3, top: ["[1986] HCA 45"] },
    explained_in:   { count: 1, top: ["master-tax-guide:ch12"] }
  }
}
```

`top` = top **3** by degree within the neighbourhood (v1; community
centrality is v2), never raw dumps. Every edge type declared in §3 that
applies to the node appears in `edges`; the label mapping covers all 10
types. The LLM sees counts + pointers, fetches content on demand by
querying the node key.

### 6.2 Serialization to LLM context

```
## s 118-110 ITAA 1997 (Main residence exemption)
INTERPRETED_BY: TR 2025/1, TD 2024/2
APPLIES: 57 private rulings (EV/1052514149928, EV/1052018296927, ...)
CONSIDERED_IN: [1986] HCA 45, [1996] HCA 36
EXPLAINED_IN: master-tax-guide ch 12
```

~80 tokens at depth=1 (verified estimate for one node with 4 edge types
and top-2 lists). The depth=2 budget must be stated and capped — counts +
top-3 per level, deduped across levels, hard cap (e.g. 400 tokens) per
result. The LLM knows where to go next without reading full text.

### 6.3 Traversal

- `depth=1`: neighborhood of each result (default)
- `depth=2`: neighborhood + neighborhood-of-neighborhood, deduped; each
  level emitted as counts + top-3, aggregated per level (NOT per-node
  expansion — that blows the context budget)
- Path queries: `GET /api/graph/path?from=KEY&to=KEY` — shortest path via
  recursive CTE, for "how does this ruling connect to this case"

## 7. Entity resolution

The critical quality gate. Without it the graph fragments: "s 118-20",
"section 118-20", "118-20 ITAA 1997" must all resolve to
`section:itaa-1997:118-20`.

- Sections: regex normalisation (act aliases: ITAA97/ITAA 1997/ITA 1936/
  TAA 1953/GST Act/FBT Act) + section-number patterns (`s 118-20`,
  `section 118-20`, `Div 40`, `Subdiv 115-A`).
- Cases: normalise to neutral citation `[year] court no`; fold in
  party-name aliases, reporter citations, AAT vs court.
- Rulings: `TR|TD|PCG|LCG|PS LA|CR|IT|GSTR|ATOID|EV` series patterns +
  year/number; private rulings already carry authnum.
- LLM mop-up pass on ambiguous strings (cheap DeepSeek batch) BACKSTOPS
  the regex pipeline (`_parse_leg_ref` / `_case_key` in
  `pipeline/graph_etl.py`): only strings regex leaves unresolved or
  ambiguous (multi-act matches). Output is a key mapping table
  (`data/entity_alias_map.json`, built by `pipeline/entity_backstop.py`
  collect/local/map/validate stages), reviewed once, cached, and served at
  runtime by `backend/services/graph_alias.py` (search `aliases` field +
  `/api/graph/data?ref=`).

## 8. Community detection + centrality (DEFERRED to v2)

- Leiden algorithm over the explicit edge table (undirected projection)
  is deferred. v1 `top` lists use degree ranking within the neighbourhood
  (`ORDER BY count(*) DESC LIMIT 3`) — sufficient for representative
  exemplars at this scale.
- v2 adds: Leiden communities (tax topic clusters), per-node centrality
  within community, LLM-generated community→label map (one batch over
  cluster member titles), `graph_community(node)` in depth=2 output.
- Trigger for v2: degree ranking demonstrably picks bad exemplars on
  sampled queries.

## 9. Ingestion pipeline

1. Private rulings (~57.6k): nodes from manifest; edges from parsed
   legislation refs + case refs + inline public-ruling refs (mop_up
   enrichment output)
2. Public rulings (11,932 in rulings_list.json): nodes + edges from
   **ruling_section_index.json** (10,410 rulings → act/section pairs).
   `citation_index.json` is now populated (7.8 MB, built 2026-08) and
   consumed by `load_citation_index()` in `pipeline/graph_etl.py`
   (applies/interpreted_by/considered_in edges) alongside
   `ruling_section_index.json`.
3. Cases (~8.5k): nodes + edges from case_section_refs.json,
   section_case_index.json; follows/distinguishes via LLM pass (v2)
4. Commentary: nodes per chapter; edges via smartlink_index.json +
   section refs
5. Definitions: nodes + `defines` edges to sections
6. Embed chunks (existing pipeline); soft-edge lookup via
   `similarity_index` — no materialised related_to rows in v1
7. Validate: every edge endpoint resolves; every workflow fetch anchor
   exists (§ procedural-knowledge spec)
8. Degree-ranked exemplar computation for `top` lists

Run as idempotent ETL: delete in FK-safe order (graph_edges first) +
rebuild per corpus version. ~1-2h total (embedding is the bulk), not
per-query.

## 10. Open questions

- Edge count estimate: ~57k private rulings × ~3 leg refs + ~1 case ref =
  ~200-250k explicit edges. Confirmed scale is fine for SQLite CTEs.
- `related_to` threshold tuning: 0.75 default; evaluate precision on a
  sample before locking (only relevant if soft edges move into the graph
  proper — v1 reuses similarity_index).
- Whether `follows`/`distinguishes` (LLM-extracted, ~8.5k cases) justify
  the batch cost vs just `cites` — deferred with the Leiden pass; `cites`
  alone covers v1.
- pgvector vs existing sqlite embeddings.db: resolved for v1 (SQLite);
  revisit only with the Postgres upgrade.
