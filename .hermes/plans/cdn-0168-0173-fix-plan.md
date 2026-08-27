# Corpus Error-Class Fix Plan — CDN-0168 through CDN-0173

Source: corpus-wide scan 2026-08-26 (script /tmp/corpus_class_scan.py) mapping every
previously-fixed bug class in the issue register (~140 tickets) to full-corpus checks.
6 new bug classes confirmed and filed. This plan fixes all of them.

## Priority & effort
| Ticket | Class | Scope | Effort | Risk |
|---|---|---|---|---|
| CDN-0168 | compilation_no type | 5 files | S (5-line) | none |
| CDN-0169 | "the the" fragments | 7 files | S | none |
| CDN-0171 | broken bold-italic | 35 files | S | none |
| CDN-0172 | phantom definition anchors | 9 terms | M | low |
| CDN-0170 | word duplication | 245 in 174 files | M | low-med (repair script) |
| CDN-0173 | tree-title vs H1 mismatch | 35 files (NZ 30) | L | med (NZ tree restructure) |

## 1. CDN-0168 — compilation_no type + missing dates
Root cause:
- `pipeline/build_cch_explorer.py:21-23` — CCH guide metas hardcode `"compilation_no": "1"/"2"` as **str**.
- `scripts/ingest_corps_act.py` writes `compilation_no: 0` (int) but no compilation_date.
- `data/spec/tree.json` — legacy artifact, no date.

Fix:
- build_cch_explorer.py: change meta dict values `"1"→1`, `"2"→2` (int).
- ingest_corps_act.py: add `compilation_date` (the Corporations Act consolidation date 2024-07-01... verify).
- spec/tree.json: add date or leave — spec is an internal scratch act; verify with Harry before touching.

Gate: `compilation_no` is int for all 14 acts; every act has a non-empty compilation_date (except spec, documented).

## 2. CDN-0169 — "the the" fragments (7 files)
Files: corps 766C, itaa-1997 165-13, itaa-1997 709-215, itaa-1936 266-10,
master-tax-guide franking-debits, master-tax-guide overview-of-the-cgt-events,
master-gst-guide calculating-wet-and-taxable-value.

Fix: targeted `the the → the` replacement in exactly these 7 files (context-verified,
not global regex — legal English legitimately contains "the the" in rare cross-line
cases; each instance verified individually).

## 3. CDN-0171 — broken bold-italic (35 files)
Pattern: `**...*...**` with exactly one inner `*` (unclosed italic inside bold),
e.g. `**would exceed its *market value**` (itaa-1997 40-180).
itAA-1997 ×19, master-tax-examples ×7, master-tax-guide ×6, gst ×2, taa-1953 ×1.

Fix: script that finds `\*\*[^*\n]*\*[^*\n]*\*\*` and repairs the inner `*` to
`**` (bold-in-bold) OR drops the stray asterisk — decision per instance: if the
inner `*word` is a known defined-term marker (preceded by `*` = italics term),
convert `**...*X...**` → `**...*X*...**` (close the italic). Verify each against
the section's actual defined terms. Fallback for ambiguous: drop the stray `*`.

## 4. CDN-0172 — phantom definition anchors (9 terms)
Root cause: `pipeline/extract_definitions.py` `_capture_terms` — the colon-style
term capture `TRAILING_PREDICATE_RE` strips trailing predicates but list-style
definitions like "…and" / "…of" (enumerated definitions: "in this Act: (a) X means …; (b) Y means …")
are captured mid-list as full terms. 8 of 9 flagged terms have anchors that do NOT
exist in the section files (verified).

Fix:
- extract_definitions.py: extend term validation — reject captured terms ending in
  `and|of|the|or` when the definition block is a list-style `(a)(b)(c)` block
  (terms must be single items, not list continuations); add an anchor-existence
  post-check (`make_anchor` must resolve in the section body).
- Re-run extract_definitions.py for the 3 affected acts (itaa-1997, itaa-1936, gst-1999)
  → rebuild definitions_all.json → re-run graph ETL (defines edges) if counts change.

Gate: 0 terms with `(and|of|the|or)$` ending; every anchor resolves to `id="..."` in
its section file.

## 5. CDN-0170 — word duplication (245 in 174 files)
Root cause: PDF extraction artifacts — "property property", "income income",
"year year", "exempt exempt", "test test" etc. Legit legal English ("had had",
"that that") must NOT be touched.

Fix:
- Repair script `/tmp/dup_repair.py`: per file, find `\b(\w{3,})\s+\1\b` (case-insensitive),
  drop duplicates ONLY when the word is in the artifact list (property, income, year,
  test, exempt, payment, company, entity, subdivision, regulations, nil, duty, gst,
  asic, dividends, interest, amount, entities, land, trusts, credits, lease, shares,
  professional, expenditure, been, distribution, purposes, employees, trustee,
  division, circumstances, day, base, child, tax, disabilities, accounts, number,
  taxation, recommendations, member...), plus context check (not preceded by "had "/"that ").
- Review every remaining hit manually (245 is manageable).
- After repair: rebuild nothing (sections are markdown content; served from disk).

Gate: 0 artifact-word duplications remain; 0 false positives on "had had"/"that that".

## 6. CDN-0173 — tree-title vs H1 mismatch (35 files)
Two sub-causes:
a) **NZ IT 2007 tree restructure (LARGE)** — `data/nz-it-2007/tree.json` mixes two
   structures: parts 1–3B are amendment-history ("Part 1 Business tax measures",
   "Section EW 59 replaced") while parts A–Z are the real act. 30 of 35 mismatches
   come from part 1 titles. The tree.json was built Jul 26 from the wrong source
   structure (amendment history, not consolidated act).
   Fix: rebuild nz-it-2007 tree from the consolidated act structure — re-run the
   NZ ingestion (pipeline/parse_nz_it.py) against the correct consolidated source
   OR restructure the existing tree.json parts 1–3B to map onto the real act parts.
   Verify against legislation.govt.nz. — **FLAG: needs Harry's sign-off on scope**
   (rebuilding NZ may drop the amendment-history parts entirely).
b) **Individual title fixes** — itaa-1997 2-10 (tree title wrong: "Capital
   allowances..." vs H1 "When defined terms are identified"), itaa-1936 266-10
   (H1 is garbage table content — file-level fix), aml-ctf-2006 s1 ("Alternative
   constitutional basis" vs "Short title" — verify which is right).

## Execution order (dependencies)
1. CDN-0168 (5 min, zero risk) — touch build_cch_explorer.py + ingest_corps_act.py
2. CDN-0169 (5 min) — 7 targeted replacements
3. CDN-0171 (15 min) — repair script + per-instance review of 35
4. CDN-0172 (30 min) — extractor validation fix + re-run for 3 acts + graph ETL
5. CDN-0170 (45 min) — repair script + manual review of 245
6. CDN-0173b (15 min) — 4-5 individual title fixes (skip NZ restructure without sign-off)
   CDN-0173a (NZ) — **DEFERRED pending Harry decision** (LARGE, rebuild scope)

## Verification
- verify_data_integrity.py --domain all (must stay PASS)
- Re-run /tmp/corpus_class_scan.py — CDN-0168/0169/0170/0171/0172 classes → 0 findings
- CDN-0173b: re-run normalized title-vs-H1 comparison → 0 mismatches (excl NZ parts 1-3B)
- Spot-check 10 repaired files render correctly in browser
- If definitions_all.json changed: rebuild search index + graph ETL + restart service

## Not in scope
- CDN-0099 (autocomplete — product), CDN-0124 (chapeau, verified clean), NZ restructure (CDN-0173a)
