## 2.8.1 — 15 Aug 2026

- **Legislation table rendering** — pipe-table detection + GFM rendering added to all tax act parsers (`parse_itaa97.py`, `parse_itaa36.py`, `parse_taa53.py`, `parse_gst1999.py`). Tables now render instead of collapsing to run-on text. Threshold: 3+ columns, 2+ wide gaps.
- **Treaty tree** — treaty navigation tree now expandable to article level with article numbers and titles.
- **ITAA 1936 re-parse** — fixed `RE_PART` regex to recognise suffix-letter parts (VA, VIIB, IIIB, IVA). Re-generated `tree.json`: 13 parts, 993 sections (up from 771), schedule sections (Schedules 2D/2F/2H) now included in navigation tree. 25 sections with tables. 0 orphans.
- **TAA 1953 re-parse** — 1,243 clean sections, 56 with tables. Deleted 1,120 stale duplicate files. Tree ↔ disk 1:1.
- **GST 1999 re-parse** — 827 sections, 55 with tables. 4 stale orphans removed. Tree ↔ disk 1:1.
- **Parser guards** — section-detection guards added to `parse_itaa36.py`, `parse_taa53.py`, `parse_itaa36_schedules.py`: skip wide-gap table rows and trailing-colon TOC labels from being misclassified as section headers.
- **Server restart** — backend restarted after data changes.

## 2.8 — 2 Aug 2026

- Treaty data type added with full navigation tree.
- GST compilation footer fix (s 228).
- Deploy loop fix: don't restart when local ahead of origin.
- Display spec document + spec-list data type.
- Audit: all 11 data types checked against display spec; 10 deviations logged.
- Audit batch fixes: s-prefix URLs, treaty slugs, Defined Terms grouping.
- Social Post Composer: frontend + backend.
- Corps Act, AML/CTF, regulatory guides bulk update. Pipeline fixes.

## 2.7.3 — 1 Aug 2026

- **B23: report_issue fixed** — dedup now includes `note` in param_hash hashing (was hashing tool+params only, causing all tool reports with no params to collide). Ticket allocation now insert-first (concurrency-safe via auto-increment id on INSERT, not pre-computed MAX(id)+1). Test noise tickets (CDN-0017–CDN-0037) cleaned.
- **B1/B2: get_section payload capped** — `max_body_length` parameter (default 50K chars), `include_commentary` (default false, returns snippet+locator only). s 995-1 returns truncated preview with note to use `get_definition`.
- **B3: get_definition boundary bleeding** — hard length cap of 5000 chars after text extraction.
- **B4: 2-digit year rulings** — `TR 97/7` → `TR 1997/7` normalizer added.
- **B5: search_cases ranking** — relevance scoring: exact name/citation matches ranked first, then all-words-in-name, then partial matches.
- **B6: case_legislation_refs act attribution** — `_fix_itaa1936_act_titles()` shared helper extracted from `get_case_metadata()`; both `get_case` and `case_legislation_refs` use it.
- **B7: s 269-15(2A) truncation** — RE_NOISE extended to strip indented `*For definition…` footnote lines.
- **B8: 1936 section dedup** — 1936-act heuristic extended beyond the 109-series; de-dupes so one ref isn't emitted under two acts.
- **B11: ATO-ID legislation_referenced** — `_KNOWN_ACT_RE` regex rejects sentence fragments as act titles; dedup by `(act, section)`.
- **B12: insolvency_get_chapter pagination** — `offset`/`limit` params added, content sliced by lines.
- **New tool: resolve_alias** — resolves "Div 7A", "s 100A", "Part IVA", "Subdiv 115-C", "109Y", "8-1", etc. to act + section number with URL.
- **New tool: list_issues** — lists issues with status, patch notes (`fixed` field), and filters (status, tool, limit, max 200).
- **CDN-0002: resolve_alias** — section alias tool added.
- **CDN-0009: paragraph backfill** — pipeline for cases with content but no paragraphs.
- **CDN-0010/0016: decision_date backfill** — 187 case names fixed, hundreds of dates backfilled from summary data.
- **CDN-0011: search_cases** — relevance ranking boost for summary fields over party-name matches.
- **CDN-0012: quoted-phrase search** — `"distributable surplus"` now does exact LIKE match bypassing FTS5 stemming.
- **CDN-0013: self-citation cleanup** — self-references filtered, AustLII chrome stripped, court-code validation.
- **CDN-0015: case_name truncation** — 187 truncated case names backfilled from summary data.
- **CDN-0044: cases_cited names** — resolution path from cases table.
- **API: `/api/issues` now returns `fixed` field** — shows per-issue patch notes for resolved bugs.