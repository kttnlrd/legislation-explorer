# Bugs to Fix Next Time (v2.1.1) — status as of 2026-08-24

## RESOLVED

### 1. `get_rulings_for_section` returns `"year": 0` on every ruling — RESOLVED
The tool was **removed** (`7b36f01bc`); ruling downloads + ATO links now ride on
summary payloads. The list endpoint (`list_rulings`) no longer emits a `year`
field per ruling — the year lives in `citation_display` ("TR 2024/1").

### 2. `get_ruling` doesn't normalise LCR → LCG — RESOLVED
`data_loader.py` maps both `LCG` and `LCR` → `COG` for ATO links and lookup;
MCP tool hint documents "LCR=LCG".

### 3. `get_definition` only resolves ITAA 1997 s 995-1 — RESOLVED
`get_definition_across_acts()` (data_loader.py) searches every act with a
definitions index, returns `also_defined_in` for cross-act matches.

### 4. Compilation metadata mismatch (GST 96 vs 228) — RESOLVED
Compilation literals were fixed in the Aug 2026 checker rebuild
(`2ce1deaa0`); `rebuild.sh` literals + `tree.json` are fixed together per the
updates skill. Section footers and `list_acts` agree.

## OPEN / KNOWN

### 5. `list_rulings` default `limit=100` makes `by_year` show one year
Calling `list_rulings()` with no params returns only the first 100 rulings
(ordered oldest-first, all 2001), so `by_year` has a single key. Docstring says
"List all ATO rulings". Not a regression — pagination design; use
`limit=0`/`counts_only`/`year=` for full views. Decide whether default should be
larger or docs should say "first 100".

### 6. Corps Act chapeau drop (CDN-0124) — BLOCKED, needs source PDF
313 corps sections (7.5% of corpus) lost their chapeau line at ingestion
(s 259A verified: heading jumps straight to "(a)"). Only corps act affected
(all other acts 0). No raw PDF stored in `source/` — faithful repair requires
re-downloading the Corporations Act 2001 compilation from FRL and a
chapeau-preserving re-ingest. LARGE job; deferred until source acquired.

### 7. Definitions index quality (itaa-1936)
532 terms have sentence-length keys ("1c) a reference in this act to foreign
income") from the extractor — cosmetic/quality class C, not blocking lookups
(term → 6AB resolves correctly after the canonical-id fix).

---

### See also: pre-existing GST 195-1 limitation
The GST definitions file (`195-1.md`) has definitions that run together on
blockquote lines instead of clean col-0 entries. Data extraction issue, not
tool logic; blocks clean `get_definition` snippets for some GST terms.
