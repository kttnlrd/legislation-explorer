# CDN-0162 — PBRs first-class searchable + graph edge backfill — FIX PLAN (v2, post-opus-audit)

## Ticket
Make PBRs (edited private rulings) first-class searchable content by section number
and keyword, and populate the private_rulings block consistently across sections
(currently present on s 340, absent on s 26AH).

## Audit status
- Claude Code opus audit (2026-08-23) returned REJECT on v1 because the regex
  was patched to `[A-Za-z]+` (mandatory letter suffix) — that drops ~65% of
  plain-numeric refs (8-1, 995-1, 204-30(1), 12-35, 142 all fail). v2 fixes
  this with `[A-Za-z]*` (zero-or-more). All audit negative cases verified passing.
- Opus findings incorporated: selftest now covers `_parse_leg_ref` (was only
  testing `REF_RE`); service must be STOPPED during rebuild; post-rebuild gate
  is `applies` edge count, not orphans; lowercase-26ah node claim corrected
  (comes from definitions loader, not parser — separate ticket).

## Changes applied (verified)

### 1. `backend/fastmcp_server.py` — search_all PBR branch (DONE, verified live)
- `search_all` calls `search_private_rulings_fts(query, limit)` when
  `type_filter` is None / "ruling" / "private_ruling"; results under
  `results["private_rulings"]`. Signature matches
  `search_private_rulings_fts(q, limit=20, operator="AND")`.
- Verified: `search_all("26AH", type_filter="ruling")` returns 5 PBR hits (was 0).
- Minor (audit): tool docstring should mention `private_ruling` as accepted
  type_filter — add in this pass.

### 2. `pipeline/graph_etl.py` — leg-ref regex fix (DONE, selftest-verified)
- `_SECTION_RE`, `_RANGE_RE`, `_SCHED_SECTION_RE`: `[A-Za-z]?` → `[A-Za-z]*`.
- `_parse_leg_ref` verified on: 26AH→26AH, 102AAA→102AAA, 8-1→8-1,
  995-1→995-1, 204-30(1)→204-30, 142→142, schedule 1 section 12-35→12-35,
  ranges, all pass.
- `--selftest` extended with `_parse_leg_ref` asserts (audit finding).
- `pipeline/entity_backstop.py` `_SECTION_KW_RE`/`_POST_RE`: same `*` fix
  (second instance of the bug class, found by cross-check).

### 3. Lowercase 26ah node — NOT fixed by rebuild (audit-corrected)
- `section:itaa-1936:26ah` (node 40129) comes from `load_definitions`
  reading `data/definitions_all.json` verbatim — NOT from `_parse_leg_ref`.
- `Graph.node` keys are exact strings; `26ah` ≠ `26AH`, no merge.
- 13,750 lowercase section nodes exist. Fix = normalize section ids in the
  definitions loader/source → **separate ticket**, out of scope here.
- Verified `26A` (node 13717) has 0 applies edges → the 26AH refs were never
  in the Aug 18 build (corpus files newer); rebuild will genuinely add them.

## Execution steps (updated per audit)

1. **Stop service** — `systemctl --user stop legislation-explorer.service`
   (audit: rebuild holds write lock on live-served DB → SQLITE_BUSY; readers
   see half-loaded graph if not stopped).
2. **Backup** — `cp data/graph.db backups/graph_20260823_pre_cdn162.db`
3. **Rebuild** — `python3 pipeline/graph_etl.py --rebuild` (drops nodes +
   graph_edges, recreates schema, loads in one run; prints counts).
4. **GATE (audit): `applies` edges ≥ 373,310** (current count) AND
   `section:itaa-1936:26AH` has >0 applies edges. Orphans==0 is NOT sufficient
   (Graph.section creates any node it references).
5. **Rebuild neighborhood_index** — `python3 -m backend.services.graph_neighborhood`
   (drops + recreates; node ids are reassigned by step 3 so this MUST follow).
6. **Start service** — `systemctl --user start legislation-explorer.service`;
   health 200.
7. **Verify live** — search_all("26AH"), graph API private_rulings block for
   26AH.
8. **Mark CDN-0162 fixed** in PostgreSQL with patch note; file separate ticket
   for definitions casing.

## Not affected (audit-confirmed, stated for clarity)
- `search_index.db` (backs search_private_rulings_fts) — separate DB, regex
  change doesn't touch it, no rebuild.
- `data/case_section_refs.json` — consumed as pre-parsed pairs, not via
  `_parse_leg_ref`.
- Four scripts with their own section regexes (backfill_legislation_refs.py,
  generate_all_summaries.py, fix_remaining.py, generate_batch_summaries.py) —
  not audited for this bug; follow-up ticket, not a blocker.
