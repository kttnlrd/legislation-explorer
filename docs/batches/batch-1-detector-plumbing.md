# Batch 1 — detector plumbing (S3, S5, X1, X2, C17-C27)

Executor log. Packet: `docs/bug-plan-2026-09-25.md` batch 1 of the recommended order — pure
detector/test plumbing, no data writes, no ingester, no service restart. Branch `master` from
`495954727`. Python `/usr/bin/python3.12`.

## Fix sites and commits

| Commit | Fix site | Files |
|---|---|---|
| `7d4bca03c` | S5 — C11 per-line first-match-wins | `scripts/scan_corpus_error_classes.py`, `scripts/test_c11_table_coherence.py` |
| `bf0619a7e` | S3 + C17-C27 — one shared `DETECTORS` list, new detectors | `scan_corpus_error_classes.py`, `randomised_api_mcp_test.py`, `final_data_audit.py`, C15 rename, 9 new/extended tests |
| `e319ef30f` | X1 — pre-commit hook untracked trigger | `scripts/pre_commit_corpus_guard.sh`, `scripts/test_corpus_change_guard.py` |
| `596c915ad` | X2 — repair-script provenance + rollback tag | `scripts/fix_page_rule_artifacts.py`, `scripts/test_page_rule_provenance.py` |

No data under `data/**` was written. No rollback tag was needed for the batch itself (the only
tag created is inside the X2 smoke test's throwaway repo). The three files that were already
dirty at `495954727` (`backend/fastmcp_server.py`, `data/quotes.json`,
`scripts/build_definitions_index.py`) are untouched and uncommitted; they belong to later
batches.

## The check that failed first (gate 3)

Every new check was shown failing against the pre-fix state before the fix landed.

* **S5** — `test_c11_table_coherence.py` against the HEAD scanner: the planted row (glyph +
  trailing connector + mid-word split) emits ONE class, and 4 of 10 assertions fail. With the
  change it emits all three and passes.
* **X1** — `test_7` against the HEAD hook: `commit exit 0 (want non-zero)`; the bad-shape
  untracked section file sails through. With the change: `commit exit 1` and the control
  commit after deleting the file still exits 0.
* **X2** — the smoke test fails at HEAD (the script writes `/tmp/cdn203-apply.json` and creates
  no tag); after the change it passes all 12 checks.
* **C17-C27** — the fail-first state is the detector FIRING on the live corpus, measured below.
  Each self-test is a pinned pair (one planted positive, one planted negative) so a later
  correction cannot mute a class quietly.

## Measured counts at HEAD (gate 3/5)

`/usr/bin/python3.12 scripts/scan_corpus_error_classes.py` — exit 0, **446 findings before,
6,862 after**. Structural classes add one finding per row; the character classes aggregate with
a `count` key (so `C22_ligature` is 3,320 findings standing for 22,212 characters).

| Class | Measured | Plan | Note |
|---|---|---|---|
| C11_table_glyph | 111 | — | unchanged |
| C11_table_midword | **106** (was 78) | 106 true incidence | S5 unmasking |
| C11_table_truncated | **80** (was 78) | +4 predicted | 2 of the 4 rows also unmask a header_split |
| C11_table_header_split | 46 (was 42) | — | rows the glyph check hid |
| C11_table_rowwrap | 20 (was 18) | — | rows the glyph check hid |
| C15_drawing_char | 22 | 22 in 11 itaa-1997 files | now in the nightly (S3) |
| C17_missing_chapeau | 313 | 313 | all in corporations-act-2001; 0 in itaa-1997/1936/gst |
| C18_nz_amendment_part | 445 | 445 | parts 1/2/3/3B = 374/40/8/23 |
| C19_ruling_title_fragment | 26 | 273 → ≤26 | already at target: the 0204 extractor landed in `3b715b745` |
| C20_non_latin_script | 4,128 chars | 1,370 тАв (4,110 chars) | 897 JSON fields: MTG tree 22, section_index 875 — 4,110 of the 4,128 chars are those 'тАв' triplets; + 9 Greek Σ in nz formula lines, 5 rulings, 2 maps, 2 derived summaries |
| C21_html_entity | 193 chars | 52+ | 52 in 50 `scripts/cleaned/summaries` files (the FTS source), 132 ruling summaries, 9 maps |
| C22_ligature | 22,212 chars | 21,000+ | MTG 18,688 in 1,315 files (exact), Keays 3,107 in 21 (exact), MTG section_index 404, maps 13 |
| C23_invisible_char | 1,947 | 1,947 | all U+FEFF, 714 nz-it-2007 files |
| C23_nonstandard_hyphen | 3,392 | 3,034 + 256 | corps 3,290 exact, + 91 in derived case summaries (plan says 90), 11 elsewhere |
| C23_soft_hyphen | 36 | 35 | 35 in rulings (22 summaries + 13 CR text) + 1 regulatory guide |
| C24_glued_heading | 176 | 176 | 89 aml-ctf-2006 files |
| C25_dot_leader_endnote | 4 rows in 3 files | "the 3 files" | gst 195-1:2483, sis 381:772/775, fbt 167:809 |
| C25_toc_leak | 139 rows in 1 file | OECD c31-32 | |
| C26_pua_glyph | 1,969 chars | 46 + 1,919 | 50 in sections, 1,919 in 63 regulatory guides |
| C27_unregistered_section | 23 | 23 | all master-tax-examples twins; no orphan in any other act |

### Two plan rules corrected to match the plan's own expectation

* **C25** — "5+ dots in a line longer than 2,000 characters, or after an Endnote heading" fires
  18 times in 11 files, and 15 of those are the legitimate population the same plan says must
  not fire (itAA-1997 Div 10/11/12 checklists, master-GST-guide checklists and glossary, MTG rate
  layouts — all one long flattened line). The test is now endnote CONTEXT (amendment-history
  wording in the line, or an Endnote heading / amendment wording within the 5 lines above), which
  lands on exactly the 3 files named. Negatives planted: `child care subsidy ...... 52-150` and a
  long flattened index row (12-5's shape).
* **C18** — the tree part id is the discriminator. 87 section titles also match the
  amendment-history shape and all 87 sit inside the four non-letter parts, so the title clause
  adds nothing at HEAD; it is kept for a future re-parse.
* **Character-class file list** — `maps/` was reached twice (as a top-level directory, and via
  the extras list), so every character in it was counted twice. Deduped in the follow-up commit,
  which is where the C20/C21/C22 numbers above come from; the first run reported C20 4,130, C21
  202, C22 22,225. `data/maps` is 13 ligatures and 9 entities, not 26 and 18.

## Verification run (gate 5 evidence for the master)

```
/usr/bin/python3.12 scripts/scan_corpus_error_classes.py            exit 0, 6,862 findings
for t in scripts/test_c[0-9]*_*.py; do $t; done                     13/13 PASS
  (c4, c6, c11, c14, c15, c16, c17, c18, c19, c20, c24, c25, c27)
/usr/bin/python3.12 scripts/test_corpus_change_guard.py             OK, 8 tests
/usr/bin/python3.12 scripts/test_page_rule_provenance.py            PASS, 11 checks
/usr/bin/python3.12 scripts/test_page_rule_fix.py                   PASS
phase 4 glob scripts/test_c[0-9]*_*.py                              4 files before, 13 after
  (C15's test renamed test_scan_drawing_chars.py -> test_c15_drawing_chars.py)
git ls-files --others --exclude-standard -- data                    0 files
```

Phase 4 of `final_data_audit.py` now also reports emitted classes that have no self-test. Run
against a real phase-2 sample the list is **C5_fragment_inline, C12_missing_heading** — reported,
not fatal, as the plan specifies; it becomes an assertion when the list is empty.

Not run: the full `final_data_audit.py` (it needs the API on :8765 and Postgres and syncs
findings into the issues portal — side effects this batch must not have). Also not run: the
nightly itself, for the same reason. The master should re-run both after batch 2's restart.

## Open items handed on

* C15 fires 22 times in itaa-1997 — the plan says open a ticket rather than let the nightly go
  red without one (S3 dependencies).
* C19 is at the plan's target already (26), so 0204's remaining work is the `_tree_title`
  regression in batch 2, not the extractor.
* C21's named-entity losses (already turned into spaces) are not recoverable without
  re-summarising; only the raw entities still present are repair candidates (batch 8).
