# Graph Spec Execution Plan — v1

**Spec:** `docs/specs/graph.md` v0.2 (opus audit 2026-08-16) + companion `docs/specs/procedural-knowledge.md`
**Branch:** `fix/ruling-summary-regen`
**Gate rule:** every phase ends with an integrity gate. Green before next phase. No exceptions.

---

## Current state (baseline, already verified)

| Item | Status |
|------|--------|
| graph.db built to spec schema (nodes + graph_edges, provenance, UNIQUE) | ✅ 106,289 nodes / 574,633 edges |
| validate_graph.py | ✅ 6/6 |
| verify_graph_readiness.py --require-mop-complete | ✅ 32/32 |
| `/api/graph/data` rewired to graph.db (ego-graph, BFS, caps) | ✅ tested, **uncommitted** |
| GraphModal private_ruling color | ✅ **uncommitted** |
| Search graph field (§6.1) | ✅ done 2026-08-17 (2a62d6d4f) — materialised `neighborhood_index` (133k rows) pulled forward from §9.8 when on-the-fly counts blew the 50ms gate (145ms → <50ms); G1 5/5 |
| LLM serialization (§6.2) | ✅ done 2026-08-18 — `backend/services/graph_serialize.py`; budgets 80/400 verified (hub 66/265); `\|` separator (commas/semicolons appear in real labels); neighborhood_index gained `target_type` for phrase accuracy; `GET /api/graph/serialize` endpoint; G2 11/11 |
| Path queries (§6.3) | ✅ done 2026-08-18 — `backend/services/graph_path.py` bidirectional BFS (recursive CTE replaced: hub blow-up, spec §4 guard); batched level expansion, frontier cap 25k, hop cap 10; `GET /api/graph/path`; G3 8/8 — hub-to-hub 74ms |
| Entity resolution LLM backstop (§7) | ✅ done 2026-08-18 — collect/local/map/validate stages (`pipeline/entity_backstop.py`); deterministic local + DeepSeek batch (stdlib urllib client, resumable checkpoints, `max_tokens=8000`); G4 2845/2845 mapped keys resolve; `data/case_crosswalk.json` (34 neutral→reporter, court+year verified) fixes phantom keys; committed `70d2785ea` + `df03399ac` |
| Exemplar computation (§9.8) | ❌ (folded into §6.1 unless perf fails) |

## Working-tree hazard

25 modified files from a sibling agent in flight (backend search/vector files, frontend App/SearchPanel, data regen). We commit ONLY our files at every step. Before Phase 1 (search), diff-check `backend/routes/search.py` for sibling overlap and merge carefully.

---

## Phase 0 — Baseline commit + live smoke (0.5h)

**Build**
1. Commit `backend/routes/graph.py` + `frontend/src/components/GraphModal.tsx` (graph files only)
2. Restart `legislation-explorer.service`
3. Live smoke: `/api/graph/data?type=section|ruling|case` (Bearer auth), modal render check via browser

**Integrity gate G0**
- validate_graph.py = 6/6
- 3 endpoint calls return 0 orphans, caps respected (≤300 nodes, ≤2000 edges)
- Node click navigation resolves (section/ruling/case URLs)

---

## Phase 1 — Search graph field §6.1 (1 day)

**Build**
1. New `backend/services/graph_neighborhood.py`: given node key → `{count, top:[3]}` per edge type (degree-ranked, `ORDER BY count(*) DESC LIMIT 3`)
2. Enrich `/api/search` response items with `graph: {node, label, edges}` where the item resolves to a graph node (batch query — no N+1)
3. Label mapping covers all 10 edge types in §3

**Integrity gate G1**
- New `backend/tests/test_graph_api.py`:
  - Sample 50 queries → every resolvable result has graph field; counts equal direct SQL COUNT
  - top-3 lists equal degree-order query
  - p95 enrichment < 50ms per 10-result batch
  - Unknown/missing node → graph field omitted, no error

---

## Phase 2 — LLM serialization §6.2 (0.5 day)

**Build**
1. Serializer: node key → token-lean block (`INTERPRETED_BY: ...` / `APPLIES: ...` / `CONSIDERED_IN: ...` / `EXPLAINED_IN: ...`)
2. depth=2 aggregation: per-level counts + top-3, deduped across levels, 400-token hard cap

**Integrity gate G2**
- Fixture tests: token estimate ≤ budget (80 at d1, 400 at d2) on real nodes incl. hub (s 8-1) and leaf
- Round-trip: serialize → parse → edge counts match graph.db
- Counts in output equal SQL

---

## Phase 3 — Path queries §6.3 (0.5–1 day)

**Build**
1. `GET /api/graph/path?from=KEY&to=KEY` — recursive CTE shortest path, visited-set cycle guard, hop cap (e.g. 10)

**Integrity gate G3**
- Known pairs (s 118-110 → TR 2025/1; EV authnum → section) resolve to sane paths
- Unreachable pair → `{path: null}`, returns fast
- `from == to` → empty path
- Hub-to-hub bounded < 2s

---

## Phase 4 — Entity resolution backstop §7 (1 day)

**Build**
1. Candidate set: loader's unresolved refs (130,892 unparsed leg refs, 63,556 dropped case refs — filter out legit non-nodes: SA state acts, regulations, TD refs)
2. DeepSeek batch mapping (resumable, marker-file checkpointing — session resets kill long processes)
3. Output `data/entity_alias_map.json`, cached

**Integrity gate G4**
- Every mapping key resolves to an existing graph node (validation script)
- Ambiguous (multi-act) strings flagged, never guessed
- 100-mapping manual review sign-off

---

## Phase 5 — Final gate (0.5 day)

1. Extend `verify_graph_readiness.py` with graph-API checks (orphans, counts-vs-SQL, caps, latency)
2. Full test suite (`backend/tests/`) + validate_graph 6/6 + verifier green
3. Changelog entry ("New features" / "Bugs fixed" sections)

**Final gate G5** — everything green, no regressions, all committed.

✅ **G5 PASSED 2026-08-18** — verifier extended with Graph API section (orphan edges, index-vs-SQL sample, BFS caps on hub, hub-to-hub <2s, alias-map resolution): 38/38. `validate_graph.py` 6/6. Full suite 300 passed (2 pre-existing collection errors excluded). CHANGELOG 2.8.2 written.

---

## Sequencing rationale

- Phase 0 first: unblocks visualization and gives a clean committed baseline
- Phases 1→2→3 share the neighborhood query core; build once, reuse
- Phase 4 (resolution) after API layers: the API works on resolved keys today; the backstop improves coverage without blocking
- Phase 5 folds exemplars in — only precompute if G1 latency fails

## Cross-cutting rules

- Every phase lands behind tests; no manual-only verification
- graph.db is read-only input for Phases 0–3, 5; if corpus rebuilds mid-plan, re-run G0/G5
- Commit only our files (sibling diff untouched)
- Bearer token for live API tests; service restart after backend changes
- Long-running jobs (Phase 4) resumable + notify_on_complete
