## VERDICT: REJECT

The plan's single most safety-critical table — the source-version audit — is factually wrong for **every act**, in the one direction that matters most for itaa-1997. And the tool the plan designates as the primary rebuild engine produces, on today's PDFs, the exact lossy signature that caused the earlier revert. Repo untouched (`git status --porcelain` = 26 untracked, unchanged; scanner wrote only `/tmp`).

---

## BLOCKERS

**1. No comp-266 source exists. The plan's itaa-1997 rebuild source is comp 263 — the corpus is 266.**

```
pdftotext -f1 -l1 staging/source/itaa-1997/C2026C00122VOL01.pdf → "Compilation No. 263"
grep -rh '^compilation_no:' data/itaa-1997/sections → 4648 × "compilation_no: 266"
```
Plan §Phase0.2 and the 2026-09-12 addendum both assert *"comp266 vol01-12.pdf + .txt ✓"*. There are no `.txt` files in staging at all, and all 12 PDFs are **263** (verified individually, all volumes). The corpus is genuinely 266: commit `091945207` "feat(data): ITAA 1997 compilation 266" updated 4,614 section files with real text changes plus new sections (Div 119, 40-291A, 112-155..185). **107 of the 133 flagged itaa-1997 files had table lines rewritten by that commit.** Rebuilding them from the 263 PDFs silently reverts the law text on the largest act in the corpus.
*Required:* delete the "comp266" claim; either download the actual comp-266 volumes from legislation.gov.au and verify `Compilation No. 266` on every volume before any itaa-1997 work, or drop itaa-1997 from scope entirely.

**2. The "NEWER compilation" column is wrong for all four acts it names — in the safe direction, but it drives the plan's whole method choice.**

| act | plan says staging has | actually (`pdftotext -f1 -l1`) | corpus fm |
|---|---|---|---|
| taa-1953 | comp225 (NEWER) | **222** (all 4 vols) | 222 ✓ |
| fbt-1986 | comp97 (NEWER) | **96** (both parts) | 96 ✓ |
| itaa-1936 | comp192 (NEWER) | **191** (all 7 vols) | 191 ✓ |
| gst-1999 | "no PDFs" | **`staging/source/gst-1999-vol{1,2}.pdf`, comp 96** | 96 ✓ |

Five of six acts have exact-compilation PDFs on disk. The plan's entire "diff section prose before using the newer PDF" procedure is unnecessary work built on a false premise, and it wrongly excludes gst-1999 from PDF-based rebuild.
*Required:* replace the table with the verified values above; delete the prose-diff-before-using-newer-PDF procedure.

**3. The designated primary extractor produces unusable output on the plan's own smoke-test section, and reproduces the reverted lossy signature.**

Run read-only, comp263 VOL03:
```
python3.12 scripts/extract_itaa_tables_pdf.py .../C2026C00122VOL03.pdf 115-30
```
- Every cell comes out character-spaced: `| 1 | A   * C G T   a s s e t   t h e   a c q u i r e r ...`. PyMuPDF `get_text("words")` returns per-glyph tokens on these table fonts; `render_rows` joins with `" "` (`extract_itaa_tables_pdf.py:282`).
- Item 2's cell ends **`...replacement asset for a`** — byte-identical to the lossy WIP signature the plan quotes in §Evidence (`"row 2 ends ...replacement asset for a |"`). The truncation is live *today*, not historic.
- Item 8 is absent from the rebuilt 10-row table.
- Header captured as `The affected sections apply as if the` — second header line and the table title `When the acquirer is treated as having acquired a CGT asset` are both dropped.

Meanwhile `pdftotext -layout -f 382 -l 383` on the *same page* yields a perfectly clean, sliceable table with the full item-2 text. **The plan has the two methods backwards:** it makes PyMuPDF word-position extraction primary for itaa-1997 and the layout slicer the fallback.
*Required:* make `pdftotext -layout` column-slicing the primary method; demote the word-position extractor to a cross-check, or drop it.

**4. The proposed fidelity gate cannot detect the failure it exists to catch.** §Phase0.3 proposes ">=98% text coverage … normalised whitespace". Two independent holes:
- *Direction.* "Coverage" is undefined. Checking that rebuilt words appear in the source page is **precision**, and a rebuild that emits 60% of the table scores 100%. The previous failure was *deletion*. The gate must be **recall over the PDF table band's token multiset**.
- *Whitespace normalisation defeats it outright.* `A * C G T   a s s e t` and `A *CGT asset` are identical after whitespace collapse. The garbage output in Blocker 3 would score 100%.
- 98% of a 500-word table = 10 words silently lost; in legal text that is a `not`, an `unless`, or a threshold.

*Required gate:* tokenise the PDF page's table band (`pdftotext -layout`, y/column-sliced) into a multiset; tokenise the rebuilt markdown table the same way; **require recall == 100%** against an explicitly enumerated drop-list (running header, `Compilation No.`, `Authorised Version`, page number, the `*To find definitions of asterisked terms…` footer). Any token dropped outside that list = reject the file. Additionally: reject if any rebuilt cell contains ≥3 consecutive single-character tokens (catches the glyph-spacing failure), and require `count('*')` in the rebuilt table == count in the source band — asterisked terms are legally operative and must **not** be normalised away (they are present in the PDF text layer: `pdftotext` shows `course of a *business`).

**5. Missing gate: nothing verifies that non-table text survives — and the existing driver actively eats prose.** `apply_itaa_table_fixes.py:254-266`: when a loose prose line is followed by a table-ish line, `find_table_region_end` classifies it as "mangled table content" and the replacement at line 300 deletes it. `validate_md()` (`:103-167`) checks frontmatter keys, the `# <section>` heading and column counts — nothing else. This is the most plausible mechanism of the reverted lossy run.
*Required:* a hard gate — strip all table-region lines from old and new file, require the remainder **byte-identical**; plus reject any file whose non-whitespace character count drops without every dropped token being accounted for by the Blocker-4 drop-list.

**6. "C11 rescan → 0" is a gameable completion gate.** `scan_corpus_error_classes.py:236` only inspects lines starting with `|`. Corruption flattened into blockquote shards or prose — precisely what §Evidence describes for 115-30 — is invisible. A rebuild that converts a broken table into prose scores 0. Also, the three classes are mutually exclusive **per line** (`continue` at `:244`, `:249`), so glyph masks truncated masks midword: fixing glyphs on a line can *raise* the truncated count. And `DANGLE_CELL_END` (`:198`) only matches a connector before the final `|` of a line, so truncation in any non-final cell is never counted — 504 is a lower bound, not a measurement.
*Required:* add a positive gate — rebuilt file must contain a well-formed table with row count == PDF table row count and no residual blockquote/orphan-prose shards in the replaced region. State in the plan that C11 counts are a floor and that class totals may rise after genuine partial fixes.

---

## REQUIRED CHANGES BEFORE EXECUTION

1. **Rewrite §Phase0.2 source table** with the verified compilations (Blocker 1–2). Add a pre-flight assertion in the driver: every source volume's page 1 must contain `Compilation No. <corpus compilation_no>`; abort the act otherwise.
2. **Re-order the acts.** Start with **gst-1999 (21 truncated, 23 files) or fbt-1986**, not itaa-1997: exact-comp PDFs, small blast radius, real calibration. itaa-1997 goes **last** and only after comp-266 sources exist. The plan's "most flags first" rule points straight at `itaa-1997/30-15.md` (42 findings) — see item 4.
3. **Replace the method.** `pdftotext -layout` slicing primary (Blocker 3). Note that `scripts/repair_itaa_tables.py` is **not** a reusable slicer: it hardcodes exactly three columns and the literal header `| Item | In this case: | The cost is: |` (`:258-260`, `:285`), and its `--apply` flag is **dead** — `main()` (`:350-371`) never calls `replace_table_in_file`, so a run believing it applied writes nothing. `scripts/extract_itaa_table.py` is likewise hardwired (`ITEM_MAX = 145`, `COST_MIN = 320`, `:18-19`, and requires `"In this case"`/`"The cost is"` at `:26`). Budget this as a new tool, not an extension.
4. **Scope out what the extractor provably cannot do.** Empirically today:
   - `104-5` (18 findings, 4th largest) → `section 104-5: no tables found`. Its table is keyed `A1/B1/C1`, header `Event number and description | Time of event | …` — no `Item` column.
   - `30-15` (42 findings, **largest single file**) → `section 30-15: no tables found`. Header `Recipient | Type of gift or contribution | …`, item number glued into cell 1 (`| 1 A fund, authority or |`).
   - **85 of 216 flagged files (39%) contain no `| Item` header at all** (fbt 10/13, gst 14/23, itaa-1936 12/17, itaa-1997 38/133, sis 2/3, taa 9/27).
   R3 is not "parameterise header detection": the row-grouping model itself is wrong. `build_rows` requires the literal `"Item"` (`:196`) — note `HEADER_WORD_RE` accepts `Items` (`:26`) but `build_rows` and `header_text:241` do not, so an `Items` block is detected then silently returns `[]` — and item keys must match `^\d+([A-Za-z]|\.\d+)*$` (`:205`), which rejects `A1`/`B1`. Either fix the model or declare these files out of scope explicitly.
5. **Add the four missing safety gates:** recall-based fidelity (Blocker 4), non-table-text-unchanged (Blocker 5), positive table-presence (Blocker 6), and rollback discipline — work on a branch, one commit per act, and a pre-commit assertion that `git diff --name-only` touches only `data/<act>/sections/**`. The plan's "repo is clean at 79a649408" is already stale: 26 untracked files including `data/definitions_all.json.bak-2026-08-22` and 20 `scripts/_*probe*.py`.
6. **Add downstream reindexing to Phase 3.** Changing 216 section files desyncs `data/search_index.db`, `data/embeddings.db` / `embeddings_matrix.npy`, and the definitions/citation/smartlink indices. Phase 3 currently verifies only `verify_data_integrity.py`, C11, and an API read. Add: re-run the section indexer for changed files and re-embed or mark-stale their chunks.
7. **Downgrade `cdn-0193-scope.json` from plan input to indicative.** `scan_truncation_scope.py:80` searches the concatenated raw of *all* volumes in reverse and takes the **last** `endswith(4-word probe)` match — not the match for that section, so the bucket is frequently decided by an unrelated occurrence. `NEWROW` (`:30`) treats any line starting `(a)`/`(b)` as a new row, but paragraph markers are the commonest *continuation* inside a legal cell — this inflates `page_split`. The 338/117/49 split should not be used to plan work.
8. **Handle endnote tables separately or scope them out.** `sis-1993/part-32/division-unknown/381.md` (5 findings) is the amendment-history endnote table — a 5-column header followed by a 4-column body (`381.md:30-36`) — not a legislative table, and not rebuildable by any section-keyed extractor.
9. **Fix the stale §Problem table.** It says 240 files / ~747 findings with itaa-1936 = 58; live is **216 files / 771 findings**, itaa-1936 = **76**, fbt = **74**, gst = **65**, taa = **106**, itaa-1997 = **418**. It contradicts the plan's own addendum.

---

## RECOMMENDED (non-blocking)

- The corpus is written live. Rebuild into a shadow tree and swap per act, or accept and state the mid-run broken-render window.
- Calibrate the fidelity gate on a table the extractor already handles cleanly (a CDN-0171-era fixed section), not on 115-30 — which is a *failing* case, not known-good.
- `collect_tables:314` merges any two adjacent blocks with equal header text regardless of page adjacency; two distinct tables sharing a header in one section would be silently concatenated. Worth a guard alongside the R4 fix.
- R6 as stated understates the risk: `is_footer_word` (`:163-167`) drops **everything** at `y1 >= 600`, not just the asterisk footnote — genuine last-row cell text on a full page is discarded, and `build_rows:222` computes the last-row cap from footer-filtered words, compounding R5.
- `repair_itaa_tables.py:259-260` silently converts smart quotes to ASCII; the corpus elsewhere retains `’`. Pick one and apply it corpus-wide, not per-tool.

---

## VERIFIED CLAIMS

**Confirmed:**
- Live C11 counts: **152 glyph / 115 midword / 504 truncated = 771** — exact match to the addendum.
- Addendum per-act truncated breakdown (340/68/29/25/21/21) — exact match.
- Repo raw compilations: itaa-1997 **263 (STALE)**, itaa-1936 191, taa 222, gst 96, fbt 96, sis 126 — all as the plan states.
- Corpus frontmatter compilations: 266/191/222/96/96/126 — all as the plan states.
- **R3** — `HEADER_WORD_RE` `extract_itaa_tables_pdf.py:26`, used `:97`, `:120`, `:196`, `:241`; item regex `:205`. Confirmed, and *worse* than stated (39% of flagged files; 104-5 and 30-15 return "no tables found").
- **R4** — `collect_tables:311-319` merges by header equality and `rows.extend`s with no cell-text rejoin. Confirmed.
- **R5** — `build_rows:218-224`, static `it["y1"] + 55`. Confirmed, and empirically the direct cause of the 115-30 item-2 truncation.
- **R6** — `is_footer_word:163-167`, `FOOTER_Y_MIN = 600`. Confirmed; broader than described.
- **R10** — `apply_itaa_table_fixes.py:75-78`, subprocess per section. Confirmed.
- "`validate_md()` checks only structure" — confirmed, `:103-167`.
- Earlier lossy signature is reproducible with today's tools on today's PDFs.

**Refuted:**
- "itaa-1997 rebuild source = comp266 PDFs" — no comp-266 source exists on disk.
- "taa-1953 staging = comp225 / fbt-1986 = comp97 / itaa-1936 = comp192 (NEWER)" — all equal the corpus compilation.
- "gst-1999 — no PDFs" — `staging/source/gst-1999-vol{1,2}.pdf`, comp 96.
- §Problem scope table (240 files / ~747 findings) — stale.

**Could not verify:**
- Whether the 263→266 table-line changes in the 107 affected files are substantive legal amendments or re-extraction churn. I did not diff them line-by-line; `82-150.md` shows the comp-266 ingest *itself* replaced a formula with an empty 3-column table and dropped its content, so at least some churn is new corruption from the current ingest pipeline — which the plan does not address, meaning the next compilation will re-corrupt whatever this rebuild fixes.
- The renderer/browser checks in §Phase3 (not exercised).
- Whether item 8 genuinely exists in the 115-30 source table (the extractor omits it; I did not page through the full PDF range).
OPUS_CC_EXIT=0
