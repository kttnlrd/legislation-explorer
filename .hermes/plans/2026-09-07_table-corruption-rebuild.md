# Plan: Table-corruption rebuild (CDN-0186/0187 class) — from authoritative PDFs

Date: 2026-09-07 · Repo: ~/legislation-explorer (master @ 79a649408)
Ticket: CDN-0190 closed; new class surfaced by C11 detector → CDN-0186/0187 family.
Status: FOR REVIEW (opus READ-ONLY → codex) — do not execute before both pass.

## Problem

Tables in section markdown are corrupt at scale. Manual check against raw
volumes + the new C11 audit class (`scan_table_coherence`, committed
1114e6e0c) finds **240 files / ~747 findings** across 6 acts:

| act       | findings (approx) | staging PDFs |
|-----------|-------------------|--------------|
| itaa-1997 | 416               | 12 vols     |
| taa-1953  | 102               | 4 vols      |
| gst-1999  | 70                | 2 vols      |
| fbt-1986  | 69                | 2 vols      |
| itaa-1936 | 58                | 7 vols      |
| sis-1993  | 32                | 2 vols      |

Three corruption signatures (C11_table_midword / _glyph / _truncated):
1. **Mid-word column splits** — PDF column text cut across pipe cells:
   `| ... ast | erisked terms ... |` (word continues in next cell), e.g. GST 9-69.
2. **Extraction glyph junk** — `ç ÷ ´ ê ú æ` etc in formula tables, e.g. FBT 9, 135W.
3. **Truncated rows** — cell text cut at page boundary mid-clause, row ends on a
   bare connector (`The partnership and |`), e.g. ITAA 40-40, 43-90, 115-30.

Root cause: the original PDF→markdown section parser flattened multi-page /
multi-column PDF tables without reflowing wrapped cell text or re-joining
page-split rows. The integrity gate never read inside `|` rows (C5 skips
tables by design); the old content classes never parsed table cells. Both now
fixed at the detector level — the corpus is not.

## Evidence (manual, verified)

- ITAA 115-30: raw vol03 shows a clean 3-col, 10-row table; committed .md has
  rows split into blockquote shards + truncated cells; cron's WIP flatten
  merged cells and lost text (row 2 ends `...replacement asset for a |`).
- ITAA 109-55: raw vol03 clean; committed file's rows 9/15A/17 truncated.
- GST 9-69/29-39/31-99: `*To find definitions of ast | erisked terms` — the
  dictionary footnote itself is tableised and split.
- FBT 135W/9: formula glyph garbage `ç 0.2 ´ Base value ´ were pr | ovided`.
- Cron WIP (10 itaa files, uncommitted, timestamped 07:53) was **lossy**:
  applied `apply_itaa_table_fixes.py` output which validated structure but not
  content; files reverted to HEAD (snapshot in /tmp/cron-wip-tables-20260907/).

## Why the existing repair tool is not enough

`extract_itaa_tables_pdf.py` / `apply_itaa_table_fixes.py` (CDN-0171 era)
reconstruct tables from PyMuPDF word x-positions. It fixed ~9 sections but the
driver's `validate_md()` checks ONLY structural soundness (frontmatter, column
counts) — never that the extracted text equals the PDF text. Lossy output
passes. Any rebuild MUST gate on content fidelity, not just structure.

## Approach — three-act rebuild, act-gated, content-verified

### Phase 0 — tooling audit + fidelity gate (before touching corpus)

1. For each act, inventory flagged files + locate source PDF volume mapping
   (frontmatter `compilation_no` → staging source).
2. **Source-version audit (CRITICAL — discovered 2026-09-07):**
   | act       | corpus fm | repo raw (data/<act>/raw)      | staging raw has              | rebuild source |
   |-----------|-----------|--------------------------------|------------------------------|----------------|
   | itaa-1997 | 266       | comp **263** (STALE)           | comp266 vol01-12.pdf + .txt  | **comp266 PDFs** (word-pos extractor) |
   | gst-1999  | 96        | vol01-02.txt comp 96 ✓         | vol01-02.txt comp 96         | repo txt (layout slicer) — no PDFs |
   | sis-1993  | 126       | part1-2.txt comp 126 ✓         | part1-2.txt comp 126         | repo txt (layout slicer) — no PDFs |
   | taa-1953  | 222       | vol01-04.txt comp 222 ✓        | comp225 PDFs (NEWER)         | repo txt 222 (or comp225 PDFs only if prose diff shows tables unchanged) |
   | fbt-1986  | 96        | part1/2 + vol txt comp 96 ✓    | comp97 PDFs (NEWER)          | repo txt 96 (or comp97 PDFs only if prose diff shows tables unchanged) |
   | itaa-1936 | 191       | vol01-07.txt comp 191 ✓        | comp192 vol01-07 PDFs (NEWER)| repo txt 191 (or comp192 PDFs only if prose diff shows tables unchanged) |
   Only itaa-1997 has corpus-comp PDFs. All other acts' staging PDFs are ONE
   comp newer than the corpus — do NOT rebuild from them blindly or the law
   text can regress/advance (fbt 96→97, itaa36 191→192, taa 222→225 are real
   comp jumps). Per flagged section: diff section prose between corpus file
   and the newer comp's text; only if prose is identical AND the table region
   text is identical may the newer PDF be used; otherwise fall back to the
   layout slicer on the repo raw (comp matches corpus).
3. Extend/extract tool with a **fidelity gate**: for every rebuilt table,
   compare reconstructed cell text against the PDF page's own text layer
   (normalised whitespace/punctuation, allow link-marker `*...*` stripping and
   smartquote normalisation). Reject + record any table where coverage < 98%
   or where reconstructed words are absent from the source page.
   Calibrate against a KNOWN-GOOD table first (clean section should score
   ≥99.5%); if the gate falsely rejects >2% of known-good cells, relax the
   threshold or extend normalisation (asterisked-term italics, smart quotes,
   [links](url) vs raw text — Kimi R7).
4. **Fix the extractor's known defects BEFORE scaling (Kimi R3-R6, R10; same
   defects found by main-agent read):**
   - R4/page-break continuation: `collect_tables()` merge (line ~312) only
     joins blocks with identical headers; a row that begins on page P and
     continues on P+1 is truncated. Detect same item number as last row of
     block N / first row of block N+1 and REJOIN cell text — single biggest
     truncation cause.
   - R5/55pt row cap: `build_rows()` caps last row at item_y+55pt (line
     ~223). Legal rows run 6-8 lines (~80pt+). Make the cap adaptive from
     actual word positions (next block start / next header), not static.
   - R6/asterisk footnote: `is_footer_word()` y≥600 drops the "*To find
     definitions of asterisked terms…" line when it sits in a table's
     vertical flow — treat that line as table metadata, keep it out of cells
     but don't lose it.
   - R3/generalise: `table_blocks()` keys off a capitalised 'Item' first word
     (line ~97). GST/FBT/SIS tables use other header shapes (column-letter
     tables, no-Item tables, roman-numeral identifiers). Parameterise or add
     act-specific block/header detection; smoke-test ONE flagged file per act
     in Phase 0.
   - R10/performance: call `collect_tables()` in-process (library import)
     instead of subprocess-per-file for 240+ rebuilds.
5. Extend `validate_md()` (or a new wrapper) with content checks:
   - no mid-word split signatures (run `scan_table_coherence` on the rebuilt
     file → 0 C11 hits),
   - no glyph chars,
   - row text present in source page (fidelity above).
5. Smoke-test on 3 known-bad sections (115-30, 109-55, FBT 135W): rebuild,
   verify fidelity gate passes AND rendered HTML looks right.
   For txt-only acts, smoke-test the txt-layout slicer (extend
   `repair_itaa_tables.py` column-slice approach to general headers) on a
   known-bad GST + SIS section.

### Phase 1 — rebuild itaa-1997 (largest, 416 findings)

Priority order within act: divisions with the most flags first (43-*, 40-*,
109-115, 296-* etc — derive exact ranking from C11 JSON).

For each flagged file:
1. Locate section pages in the right compilation volume.
2. Rebuild all tables in the file from PDF word positions with proper cell
   reflow + row continuation across page breaks (fix the extractor's known
   gaps rather than hand-editing).
3. Run fidelity gate + C11 rescan on the rebuilt file. 0 C11 + gate pass =
   done; else keep the file on the reject list with the diff.
4. Human/agent spot-read of a sample (Harry's rule: blind 0.0% is not done).

### Phase 2 — rebuild remaining acts

Same procedure for taa-1953, gst-1999, fbt-1986, itaa-1936, sis-1993 (each
act-gated; stop and review after every act).

### Phase 3 — regression verification (per act, per rebuild batch)

1. `python3 scripts/verify_data_integrity.py --domain all` — PASS.
2. C11 content phase re-run: flagged files for the act → 0.
3. API read-back: `GET /api/section/<act>/<sec>` returns the rebuilt table
   (curl a sample, confirm cell text is present and unbroken).
4. Service restart before final verification (files are read live, but the
   running process caches act lists).

### Phase 4 — commit + ticket close

- Logical commits per act: `fix(data): rebuild <act> tables from compilation
  PDFs (C11 table-coherence class)` — corpus changes only, scripts committed
  separately if modified.
- After all acts: run the full `final_data_audit.py` (NEW random seed) —
  C11 must be the only reduced class; verdict PASS.
- Close CDN tickets for the table class (CDN-0186/0187 + any auto-synced C11
  ticket) with `note || '; Fixed 2026-09-07 (raw-PDF table rebuild)'`.
- Update `BUGS_NEXT_TIME.md` / patch owning skills if procedure changed.

## Gates / abort conditions

- Any act whose fidelity gate rejects >5% of files → STOP, review extractor,
  do not proceed to next act.
- Do NOT commit a file whose C11 rescan still flags it.
- Do NOT run over uncommitted WIP — repo is clean at 79a649408 except
  approved commits; re-check `git status` before Phase 1.
- Rebuild scripts run with python3.12 + fitz (venv/interp as per existing
  apply script). Never use python3 (3.11) for fitz code.

## Risks / mitigations

- **Extractor gaps on complex tables** (multi-level headers, merged cells,
  formulas): formulas (FBT 9, 135W) may need manual reconstruction from raw —
  keep a manual-fix list, do NOT auto-apply questionable rebuilds.
- **Volume mapping drift**: frontmatter `source_pdf` may be stale (comp 263
  vs 266 era). Verify section presence in the PDF page set before trusting
  extraction; prefer the compilation volume matching frontmatter
  `compilation_no` and fall back to searching all vols of the act.
- **Size**: ~240 files. Parallelise with subagents per division, main agent
  owns gates/commits. Subagent fixes are READ-ONLY-plan + execute + verify per
  the mandated chain; do not let subagents commit.
- **Renderer-side**: verify at least one table per act in a real browser
  (markdown table renders with correct columns), not just file-level checks.

## Scope measured 2026-09-12 (nightly bug-squash run) — CDN-0193

The randomised corpus audit (seed 39878977) opened **CDN-0193 = this plan's
`C11_table_truncated` signature**. Live C11 rescan on 2026-09-12:
**152 glyph / 115 midword / 504 truncated = 771 findings**, i.e. the truncated
class is the largest single remaining data-loss class in the corpus.

`scripts/scan_truncation_scope.py` (new, committed with this addendum) probes
each truncated finding's offending cell tail in the act's repo raw text and
splits it by *where the lost text can be recovered from*:

| act       | truncated findings | tail continues in repo raw | split at PDF page boundary | tail not located | repo raw comp | corpus comp | staging source present |
|-----------|--------------------|----------------------------|----------------------------|------------------|---------------|-------------|------------------------|
| itaa-1997 | 340                | 238                        | 71                         | 31               | **263 (STALE)** | 266       | comp266 vol01-12 PDFs ✓ |
| taa-1953  | 68                 | 39                         | 19                         | 10               | 222 ✓         | 222         | comp225 vol01-04 PDFs  |
| sis-1993  | 29                 | 14                         | 12                         | 3                | 126 ✓         | 126         | part1-2 PDFs ✓         |
| itaa-1936 | 25                 | 13                         | 8                          | 4                | 191 ✓         | 191         | comp192 vol01-07 PDFs  |
| gst-1999  | 21                 | 16                         | 5                          | 0                | 96 ✓          | 96          | (repo raw txt only)    |
| fbt-1986  | 21                 | 18                         | 2                          | 1                | 96 ✓          | 96          | part1-2 PDFs ✓         |
| **total** | **504**            | **338**                    | **117**                    | **49**           |               |             |                        |

Read this table as *text availability*, not as a licence to patch from raw:

- "tail continues in repo raw" (338) means the lost cell text exists in the
  repo's own extraction text — no new download needed for those *acts whose raw
  matches the corpus compilation*. For itaa-1997 the repo raw is the STALE
  comp 263 while the corpus is comp 266 (the 238-column above), so itaa-1997
  must still be rebuilt from the staging comp266 PDFs as this plan requires.
- "split at PDF page boundary" (117) needs the source PDF / next page join —
  exactly the extractor defect R4/§Phase0.4 (row continuation across page
  breaks), plus R5 (row cap). This is the single biggest truncation cause, as
  this plan predicted.
- "tail not located" (49) is a probe artefact or in-file scramble (the
  multi-column band interleave, e.g. `itaa-1936/schedule-2f/266-10`,
  `itaa-1997/30-15`, `sis-1993/part-1/6`), not a detector false positive: every
  sampled finding is genuinely cut mid-clause. No detector-tightening fix is
  available for this class (unlike CDN-0191's accent-fold exemption).

Execution gate status as of 2026-09-12: **not satisfied** — no opus/codex review
artefacts for this plan exist in the repo, and the repo's own history shows an
earlier cron attempt at this class was lossy and had to be reverted
(§Evidence, 2026-09-07). Held for Harry's sign-off; do not execute piecemeal.

## Out of scope (this pass)

- NZ IT 2007 (0 flags), OECD/treaties/proposed-law (not flagged).
- `spec` fixture tables (clean; detector has 0 hits there).
- Non-table truncation classes (CDN-0182 30-212 etc) — separate tickets.
