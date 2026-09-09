# All-Open-Bugs Fix Plan (2026-09-05)

> **For Hermes:** delegate to Claude Code for assessment before implementation per Harry's gate; then implement in the order below.

**Goal:** Close every open bug in the legislation-explorer queue: CDN-0182, 0183, 0184, 0185, 0186, 0187 (fixable now), CDN-0124/0173 (LARGE, need sign-off + source), CDN-0099 (product decision).

**Architecture:** Three root-cause clusters cover 6 of 9 tickets:
1. **Table page-split corruption** (CDN-0186, CDN-0187) — same class CDN-0171 fixed, using the proven extractor/apply driver.
2. **Legislation-ref extraction act-scoping + hyphen truncation** (CDN-0184, CDN-0185) — one re-extraction fixes both.
3. **Citation normaliser gaps** (CDN-0183) — small code fix + alias data.
4. **Isolated data contamination** (CDN-0182) — one-line data strip.

**Tech stack:** Python 3.11, PyMuPDF extractor (`scripts/extract_itaa_tables_pdf.py`), apply driver (`scripts/apply_itaa_table_fixes.py`), backend FastMCP server (`backend/fastmcp_server.py`), PostgreSQL `cadena_knowledge`.

---

## Cluster A — Table page-split corruption (CDN-0186, CDN-0187)

**Context:** Both URLs (itaa-1997/115-30, itaa-1997/109-55) are the same class CDN-0171 fixed on 13 sections: tables split across PDF pages with duplicate intro headings, column bleed, blockquote fragments, missing/duplicate rows. The original 13-section scope missed these two.

- **115-30.md**: 5 duplicate "When the acquirer is treated as having acquired a CGT asset" headings (lines 22/34/58/84), row 9 columns interleaved at lines 64-71, row 8 appears **missing** from the file entirely, row 9A's (a)/(b) split as blockquotes below, fragment "**trust involved in the first**" at line 73.
- **109-55.md**: rows 11A/11B corrupted (row 11B's item cell contains "interest" bleed, "(b) a connected entity of the **issuer of the exchangeable**" fragment at line 49), duplicate table headers at lines 54/63, item 12 missing.

**Fix:** These sections sit in vol03 (source_pdf field confirms). Run the extractor on both, then apply. The existing extractor handles exactly this class.

### Task A1: Extract both tables from vol03

Run: `python3 scripts/extract_itaa_tables_pdf.py --section 115-30 --section 109-55` (verify CLI flags first — the script currently takes pages/volumes; may need a section-arg path like the driver's `--only`).

Files:
- Modify: `scripts/extract_itaa_tables_pdf.py` (only if a section-name entrypoint is missing)

### Task A2: Dry-run apply, review output, then apply

Run: `python3 scripts/apply_itaa_table_fixes.py --only 115-30,109-55 --dry-run`
Expected: WOULD replace 1 table each (or 2 for 109-55's two real tables).
Then apply for real after reviewing the generated clean tables row-by-row against the PDF.

Files:
- Modify: `data/itaa-1997/sections/part-3-1/division-115/115-30.md`
- Modify: `data/itaa-1997/sections/part-3-1/division-109/109-55.md`

### Task A3: Verify

- Broken-bold fragment scan returns 0 for both files.
- Row counts match the PDF (115-30 should have items 1-10 incl. missing 8; 109-55 items 1-17 incl. 11A/11B — confirm against vol03 what item 12's content actually is; it may be genuinely absent like 40-300's item 12).
- Frontmatter intact; single clean table per table-family.
- Render check via the live site or backend section API.

---

## Cluster B — Legislation-ref extraction (CDN-0184 + CDN-0185)

**Context:** Confirmed by DB evidence (2026-09-05 run):
- `[2012] FCAFC 177` paragraphs store "Section 105-50(3)" as `s.105` (hyphen truncation), act attribution double-counts (4 rows for 2 refs: TAA s.75 + GST s.75 + TAA s.38 + GST s.38), Bankruptcy Act refs attributed to GST/TAA, Schedule 1 TAA refs default to ITAA 1997.
- Root cause: 2026-02-18 ingest regex (older than `scripts/backfill_legislation_refs.py`, which has the corrected hyphen-aware pattern) + naive act-scoping: any para naming GST+TAA gets every section ref × every mentioned act; paras naming no act default to ITAA.
- CDN-0184 (gst s 105-5 vs TAA Sch 1 s 105-5 collision) is a downstream symptom of the same defect — no separate code path.

**Fix:** Re-extract contaminated rows with the corrected hyphen-aware regex + proper act-scoping (Schedule 1 context → TAA 1953 Sch 1; act attribution only for acts actually named or unambiguous).

### Task B1: Scope the contamination

Query DB for `case_legislation_refs` rows whose context contains "Section N-" but stored ref is `s.<int>` (hyphen truncated); count them. Confirm the ingestion date/version that created them so the fix targets only that batch.

### Task B2: Write scoped re-extraction script

Create: `scripts/re_extract_legislation_refs.py`
- For each contaminated case paragraph: re-run extraction with the hyphen-aware pattern from `backfill_legislation_refs.py`.
- Act-scoping rules: (a) act named in the para → that act only; (b) "Schedule 1 ... Administration Act" / TAA Sch 1 context → TAA 1953 Sch 1; (c) no act named → ITAA 1997 only when section range matches ITAA numbering, else NULL/unknown rather than wrong default; (d) never multiply refs by the number of acts mentioned.
- Delete replaced rows, insert corrected ones in one transaction.

### Task B3: Verify

- `[2012] FCAFC 177` para 19: exactly 2 refs (not 4), correct acts. Para 26: Bankruptcy Act ref correctly attributed or dropped (Bankruptcy Act isn't scoped — decide: keep with act label "Bankruptcy Act 1966" or drop; recommend keep-with-label since corpus includes it).
- Para 82: TAA Sch 1 s 105-50(1), not ITAA.
- gst s 105-5 / TAA Sch 1 s 105-5 no longer collide: each ref carries explicit act scope.
- Run the case-section linkage check that originally filed CDN-0184: no cross-act collisions.

---

## Cluster C — Citation normaliser gaps (CDN-0183)

**Context:** `[2009] ATC 1-016` (Case 12/2009) fails resolution:
- `_normalise_case_citation` regex number group is `\d+` — can't parse report-series "1-016".
- AATA corpus (3,456 records) has zero ATC-series citations — no alias to resolve against.
- Target case exists as `[2009] AATA 805` (YXFP and Commissioner of Taxation). Master Tax Guide confirms Case 12/2009 / 2009 ATC ¶1-016 / [2009] AATA 805 are the same case.

**Fix:** Build a small ATC↔medium-neutral alias map + extend the normaliser.

### Task C1: Extend `_normalise_case_citation`

Modify: `backend/fastmcp_server.py` (find exact function location)
- Accept report-series numbers: `[YYYY] ATC N-NNN` (allow the dash in the number group for ATC/FCAFC/NSWLR-style report citations).
- Add an alias lookup step: `[YYYY] ATC n-nnn` → canonical medium-neutral citation via a small JSON map.

### Task C2: Build the ATC alias map

Create: `data/atc_alias_map.json` — start with Case 12/2009 → `[2009] AATA 805`; extend only with verified pairs (master-tax-guide / AATA decisions confirmed same case). Do NOT mass-generate from ATC series numbers (risk of false joins — verify each).

### Task C3: Verify

- `get_case("[2009] ATC 1-016")` returns the YXFP case (via AATA 805).
- Existing citations unaffected (regression: run the normaliser over the fcafc corpus list — all still resolve).
- py_compile + relevant backend tests.

---

## Cluster D — Isolated data contamination (CDN-0182)

**Context:** Truncation flag fires on itaa-1997 s 30-212 because the .md body has trailing contamination: "Working out the amount you can deduct for a gift of property" is the running-head/title of the NEXT section (30-215), not s 30-212 content. Raw `vol01.txt:17200` confirms s 30-212 ends at "...regulations for making the valuation." The 50,000-char cap is NOT implicated. Siblings 30-205/30-215 verified clean — isolated.

### Task D1: Strip the contamination

Modify: `data/itaa-1997/sections/part-2-5/division-30/30-212.md`
- Remove the trailing " Working out the amount you can deduct for a gift of property" from the end of subsection (2).
- Also scan the rest of the file for any other running-head bleed (verify the full body, not just the tail).

### Task D2: Verify

- `get_section` truncation flag stops firing for 30-212.
- Content matches vol01.txt:17200 source exactly.
- Re-run the truncation scan: no other sections fire the flag spuriously (confirm the 30-212 case was the only contamination-driven flag; if others fire, treat as Cluster D-widespread).

---

## LARGE / decision tickets (flag to Harry, no execution without sign-off)

### CDN-0173 — NZ IT 2007 tree/corpus rebuild (LARGE)
30 amendment-history-title sections + 415 structural sections carry titles like "Section CG 4 replaced" instead of consolidated titles ("What is a transfer of value?"). Tree untouched since Jul 26; corpus part-1 files carry the same bad titles. Fix = rebuild NZ tree + corpus from consolidated source. Needs Harry sign-off + consolidated source location. **No repo source for the consolidated act — confirm whether the NZ IT 2007 consolidated PDF is available or must be sourced.**

### CDN-0124 — Corps Act chapeau re-ingest (LARGE/BLOCKED)
313 corps sections missing the chapeau line (s259A verified). No source PDF in repo. Needs FRL corps PDF re-download + chapeau-preserving re-ingest. **Ask Harry whether to source the FRL PDF now or keep parked.**

### CDN-0099 — search autocomplete (product decision)
Half-shipped: /search page exists with advanced filters. Live-typing autocomplete deliberately disabled (commit 7066299a5). Re-enabling is a product call. **Ask Harry: enable typeahead dropdown, or leave as-is?**

---

## Execution order (per Harry's delegation gate)

1. **Claude Code assessment** of this plan (opus) before any implementation.
2. Smallest first: D (30-212 strip) → C (citation normaliser) → B (re-extraction) → A (tables).
3. Flag LARGE/decision items to Harry in the same report.

## Risks / open questions

- **115-30 item 8 / 109-55 item 12 missing**: may be genuinely absent from source PDF (like 40-300 item 12) — verify against vol03 before assuming data loss.
- **B act-scoping edge cases**: paras naming multiple acts with section refs that genuinely appear in more than one (e.g. s 105-5 exists in both GST and TAA Sch 1) need a disambiguation rule — context proximity wins, else NULL.
- **ATC alias map**: must not mass-generate; only verified case pairs.
- **CDN-0185 re-extraction write**: transaction-scoped, delete-then-insert per case, verify `MAX(id)` behavior and no partial writes.
- No commits (repo's uncommitted workflow); backups before data-file applies.

## Files likely to change

- `data/itaa-1997/sections/part-3-1/division-115/115-30.md` (A)
- `data/itaa-1997/sections/part-3-1/division-109/109-55.md` (A)
- `scripts/apply_itaa_table_fixes.py` (A — only if --only needs extension)
- `data/itaa-1997/sections/part-2-5/division-30/30-212.md` (D)
- `scripts/re_extract_legislation_refs.py` (B, new)
- `backend/fastmcp_server.py` (C)
- `data/atc_alias_map.json` (C, new)
- DB `case_legislation_refs` rows (B)
