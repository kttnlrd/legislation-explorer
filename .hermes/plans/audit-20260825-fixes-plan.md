# Fix Plan — Audit Findings 2026-08-25 (API→MCP layer audit)

Source: `scripts/randomised_api_mcp_test.py` run (seed 20260825) — 88 checks,
0 FAIL, 5 FIND. Each FIND below is a fix item with hypothesis, root cause,
fix, verification gates, risk, rollback. Execution order: F1 → F2 → F3 → F4
→ F5 (no code) → F6 drafts → F7/F8 UI → re-audit.

Pre-flight (MANDATORY before F2/F3 renames): `git status --short` must be
clean of uncommitted corpus WIP (rule: never rename over WIP). Backups:
`cp data/<act>/tree.json backups/tree_<act>_pre_fix.json` for every touched act.

════════════════════════════════════════════════════════════════════════

## F1 — Harding [2019] FCAFC 29 missing from API text store (dual case-store split)

**Finding:** `/api/case/[2019] FCAFC 29` → 404. MCP `get_case` returns full
metadata (Harding v Commissioner of Taxation, 2019-02-22) from
`data/fcafc_tax_cases.json` (metadata store). API `/api/case` reads
`CASE_DIR = /home/harrison/projects/asic-scraper/cases` (text store, 524
files) — no `[2019]_FCAFC_29.json`.

**Root cause:** two case stores; the text store lacks the case.

**Fix:**
1. Fetch AustLII HTML for FCAFC 2019/29:
   `python3 -c` using curl_cffi impersonate="chrome120" (mirror
   `scripts/download_case_texts.py` AUSTLII_CASE pattern):
   `https://www.austlii.edu.au/cgi-bin/viewdoc/au/cases/cth/FCAFC/2019/29.html`
2. Write `/home/harrison/projects/asic-scraper/cases/[2019]_FCAFC_29.json`
   with the text-store schema (verified against [2009]_FCAFC_29.json):
   `{citation, case_name, year, court, decision_date, source_url, content}`
   — citation `[2019] FCAFC 29`, case_name `Harding v Commissioner of
   Taxation`, year 2019, court FCAFC, decision_date 2019-02-22 (from the
   metadata store), content = raw AustLII HTML.
3. Note in code/docs: MCP get_case reads the metadata store; API /api/case
   reads the text store. Full store unification is out of scope; record as
   known issue in BUGS_NEXT_TIME.

**Gates:** `/api/case/[2019] FCAFC 29` → 200 with body containing "Harding";
MCP `get_case` still 200 and now consistent; JSON validates against schema.

**Risk:** AustLII blocks → use the existing script's impersonate/verify
settings; fall back to `https://www8.austlii.edu.au/...` mirror.

**Rollback:** `git rm` the added file (or delete).

════════════════════════════════════════════════════════════════════════

## F2 — 190 ligature filenames + frontmatter ids in master-tax-guide

**Finding:** 190 files with non-ASCII (U+FB01 ﬁ) basenames AND frontmatter
`section:` ids (e.g. `oﬀences.md` / id `oﬀences`); tree.json has 193
ligature paths. API resolves via fallback glob but slugs are polluted.

**Root cause:** parser ingested PDF text with ligatures into filenames,
frontmatter, and tree paths.

**Fix:**
1. NFKC-normalize the basename AND frontmatter `section:` value of each of
   the 190 files (`unicodedata.normalize("NFKC", s)` — ﬁ→fi, ﬀ→ff).
   `git mv` old → new (preserve rename history).
2. Rewrite `data/master-tax-guide/tree.json`: NFKC-normalize every `path`
   and `id` string (193 paths).
3. Rebuild indexes that read tree.json/filenames:
   `python3 scripts/build_smartlink_index.py` (and
   `build_section_case_index.py` if it covers this act). FTS index stores
   frontmatter ids (now normalized) — rebuild search index if the route
   doesn't auto-build: `python3 -m backend.services.search_index` (check
   exact module name at execution; /api/search auto-builds when missing).

**Gates:** re-run the audit scan → 0 non-ASCII basenames; `tree.json` has 0
ligature paths; `/api/section/master-tax-guide/oﬀences` AND
`/api/section/master-tax-guide/offences` both → 200 (old id tolerated via
fallback, new id canonical); integrity gate sections domain PASS.

**Risk:** 193 vs 190 path count (3 extra tree entries) — normalize whatever
is there; verify tree leaf count unchanged after normalization.

**Rollback:** `git checkout` (files + tree.json).

════════════════════════════════════════════════════════════════════════

## F3 — 1,260 filename-vs-frontmatter case mismatches (4 acts)

**Finding:** files named lowercase-suffix but frontmatter id uppercase:
fbt-1986 170 (135m→135M), itaa-1936 547 (6ab→6AB), sis-1993 343
(224c→224C), taa-1953 200 (14zo→14ZO). tree.json paths all lowercase
(`'6AB' → 'part-i/division-unknown/6ab.md'`). 0 rename collisions.

**Root cause:** parser wrote letter-suffixed filenames lowercase; canonical
ids uppercase. Resolver's case-insensitive glob fallback masks it.

**Fix:**
1. For each of the 1,260 files: `git mv` to the frontmatter `section:` id
   (uppercase), same directory.
2. Rewrite the 4 acts' tree.json: replace each lowercase path basename with
   the canonical id (map filename→frontmatter id built in step 1).
3. Rebuild tree-dependent indexes (same as F2 step 3).
4. Graph: content_ref may hold old paths — only rebuild graph if the
   re-audit shows stale refs (graph nodes keyed by canonical section ids
   already, per CDN-0164; check `content_ref` values for `.md` paths before
   deciding).

**Gates:** audit scan → 0 case mismatches; tree.json paths match on-disk
filenames for ALL leaves (set-diff both directions, per act); random sample
of renamed sections (incl. 135M, 6AB, 224C, 14ZO) → `/api/section/{act}/{id}`
200; search exact-match still ranks; integrity gate PASS.

**Risk:** case-insensitive filesystems (none here — Linux); rename
collisions already checked = 0. Do NOT run over WIP (pre-flight).

**Rollback:** `git checkout` + re-run tree rewrite (or `git revert`).

════════════════════════════════════════════════════════════════════════

## F4 — MCP lacks ruling-by-citation tool (get_ruling)

**Finding:** MCP tools/list has no get_ruling; API has
`/api/ruling/{citation}` backed by `backend/routes/rulings.py:get_ruling()`
(handles TR/AID alias normalization, summaries + text). MCP users cannot
fetch a ruling by citation.

**Fix:**
1. In `backend/fastmcp_server.py`, add:
   ```python
   @mcp.tool(structured_output=False)
   async def get_ruling(citation: str) -> str:
       """Fetch an ATO ruling by citation (e.g. 'TR 2022/1')."""
       from .routes.rulings import get_ruling as _get_ruling
       import json
       return json.dumps(_get_ruling(citation), indent=2, default=str)
   ```
   Place next to `list_rulings` (~line 2263).
2. `python3 -m py_compile backend/fastmcp_server.py`; restart service.

**Gates:** `tools/list` contains get_ruling; MCP `get_ruling("CR 2026/1")`
returns the same content as `/api/ruling/CR_2026_1`; prod suite still 52/52
(`python3 backend/tests/test_prod_v270.py`).

**Risk:** import cycle (fastmcp_server ↔ routes.rulings) — import inside
function avoids it; route function returns dict (verify type at execution).

**Rollback:** revert the one-file change.

════════════════════════════════════════════════════════════════════════

## F5 — list_rulings default limit=100 (no fix, documented)

**Finding:** MCP `list_rulings` slices before grouping → bare call shows
`ato_rulings_total: 100`, single-year by_year view. Confirmed pagination
design (same as /api/rulings-list), NOT a regression. Already documented in
BUGS_NEXT_TIME; no code change.

════════════════════════════════════════════════════════════════════════

## F6 — Draft rulings: missing from corpus AND hidden in UI (Harry 2026-08-24)

**Findings (evidence gathered):**
- Corpus holds only **2 drafts**: `TD_2026_D1`, `TD_2026_D2`.
- ATO currently publishes at least **PCG 2026/D1, /D2, /D3** (docids
  DPC/PCG2026D1..3/NAT/ATO/00001 — verified via web) — **none in corpus**.
  More in "advice under development" pipeline. No draft enumeration exists:
  `check_ruling_updates.py` has zero draft handling.
- The 2 TD drafts ARE in `/api/rulings-list` but under **part id "0" titled
  "IT Rulings"** — the year extraction fails on `/D` citations, so the UI
  (year-grouped tree) never shows them in the 2026 → TD division.
- `/api/search?q=TD 2026/D1` → **0 hits** (citation normalization gap);
  MCP `search_all` normalizes (`TD 2026 D1`) and finds it. Content search
  ("wrapping contract") misses the D2 draft body.

**Fixes:**
1. **Draft enumeration + ingest**: extend `scripts/check_ruling_updates.py`
   (or new `scripts/fetch_draft_rulings.py`) to enumerate ATO draft DocIDs
   (`DXT/*` determinations, `DPC/*` PCGs, `DTR/*` rulings) for the current
   year; fetch via the print-view pattern (`fetch_ruling`); store as
   `data/rulings/{PREFIX}_{YEAR}_{Dn}.txt` (+ summary JSON), matching the
   existing corpus layout. Get at least PCG 2026/D1-3 (TD D1/D2 already
   present).
2. **Year extraction fix**: the rulings tree builder's year regex must
   handle `/D\d+` citations → drafts land under the correct year part and
   type division (2026 → TD/PCG), not part "0".
3. **Search normalization**: `/api/search` citation matching must normalize
   `TD 2026/D1` → `TD 2026 D1` (reuse the MCP normalizer) so drafts are
   findable by citation.

**Gates:** corpus has PCG_2026_D1..D3 (+ any other current drafts);
`/api/rulings-list` shows drafts under 2026 → correct division; `/api/search`
"TD 2026/D1" → ≥1 hit with the draft top-ranked; layer audit new seed → no
new FINDs; integrity gate PASS (rulings domain).

**Risk:** ATO rate limiting (use DELAY + impersonate as in
download_case_texts.py); draft DocID scheme variations — verify each type's
prefix (DXT/DPC/DTR) against a live fetch before bulk.

**Rollback:** git revert of added files + tree-builder/route changes.

════════════════════════════════════════════════════════════════════════

## F7 — UI: "Rulings" section should be "Public Rulings" (Harry 2026-08-24)

**Finding:** the Australian Tax domain contains the 'rulings' act whose tree
root renders as **"ATO Rulings"** (`/api/rulings-list` act name); MapView
hardcodes "ATO Rulings" (MapView.tsx:271); SmartLinkPanel groups under
"Rulings". Harry wants the section labelled Public Rulings.

**Fix (photo-confirmed 2026-08-24):** the dropdown header renders
`shortActName('rulings')` → fallback "Rulings". The tree division titles come
from `backend/routes/rulings.py` TYPE_DISPLAY — which is MISSING CR and PR,
so they render bare while all other types show " – description". Two other
maps (fastmcp_server.py:1981, search_service.py:669) include CR/PR but call
LCG "Law Companion Ruling" (wrong — it's a Guideline).

Concrete changes:
- `frontend/src/utils/display.ts` ACT_SHORT: add
  `'rulings': 'Public Rulings'` (and explicit `'private-rulings'` entry).
- `backend/routes/rulings.py` TYPE_DISPLAY: add
  `"CR": "CR – Class Ruling"`, `"PR": "PR – Product Ruling"`.
- `backend/fastmcp_server.py` + `backend/services/search_service.py` maps:
  `"LCG": "Law Companion Ruling"` → `"Law Companion Guideline"`.
- `frontend/src/components/SearchPanel.tsx:505` filter tab label
  'Rulings' → 'Public Rulings'.
- MapView.tsx:271 hardcoded "ATO Rulings" → "Public Rulings";
  SmartLinkPanel.tsx:289 "Rulings" group → "Public Rulings".

**Gates:** sidebar shows Public Rulings; MapView/SmartLinkPanel labels
consistent; prod suite passes (any backend label assert).

**Risk:** label-only change; check nothing matches on the old string.

════════════════════════════════════════════════════════════════════════

## F8 — UI: Private Rulings under Tax, not a standalone section (Harry 2026-08-24)

**Finding:** `frontend/src/App.tsx` DOMAINS:
`{ label: 'Private Rulings', ids: ['private-rulings'] }` is its own top-level
sidebar domain — a single section holding a single thing. Harry wants
private rulings grouped under the Australian Tax domain.

**Fix:** remove the standalone 'Private Rulings' domain entry and add
`'private-rulings'` to the **Australian Tax** domain ids:
`{ label: 'Australian Tax', ids: ['itaa-1997', ..., 'rulings', 'private-rulings', 'tax-cases'] }`.
Sidebar then nests Private Rulings under Tax beside Public Rulings and
cases. Check the tree loader handles 'private-rulings' as a root id inside
a domain (it already does as a standalone root).

**Gates:** build (`npm run build` / `vite build`) succeeds; sidebar shows
Private Rulings under Australian Tax; browsing a private ruling still works
(month/year expansion path untouched).

**Risk:** TS/type changes if DOMAINS is typed; keep the same tree-root id.

**Rollback:** revert App.tsx.

════════════════════════════════════════════════════════════════════════

## Opus audit verdict — 2026-08-26 (READ-ONLY, claude-opus-5, 100 turns)

Verdicts: F1 APPROVE-WITH-CHANGES · F2 **REJECT as written** · F3
**REJECT as written** · F4 APPROVE-WITH-CHANGES · F5 APPROVE · F6
APPROVE-WITH-CHANGES · F7 APPROVE-WITH-CHANGES · F8 APPROVE-WITH-CHANGES.
MUST-FIX (author must implement before execution):

1. **F3 graph rebuild is MANDATORY, not conditional.** 1,260 `nodes.content_ref`
   rows point at the lowercase basenames (same count as the renames).
   `fastmcp_server.py:632`/`:1010` do `DATA_DIR / content_ref...` and silently
   drop missing files. `pipeline/graph_etl.py --rebuild` becomes a required
   F3 step (gated recipe: stop service → backup → integrity_check → rebuild →
   gates → restart).
2. **F2 graph is affected too.** 124 `nodes` rows have U+FB01/U+FB00 in `key`
   or `content_ref`; 1,400 master-tax-guide nodes total. NFKC-ing frontmatter
   `section:` changes node keys (`section:master-tax-guide:oﬀences`). Add graph
   rebuild + check `citation_index.json`/`section_case_index.json` keys first.
3. **F2/F3 gate is unsound: 200 proves nothing.** `data_loader.py:938-948`
   matches tree ids case-insensitively; a missed tree.json entry → HTTP 200
   with EMPTY body (`data_loader.py:975-980`). Gate must assert non-empty
   body/frontmatter for EVERY renamed leaf, not status 200.
4. **F2/F3 FTS rebuild mandatory.** `search_service.py:35-70` DROPs+recreates
   `sections_fts` driven by tree.json — never incremental. Pin the real entry
   point (`python3 -m backend.services.search_index` does NOT exist as a
   module; verify actual module before execution).
5. **F3 restart service after renames.** `get_act_section_content`,
   `find_section_path` callers, `load_rulings`, `_definition_section_file`
   are `@lru_cache` (data_loader.py:954, 993, 615) — stale caches otherwise.
   Add "restart backend" to F2/F3/F6.
6. **F1 content format = plain TEXT, not raw HTML** (matches
   `[2009]_FCAFC_29.json`). And adding the file does NOT index into
   `data/cases.db`/`case_summaries_fts` — /api/search will still miss Harding;
   state out-of-scope or add index step.
7. **F6 year-extraction bug is in `data_loader.py:627`**, NOT the tree
   builder: `re.match(r'^([A-Za-z]+)_(\d{2,4})_(\d+)', f.stem)` — `(\d+)`
   cannot match `D1`, so `year=0` AND `ruling_type` falls to hard-coded
   default `"LCG"` (data_loader.py:618) — a SECOND bug (drafts mis-typed as
   LCG). Fix regex to `(\d+|D\d+)` AND the type default.
8. **F6 "reuse the MCP normalizer" has no referent.** No citation
   preprocessing in search_all; the only normalizer is `_normalise_case_citation`
   (fastmcp_server.py:111, for cases). Establish why MCP finds `TD 2026/D1`
   before writing the fix.
9. **F7 SmartLinkPanel.tsx:289 is a COMMENT, not a label.** Real group labels:
   `backend/routes/graph.py:378` `"interpreted_by": "Rulings"` + `:377`
   `"applies_private": "Private Rulings"`. Editing the comment is a no-op.
10. **F7 three more "ATO Rulings" sources:** `acts.py:32` (/api/acts name),
    `fastmcp_server.py:1064` (MCP list_acts), `rulings.py:174` + `:258/:281/:313`
    (act field). If `rulings.py:174` changes, `backend/tests/test_api_content.py:175`
    (`assert data["act"] == "ATO Rulings"`) fails — plan's "prod suite" gate
    does not cover that file; add it.
11. **F8 second DOMAINS list:** `SearchPanel.tsx:31` has its own
    `{ label: 'Private Rulings', ids: ['private-rulings'] }`. Change both.
12. **F4 absolute import** (`from backend.routes.rulings import get_ruling as
    _get_ruling`, consistent with fastmcp_server.py:302/772/778) + wrap
    `HTTPException(404)` (rulings.py:325) into a JSON error for MCP.
13. **Pre-flight FAILING (WIP in repo):** ~30 modified corpus/code files NOT
    authored by this fix session (definitions feature WIP: markdown.py,
    App.tsx, definitions.json ×3, 6 tree.json, ~15 corpus sections,
    build_cch_explorer.py) + untracked `scripts/_cron_probe*.py`,
    `.hermes/plans/*`, `data/definitions_all.json.bak-*`. F2/F3/F8 conflict
    with this WIP (master-tax-guide tree.json + itaa-1936 266-10.md +
    App.tsx are WIP-modified). RESOLUTION REQUIRED before those items: commit
    or stash the WIP (owner: parallel hermes CLI session on pts/2).

## Codex review verdict — 2026-08-26 (read-only exec)

Overall **APPROVE-WITH-CHANGES**; **F6 REJECT** until second regex, citation
display, and discovery completeness gates added. Per-item: F1-F5 AWC/APPROVE,
F6 REJECT, F7/F8 AWC, re-audit AWC, order AWC.

Codex MUST-FIX (supersedes/extends opus where overlapping):

1. Real FTS command is `python3 scripts/rebuild_search_index.py`
   (calls `init_search_index()` at :7) — drop the nonexistent module command.
2. **Vector-index handling mandatory for F2/F3**: `embeddings.db` +
   `embeddings_meta.pkl` retain section ids AND file paths
   (vector_search_service.py:128; openai_embed.py:188). Renames require
   `openai_embed.py --type sections`, matrix snapshot rebuild, restart,
   gates proving no old ids/paths remain.
3. Gates must validate EVERY rename across disk/tree/FTS/graph/vectors —
   not samples. HTTP 200 can carry `{}` + empty body (data_loader.py:968).
4. Preserve generated old-path→new-path MANIFEST; reject duplicate targets
   before mutation (rerun collision check after WIP; currently zero; F3 =
   1,260 one-to-one, F2 = 193 occurrences / 190 paths). Tree rewriting is
   deterministic from the manifest.
5. Graph rebuild UNCONDITIONALLY after F2 and F3 (nodes embed canonical ids
   + physical paths from tree data — graph_etl.py:175,183).
6. Audit/rebuild section-keyed derivative indexes: `citation_index.json`
   already holds ≥1 affected lowercase ITAA 1936 key; smart-link generation
   consumes section ids verbatim (build_smartlink_index.py:131). Gate old
   vs new key sets.
7. F6 must ALSO change the FTS ingestion regex at search_service.py:108 —
   else draft citations enter `rulings_meta` with year 0 / blank type even
   after `load_rulings()` is fixed.
8. Draft citation display parsing at search_service.py:687 accepts only
   numeric final components → `TD_2026_D1` renders "TD 2026 D1" not
   "TD 2026/D1".
9. **F6 diagnosis corrected**: REST and MCP BOTH call `search_rulings`;
   normalization already exists at search_service.py:785; MCP delegates at
   fastmcp_server.py:1362. REPRODUCE the REST-vs-MCP difference against the
   same process/db before changing normalization (the plan's premise that
   MCP normalizes and REST doesn't is suspect).
10. Draft discovery completeness gate: record the authoritative listing
    source; FAIL if a fetched doc's citation/status/type/year disagrees
    with its filename.
11. F4 direct success + 404 tests; `test_prod_v270.py:75` asserts a SUBSET
    of tool names; `:140` contains a STALE statement that get_ruling was
    removed — update it.
12. F7 must change graph grouping (graph.py:378), API/MCP act names, ALL
    ruling `frontmatter.act` values, + explicit assertion
    test_api_content.py:175.
13. Resolve WIP BEFORE deriving rename maps or editing either DOMAINS list
    (App.tsx:43 + master-tax-guide/tree.json modified); rerun collision
    counts + derived-index impact after WIP lands.

F6 rework required before execution: add search_service.py:108 regex fix,
:687 display fix, discovery completeness gate; reproduce REST-vs-MCP search
difference first.

1. `python3 scripts/randomised_api_mcp_test.py` with a NEW seed (edit SEED
   → e.g. 20260826): expect 0 FAIL and FINDs reduced to 0 (F1/F2/F3/F4
   resolved; F5 remains a documented note).
2. Integrity gate: `python3 scripts/verify_data_integrity.py --domain all
   --json-out /tmp/integrity_20260825b.json` → PASS.
3. Manual review sample: 2-3 renamed sections + Harding API response +
   get_ruling MCP response (Harry's rule — no blind green).
4. Commits (logical): F1 (case file), F2 (master-tax-guide renames +
   tree), F3 (4-act renames + trees), F4 (MCP tool). Push.
5. Update BUGS_NEXT_TIME.md (case-store split note; resolved classes) and
   patch `randomised-data-audit` + `legislation-explorer-error-fixes`
   skills with any new pitfalls.

## Audit chain (mandated before execution)

This plan goes to: Claude Code opus READ-ONLY audit → Codex review → execute
only after both pass. Honest gap to disclose to the reviewers: F2/F3 renames
touch ~1,450 files total; the tree.json rewrites are derived from the rename
map and must be validated by the set-diff gate, not assumed.
