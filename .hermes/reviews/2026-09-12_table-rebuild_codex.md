Reading additional input from stdin...
OpenAI Codex v0.149.0
--------
workdir: /home/harrison/legislation-explorer
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: none
reasoning summaries: none
session id: 01a093d1-3d3b-7941-8a9e-9443630d1954
--------
user
# TASK — READ-ONLY AUDIT of a corpus-rebuild plan (legislation-explorer)

You are reviewing a plan BEFORE it is executed against a live legal-research corpus.
Work strictly READ-ONLY: do not modify, create, or delete ANY file in the repo, do not
run anything that writes (no apply/driver scripts, no `git commit`, no service restart).
Reading files, grepping, running read-only analysis scripts and the C11 scanner is expected
and encouraged. Verify claims against real code and real data — do not merely agree with prose.

## Repo
/home/harrison/legislation-explorer (branch master). Live service reads these files directly.

## The plan under review
`.hermes/plans/2026-09-07_table-corruption-rebuild.md` — read it IN FULL, including the
2026-09-12 addendum "Scope measured 2026-09-12" at the end. Supporting artefact:
`.hermes/plans/cdn-0193-scope.json`, and the probe script `scripts/scan_truncation_scope.py`.

## Background you must assume
- The corpus is PDF->markdown; a subset of table-bearing sections is corrupt in three
  signatures, detected by `scripts/scan_corpus_error_classes.py` (`scan_table_coherence`):
  C11_table_midword, C11_table_glyph, C11_table_truncated.
- Current live counts (verify them yourself): 152 glyph / 115 midword / 504 truncated = 771 findings.
- Mid-word splits and the glyph false-positive class have already been partly repaired
  (commits b397eb655, ace38fb4c). Remaining work is this rebuild.
- An EARLIER automated attempt at this class was LOSSY and had to be reverted (§Evidence in
  the plan). That is the failure this gate exists to prevent.

## What to verify (do each, with evidence)
1. **Extractor defects.** The plan asserts specific defects in the PDF table tooling
   (R3 header detection keyed on a capitalised 'Item' first word, R4 page-break row
   continuation merge, R5 static 55pt last-row cap, R6 footer-word filter dropping the
   asterisked-terms line, R10 subprocess-per-file cost). Open the actual scripts
   (`scripts/extract_itaa_tables_pdf.py`, `scripts/extract_itaa_table.py`,
   `scripts/apply_itaa_table_fixes.py`, `scripts/repair_itaa_tables.py`) and confirm or
   refute each with file:line evidence. Note the line numbers in the plan are approximate.
2. **Source-version audit.** The plan's table claims each act's rebuild SOURCE (corpus
   frontmatter compilation vs repo raw compilation vs staging PDFs, some one compilation
   NEWER). Verify on disk: read `data/<act>/raw/`, check `/home/harrison/legislation-explorer-staging/source/`,
   and compare against section frontmatter `compilation_no`. Flag any act where the plan's
   stated source is wrong or unverifiable. This is the highest-risk item: rebuilding from a
   newer compilation would silently change the law text.
3. **Fidelity gate.** The plan proposes gating rebuilt tables on >=98% text coverage against
   the PDF text layer, calibrated on a known-good table. Assess: is this gate strong enough to
   catch the previous lossy failure mode? What normalisation is needed (asterisked italics,
   smart quotes, markdown links, hyphenation)? Propose the concrete gate (what is compared,
   what threshold, what happens on failure) and any additional content gate needed.
4. **Scope numbers.** Re-run the C11 scan (`python3 scripts/scan_corpus_error_classes.py`)
   and check the act-level breakdown and the truncated-class triage in the addendum against
   the live scanner output. Report any mismatch.
5. **Gates and abort conditions.** Are the plan's gates sufficient to prevent data loss at
   ~240-500 files scale? Identify missing fail-fast gates (e.g. per-file diff-review rules,
   "cell text must be a subsequence of source page text", back-up/rollback discipline,
   forbidden-edit rules, verification that no non-table line changed).
6. **Ordering / risk of regression.** Is the act order (itaa-1997 first, 340 truncated
   findings, repo raw STALE at comp 263 vs corpus 266) correct? Any act that should go first
   as a calibration target? Any act where the plan's fallback (repo raw layout slicer) is
   unsound?
7. **Anything else that would make this rebuild lossy or silently wrong.** Include issues
   with the plan's own measurement method (e.g. does the scanner over- or under-count, are
   the FIND classes mutually exclusive, could a rebuild fix one class and introduce another).

## Output format (your final message)
- `VERDICT: APPROVE` | `APPROVE-WITH-CHANGES` | `REJECT`
- `BLOCKERS:` numbered, each with file:line or command evidence and the exact change required.
- `REQUIRED CHANGES BEFORE EXECUTION:` numbered, prioritised, concrete (what to add/change).
- `RECOMMENDED (non-blocking):` brief.
- `VERIFIED CLAIMS:` which plan claims you independently confirmed, and which you could not.
Be specific and terse. Cite evidence for every claim. If you cannot verify something, say so
rather than assuming.
codex
I’ll conduct this strictly read-only. I’ll first read the full plan and probe/scanner, then inspect extractor code and corpus/source metadata, and finally rerun only the read-only scans and targeted analyses.
exec
/bin/bash -lc "sed -n '1,260p' .hermes/plans/2026-09-07_table-corruption-rebuild.md && sed -n '261,620p' .hermes/plans/2026-09-07_table-corruption-rebuild.md && sed -n '1,260p' scripts/scan_truncation_scope.py && sed -n '1,220p' .hermes/plans/cdn-0193-scope.json" in /home/harrison/legislation-explorer
 succeeded in 0ms:
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
#!/usr/bin/env python3
"""Size the CDN-0193 C11_table_truncated class.

For every C11_table_truncated finding, probe the act's raw extraction text
(data/<act>/raw/*.txt) for the offending cell's tail. If the raw line that
carries the tail CONTINUES onto a following raw line that is body text (not a
page footer/header, not a fresh table row), the loss is parser-side and the
text is recoverable from the repo raw. If the raw line also stops there, the
row was split at a PDF page boundary and recovery needs the source PDF.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path("/home/harrison/legislation-explorer")
DATA = REPO / "data"
FINDINGS = Path("/tmp/corpus_scan_20260826.json")

FOOTER = re.compile(
    r"compilation no|authorised version|^\s*\d+\s*$|"
    r"^\s*(income tax assessment act|taxation administration act|"
    r"a new tax system|fringe benefits tax assessment act|"
    r"superannuation industry \(supervision\) act)",
    re.I,
)
# a fresh table row / header starts a new logical row, not a continuation
NEWROW = re.compile(r"^\s*(item\b|\d+(\.\d+)*[A-Z]?\s|\(\w+\))", re.I)


def norm(s: str) -> str:
    s = re.sub(r"[*_`]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def raw_lines(act: str):
    out = []
    for p in sorted((DATA / act / "raw").glob("*.txt")):
        for ln in p.read_text(errors="replace").splitlines():
            out.append(norm(ln))
    return out


def main() -> int:
    findings = json.loads(FINDINGS.read_text())
    trunc = [f for f in findings if f["class"] == "C11_table_truncated"]

    cache: dict[str, list[str]] = {}
    stats = {"parser_side_recoverable": 0, "page_split": 0, "probe_not_found": 0}
    per_act: dict[str, dict] = {}
    detail_examples: dict[str, list[str]] = {k: [] for k in stats}

    for f in trunc:
        path = f["path"]  # e.g. itaa-1997/sections/...
        act = path.split("/", 1)[0]
        m = re.search(r"line (\d+)", f["detail"])
        if not m:
            continue
        ln_no = int(m.group(1))
        md = DATA / path
        try:
            md_line = md.read_text(errors="replace").splitlines()[ln_no - 1]
        except Exception:
            continue
        cells = [c.strip() for c in md_line.strip().strip("|").split("|")]
        if not cells:
            continue
        tail = norm(cells[-1])
        probe = " ".join(tail.split()[-4:])
        if not probe:
            continue
        if act not in cache:
            cache[act] = raw_lines(act)
        lines = cache[act]

        hit_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].endswith(probe):
                hit_idx = i
                break
        bucket = "probe_not_found"
        if hit_idx is not None:
            nxt = None
            for j in range(hit_idx + 1, min(hit_idx + 4, len(lines))):
                if lines[j]:
                    nxt = j
                    break
            if nxt is None or FOOTER.search(lines[nxt]) or NEWROW.match(lines[nxt]):
                bucket = "page_split"
            else:
                bucket = "parser_side_recoverable"
                if len(detail_examples[bucket]) < 8:
                    detail_examples[bucket].append(
                        f"{path}:{ln_no} tail={probe!r} cont={lines[nxt][:70]!r}"
                    )
        stats[bucket] += 1
        pa = per_act.setdefault(act, {"total": 0, "parser_side_recoverable": 0,
                                      "page_split": 0, "probe_not_found": 0})
        pa["total"] += 1
        pa[bucket] += 1

    print(f"C11_table_truncated findings: {len(trunc)}")
    print(f"  parser-side recoverable from repo raw : {stats['parser_side_recoverable']}")
    print(f"  split at PDF page boundary (needs PDF): {stats['page_split']}")
    print(f"  probe not located in raw              : {stats['probe_not_found']}")
    print()
    for act, pa in sorted(per_act.items()):
        print(f"{act:14s} total={pa['total']:4d}  recoverable={pa['parser_side_recoverable']:4d}"
              f"  page_split={pa['page_split']:4d}  not_found={pa['probe_not_found']:4d}")
    print()
    print("--- example recoverable (parser-side) ---")
    for e in detail_examples["parser_side_recoverable"]:
        print("  " + e)

    out = REPO / ".hermes/plans/cdn-0193-scope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"stats": stats, "per_act": per_act}, indent=2))
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
{
  "stats": {
    "parser_side_recoverable": 338,
    "page_split": 117,
    "probe_not_found": 49
  },
  "per_act": {
    "itaa-1997": {
      "total": 340,
      "parser_side_recoverable": 238,
      "page_split": 71,
      "probe_not_found": 31
    },
    "gst-1999": {
      "total": 21,
      "parser_side_recoverable": 16,
      "page_split": 5,
      "probe_not_found": 0
    },
    "fbt-1986": {
      "total": 21,
      "parser_side_recoverable": 18,
      "page_split": 2,
      "probe_not_found": 1
    },
    "taa-1953": {
      "total": 68,
      "parser_side_recoverable": 39,
      "page_split": 19,
      "probe_not_found": 10
    },
    "itaa-1936": {
      "total": 25,
      "parser_side_recoverable": 13,
      "page_split": 8,
      "probe_not_found": 4
    },
    "sis-1993": {
      "total": 29,
      "parser_side_recoverable": 14,
      "page_split": 12,
      "probe_not_found": 3
    }
  }
}
exec
/bin/bash -lc "nl -ba scripts/extract_itaa_tables_pdf.py | sed -n '1,390p'; nl -ba scripts/extract_itaa_table.py | sed -n '1,360p'; nl -ba scripts/apply_itaa_table_fixes.py | sed -n '1,420p'; nl -ba scripts/repair_itaa_tables.py | sed -n '1,420p'; nl -ba scripts/scan_corpus_error_classes.py | sed -n '1,360p'" in /home/harrison/legislation-explorer
 succeeded in 0ms:
     1	#!/usr/bin/env python3
     2	"""CDN-0171: rebuild mangled markdown tables in ITAA 1997 section files.
     3	
     4	Uses PyMuPDF word positions to reconstruct table cells column-by-column,
     5	eliminating the interleaving artifacts of pdftotext -layout.
     6	
     7	Method:
     8	  1. Locate the section's pages (find "Section X" body headers, fall back to
     9	     running headers).
    10	  2. On each page, find table header lines ("Item ...").
    11	  3. Derive column boundaries from the header words' x positions.
    12	  4. Assign every word to a column by x, group into rows by item number.
    13	"""
    14	
    15	import argparse
    16	import re
    17	import sys
    18	from pathlib import Path
    19	
    20	try:
    21	    import fitz  # PyMuPDF
    22	except ImportError:
    23	    fitz = None
    24	
    25	
    26	HEADER_WORD_RE = re.compile(r"^(Item|Items)$")  # capitalised; lower-case
    27	# 'item 6 of the table' in a body cell must NOT split a block
    28	
    29	
    30	def words_for_page(page) -> list[dict]:
    31	    """All words on a page sorted by (baseline y1, x0).
    32	
    33	    Different fonts (asterisked terms) have different ascents, so y0 differs
    34	    for the same visual line; baselines (y1) align across fonts.
    35	    """
    36	    out = []
    37	    for w in page.get_text("words"):
    38	        x0, y0, x1, y1, t = w[0], w[1], w[2], w[3], w[4]
    39	        out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "t": t})
    40	    out.sort(key=lambda w: (round(w["y1"], 2), w["x0"]))
    41	    return out
    42	
    43	
    44	def find_section_pages(doc, section: str) -> list[int]:
    45	    """Pages containing a body header 'Section X', a running header, or the
    46	    section's own heading line (e.g. '40-190 Second element of cost').
    47	    TOC entries (leader dots + page numbers) are excluded.
    48	    """
    49	    pages = []
    50	    pat_body = re.compile(rf"^Section\s+{re.escape(section)}\s*$", re.MULTILINE)
    51	    pat_run = re.compile(rf"Section\s+{re.escape(section)}\s*$", re.MULTILINE)
    52	    pat_own = re.compile(rf"^\s*{re.escape(section)}\s+\S", re.MULTILINE)
    53	    for pno in range(doc.page_count):
    54	        page = doc[pno]
    55	        txt = page.get_text("text")
    56	        # skip pages whose only mention is a TOC entry (leader dots)
    57	        if pat_body.search(txt) or pat_run.search(txt):
    58	            pages.append(pno)
    59	            continue
    60	        for ln in txt.splitlines():
    61	            if ".." in ln:
    62	                continue  # TOC leader line
    63	            if re.match(rf"^\s*{re.escape(section)}\s+\S", ln):
    64	                pages.append(pno)
    65	                break
    66	    # A table may start on the page BEFORE the first section marker (the
    67	    # section body continues from the previous page) and may flow onto the
    68	    # page after the last marker. Include both neighbours.
    69	    if pages:
    70	        first = pages[0]
    71	        if first - 1 >= 0 and first - 1 not in pages:
    72	            pages.insert(0, first - 1)
    73	        last = pages[-1]
    74	        nxt = last + 1
    75	        if nxt < doc.page_count and nxt not in pages:
    76	            pages.append(nxt)
    77	    return pages
    78	
    79	
    80	def table_blocks(page) -> list[list[dict]]:
    81	    """Split the page's words into table blocks: consecutive lines sharing
    82	    a common 'Item' header. Returns list of blocks; each block is a list of
    83	    word dicts (header words + body words)."""
    84	    words = words_for_page(page)
    85	    # Build lines: group words by rounded baseline y1 (aligns across fonts)
    86	    lines: dict[float, list[dict]] = {}
    87	    for w in words:
    88	        key = round(w["y1"], 2)
    89	        lines.setdefault(key, []).append(w)
    90	    ordered = sorted(lines.items())
    91	    blocks = []
    92	    cur = None
    93	    for y, ws in ordered:
    94	        # header line: first word is capitalised 'Item' IN THE ITEM COLUMN
    95	        # (lower-case 'item N of the table...' refs inside body cells must
    96	        # not split a block)
    97	        is_header = bool(ws) and HEADER_WORD_RE.match(ws[0]["t"])
    98	        if is_header:
    99	            if cur is not None and len(cur) > 1:
   100	                blocks.append(cur)
   101	            cur = []
   102	        if cur is not None:
   103	            cur.extend(ws)
   104	    if cur is not None and len(cur) > 1:
   105	        blocks.append(cur)
   106	    return blocks
   107	
   108	
   109	def col_boundaries(block: list[dict]) -> list[float]:
   110	    """Column x boundaries.
   111	
   112	    Prefer the header line's word clusters (accurate for standard tables);
   113	    fall back to line-start clustering when the header line has fewer than
   114	    3 words (covers wrapped two-line headers like 118-300's).
   115	    """
   116	    ys = sorted({round(w["y1"], 2) for w in block})
   117	    header_y = ys[0]
   118	    hdr = [w for w in block if round(w["y1"], 2) == header_y]
   119	    hdr.sort(key=lambda w: w["x0"])
   120	    if len(hdr) >= 3 and hdr[0]["t"] == "Item":
   121	        # cluster header words by gap > 8
   122	        clusters = []
   123	        cur = [hdr[0]]
   124	        for w in hdr[1:]:
   125	            gap = w["x0"] - cur[-1]["x1"]
   126	            if gap > 8:
   127	                clusters.append(cur)
   128	                cur = [w]
   129	            else:
   130	                cur.append(w)
   131	        clusters.append(cur)
   132	        if len(clusters) >= 2:
   133	            return [c[0]["x0"] for c in clusters[1:]]
   134	    return _col_boundaries_line_start(block)
   135	
   136	
   137	def _col_boundaries_line_start(block: list[dict]) -> list[float]:
   138	    """Fallback: cluster line-start x0s (leftmost word per baseline) across
   139	    the whole block. Handles wrapped two-line headers."""
   140	    line_starts = {}
   141	    for w in block:
   142	        key = round(w["y1"], 2)
   143	        if key not in line_starts or w["x0"] < line_starts[key]:
   144	            line_starts[key] = w["x0"]
   145	    xs = sorted(set(round(v, 1) for v in line_starts.values()))
   146	    if not xs:
   147	        return []
   148	    clusters = []
   149	    cur = [xs[0]]
   150	    for x in xs[1:]:
   151	        if x - cur[-1] > 20:
   152	            clusters.append(cur)
   153	            cur = [x]
   154	        else:
   155	            cur.append(x)
   156	    clusters.append(cur)
   157	    return [c[0] for c in clusters[1:]]
   158	
   159	
   160	FOOTER_Y_MIN = 600  # footer boilerplate starts ~y600 on the 842pt pages
   161	
   162	
   163	def is_footer_word(w: dict) -> bool:
   164	    """Footer boilerplate (the 'To find definitions...' line, the Compilation
   165	    header line, and the page number) sits in the bottom band of every page
   166	    (y1 >= ~600). Table cells never extend there."""
   167	    return w["y1"] >= FOOTER_Y_MIN
   168	
   169	
   170	def build_rows(block: list[dict], boundaries: list[float]) -> list[dict]:
   171	    """Assign words to columns, group into rows by item-number y positions.
   172	
   173	    The PDF's columns have different y-offsets for the same visual line
   174	    (font metrics), so line-grouping by y is unreliable. Instead:
   175	      1. Assign every word to a column by x.
   176	      2. The item column has one word per row (the item number). Sort those
   177	         by y; each marks the start of a row.
   178	      3. Every non-item word belongs to the row whose item-y it follows
   179	         (up to the next item-y).
   180	      4. Words in the footer band (y1 >= FOOTER_Y_MIN) are dropped.
   181	    """
   182	    # assign columns
   183	    for w in block:
   184	        col = 0
   185	        for i, bx in enumerate(boundaries):
   186	            if w["x0"] >= bx:
   187	                col = i + 1
   188	        w["col"] = col
   189	
   190	    # separate header line (the line containing 'Item' as first word)
   191	    ys = sorted({round(w["y1"], 2) for w in block})
   192	    header_y = None
   193	    for y in ys:
   194	        ws = [w for w in block if round(w["y1"], 2) == y]
   195	        if ws and ws[0]["t"] == "Item":
   196	            header_y = y
   197	            break
   198	    if header_y is None:
   199	        return []
   200	
   201	    # Item candidates must be above the footer band (page numbers live in
   202	    # the footer band and land in the item column).
   203	    items = []
   204	    for w in block:
   205	        if (w["col"] == 0 and re.match(r"^\d+([A-Za-z]|\.\d+)*$", w["t"])
   206	                and round(w["y1"], 2) > header_y and w["y1"] < FOOTER_Y_MIN):
   207	            items.append(w)
   208	    items.sort(key=lambda w: w["y1"])
   209	    if not items:
   210	        return []
   211	
   212	    rows = []
   213	    for idx, it in enumerate(items):
   214	        y_lo = it["y1"]
   215	        if idx + 1 < len(items):
   216	            y_hi = items[idx + 1]["y1"]
   217	        else:
   218	            # Cap the last row: table rows are at most ~55pt tall (4-5 text
   219	            # lines). Without a cap, the block's tail (notes, next section)
   220	            # gets swept into the last row.
   221	            y_hi = min(
   222	                max(w["y1"] for w in block if not is_footer_word(w)) + 1,
   223	                it["y1"] + 55,
   224	            )
   225	        row = {"item": it["t"], "cols": {i + 1: [] for i in range(len(boundaries))}}
   226	        for w in block:
   227	            if w["col"] > 0 and not is_footer_word(w) and y_lo <= w["y1"] < y_hi:
   228	                row["cols"][w["col"]].append(w["t"])
   229	        rows.append(row)
   230	    return rows
   231	
   232	
   233	def header_text(block: list[dict], boundaries: list[float]) -> list[str]:
   234	    """Real column labels from the table header line(s).
   235	
   236	    Primary: the 'Item' line itself. If a column has no words on that line
   237	    (wrapped header, e.g. 118-300's two-line header), add the next line.
   238	    """
   239	    item_line_y = None
   240	    for w in block:
   241	        if w["t"] == "Item" and w["col"] == 0:
   242	            item_line_y = round(w["y1"], 2)
   243	            break
   244	    if item_line_y is None:
   245	        return []
   246	
   247	    def labels_for(hdr_words: list[dict]) -> list[str]:
   248	        hdr_words.sort(key=lambda w: w["x0"])
   249	        labels = []
   250	        for i, bx in enumerate(boundaries):
   251	            if i + 1 < len(boundaries):
   252	                nxt = boundaries[i + 1]
   253	                words = [w["t"] for w in hdr_words if bx <= w["x0"] < nxt]
   254	            else:
   255	                words = [w["t"] for w in hdr_words if w["x0"] >= bx]
   256	            labels.append(" ".join(words))
   257	        return labels
   258	
   259	    ys = sorted({round(w["y1"], 2) for w in block})
   260	    idx = ys.index(item_line_y)
   261	    hdr = [w for w in block if round(w["y1"], 2) == item_line_y]
   262	    labels = labels_for(list(hdr))
   263	    # if any column is empty, add the next line (wrapped header)
   264	    if any(not lab.strip() for lab in labels) and idx + 1 < len(ys) and ys[idx + 1] - item_line_y < 16:
   265	        nxt_y = ys[idx + 1]
   266	        hdr2 = [w for w in block if round(w["y1"], 2) == nxt_y]
   267	        labels = labels_for(list(hdr) + hdr2)
   268	    return labels
   269	
   270	
   271	def render_rows(rows: list[dict], boundaries: list[float], header: list[str] | None = None) -> str:
   272	    """Render rows as a markdown table with real column headers."""
   273	    ncols = len(boundaries) + 1
   274	    if header and len(header) == len(boundaries):
   275	        header_cells = ["Item"] + header
   276	    else:
   277	        header_cells = ["Item"] + [f"Column {i + 1}" for i in range(len(boundaries))]
   278	    out = ["| " + " | ".join(header_cells) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
   279	    for r in rows:
   280	        cells = [r["item"]]
   281	        for i in range(len(boundaries)):
   282	            cells.append(" ".join(r["cols"].get(i + 1, [])))
   283	        out.append("| " + " | ".join(cells) + " |")
   284	    return "\n".join(out)
   285	
   286	
   287	def collect_tables(doc, section: str) -> list[dict]:
   288	    """All table blocks for a section as dicts: {header, rows} where rows is
   289	    [{item, cols: {col: text}}]. Blocks that are continuations of the same
   290	    logical table (same header, adjacent pages) are merged into one table.
   291	    """
   292	    pages = find_section_pages(doc, section)
   293	    out = []
   294	    for pno in pages:
   295	        page = doc[pno]
   296	        for block in table_blocks(page):
   297	            bd = col_boundaries(block)
   298	            if len(bd) < 2:
   299	                continue
   300	            rows = build_rows(block, bd)
   301	            if not rows:
   302	                continue
   303	            hdr = header_text(block, bd)
   304	            out.append({
   305	                "page": pno + 1,
   306	                "cols": len(bd) + 1,
   307	                "header": hdr,
   308	                "rows": [{"item": r["item"], "cols": {k: " ".join(v) for k, v in r["cols"].items()}} for r in rows],
   309	            })
   310	
   311	    # Merge blocks with the same header text (multi-page tables).
   312	    merged: list[dict] = []
   313	    for t in out:
   314	        if merged and merged[-1]["header"] == t["header"]:
   315	            # continuation: append rows (keep item numbering order)
   316	            merged[-1]["rows"].extend(t["rows"])
   317	            merged[-1]["page"] = f"{merged[-1]['page']}-{t['page']}"
   318	        else:
   319	            merged.append(dict(t))
   320	    return merged
   321	
   322	
   323	def main() -> int:
   324	    ap = argparse.ArgumentParser()
   325	    ap.add_argument("pdf")
   326	    ap.add_argument("section")
   327	    ap.add_argument("--json", action="store_true", help="emit JSON for the repair driver")
   328	    args = ap.parse_args()
   329	
   330	    if fitz is None:
   331	        print("PyMuPDF not available", file=sys.stderr)
   332	        return 2
   333	
   334	    doc = fitz.open(args.pdf)
   335	    tables = collect_tables(doc, args.section)
   336	    if not tables:
   337	        print(f"section {args.section}: no tables found", file=sys.stderr)
   338	        return 1
   339	
   340	    if args.json:
   341	        import json
   342	        print(json.dumps(tables, ensure_ascii=False))
   343	        return 0
   344	
   345	    print(f"section {args.section}: {len(tables)} tables")
   346	    for t in tables:
   347	        print(f"\n=== page {t['page']} cols={t['cols']} rows={len(t['rows'])} ===")
   348	        print(render_rows(
   349	            [{"item": r["item"], "cols": {int(k): v for k, v in r["cols"].items()}} for r in t["rows"]],
   350	            [0] * (t["cols"] - 1),
   351	            t["header"],
   352	        ))
   353	    return 0
   354	
   355	
   356	if __name__ == "__main__":
   357	    sys.exit(main())
     1	#!/usr/bin/env python3
     2	"""CDN-0171: rebuild mangled markdown tables in ITAA 1997 section files from
     3	the authoritative compilation PDFs using PyMuPDF layout extraction.
     4	
     5	Column boundaries (page-local x units): item ~125, case ~161, cost ~359.
     6	
     7	Usage:
     8	  python3 extract_itaa_table.py <pdf> <section>
     9	"""
    10	from __future__ import annotations
    11	
    12	import argparse
    13	import re
    14	import sys
    15	
    16	import fitz
    17	
    18	ITEM_MAX = 145
    19	COST_MIN = 320
    20	
    21	
    22	def find_table_pages(doc, section: str) -> list:
    23	    hits = []
    24	    for pno in range(doc.page_count):
    25	        page = doc[pno]
    26	        txt = page.get_text()
    27	        if f"Section {section}" in txt and "In this case" in txt and "The cost is" in txt:
    28	            hits.append(pno)
    29	    return hits
    30	
    31	
    32	def extract_table(doc, pno: int) -> list[list[str]]:
    33	    """Extract rows as [item, case, cost] from a page using line layout."""
    34	    page = doc[pno]
    35	    d = page.get_text("dict")
    36	    lines: list[tuple[float, list[tuple[float, str]]]] = []  # (y0, [(x0, word)])
    37	    for block in d["blocks"]:
    38	        if block["type"] != 0:  # text only
    39	            continue
    40	        for line in block["lines"]:
    41	            y0 = line["bbox"][1]
    42	            ws = []
    43	            for span in line["spans"]:
    44	                for ch in span.get("chars", []):
    45	                    pass
    46	                # spans have text; use span-level words via split
    47	                txt = span["text"]
    48	                if not txt.strip():
    49	                    continue
    50	                x0 = span["bbox"][0]
    51	                ws.append((x0, txt))
    52	            if ws:
    53	                lines.append((y0, ws))
    54	    # sort by y0 then x0
    55	    lines.sort(key=lambda t: (t[0], t[1][0] if t[1] else 0))
    56	
    57	    rows: list[list[str]] = []
    58	    cur = None
    59	
    60	    def flush():
    61	        nonlocal cur
    62	        if cur:
    63	            rows.append(cur)
    64	        cur = None
    65	
    66	    for y0, ws in lines:
    67	        joined = " ".join(w for _, w in ws)
    68	        # Detect row start: first word in item column is a number
    69	        first_x, first_w = ws[0]
    70	        if first_x < ITEM_MAX and re.match(r"^\d+$", first_w):
    71	            flush()
    72	            item = first_w
    73	            case, cost = [], []
    74	            for x, w in ws[1:]:
    75	                if x < COST_MIN:
    76	                    case.append(w)
    77	                else:
    78	                    cost.append(w)
    79	            cur = [item, case, cost]
    80	        elif cur is not None:
    81	            for x, w in ws:
    82	                if x < COST_MIN:
    83	                    cur[1].append(w)
    84	                else:
    85	                    cur[2].append(w)
    86	    flush()
    87	    return rows
    88	
    89	
    90	def main() -> None:
    91	    ap = argparse.ArgumentParser()
    92	    ap.add_argument("pdf")
    93	    ap.add_argument("section")
    94	    args = ap.parse_args()
    95	
    96	    doc = fitz.open(args.pdf)
    97	    pages = find_table_pages(doc, args.section)
    98	    print(f"pages with {args.section} table: {[p+1 for p in pages]}", file=sys.stderr)
    99	
   100	    for pno in pages:
   101	        rows = extract_table(doc, pno)
   102	        if not rows:
   103	            continue
   104	        print(f"--- page {pno+1}: {len(rows)} rows ---", file=sys.stderr)
   105	        print("| Item | In this case: | The cost is: |")
   106	        print("| --- | --- | --- |")
   107	        for item, case, cost in rows:
   108	            c = " ".join(case).replace("’", "'").replace("“", '"').replace("”", '"')
   109	            co = " ".join(cost).replace("’", "'").replace("“", '"').replace("”", '"')
   110	            print(f"| {item} | {c} | {co} |")
   111	
   112	
   113	if __name__ == "__main__":
   114	    main()
     1	#!/usr/bin/env python3
     2	"""CDN-0171 driver: extract ITAA 1997 tables from the authoritative PDFs and
     3	replace the mangled table regions in the section markdown files.
     4	
     5	Usage:
     6	  python3 scripts/apply_itaa_table_fixes.py [--dry-run] [--only SECT,SECT]
     7	"""
     8	
     9	import argparse
    10	import importlib.util
    11	import json
    12	import re
    13	import subprocess
    14	import sys
    15	from pathlib import Path
    16	
    17	REPO = Path("/home/harrison/legislation-explorer")
    18	DATA = REPO / "data" / "itaa-1997" / "sections"
    19	PDFDIR = Path("/home/harrison/legislation-explorer-staging/source/itaa-1997")
    20	
    21	# PyMuPDF lives in python3.12 (/usr/bin/python3); python3 (3.11) lacks fitz.
    22	# The extractor subprocess must use an interpreter that can import fitz.
    23	def _find_python_with_fitz() -> list[str]:
    24	    import shutil
    25	    for cand in ("python3.12", "/usr/bin/python3"):
    26	        path = shutil.which(cand) or (cand if Path(cand).exists() else None)
    27	        if not path:
    28	            continue
    29	        try:
    30	            r = subprocess.run(
    31	                [path, "-c", "import fitz"], capture_output=True, text=True, timeout=20,
    32	            )
    33	            if r.returncode == 0:
    34	                return [path]
    35	        except Exception:
    36	            continue
    37	    return ["python3"]  # fall back; extraction will fail loudly if fitz absent
    38	
    39	SECTIONS = {
    40	    "30-25": "C2026C00122VOL01.pdf",
    41	    "40-180": "C2026C00122VOL02.pdf",
    42	    "40-190": "C2026C00122VOL02.pdf",
    43	    "40-300": "C2026C00122VOL02.pdf",
    44	    "118-300": "C2026C00122VOL03.pdf",
    45	    "122-25": "C2026C00122VOL04.pdf",
    46	    "109-55": "C2026C00122VOL03.pdf",
    47	    "115-30": "C2026C00122VOL03.pdf",
    48	    "126-15": "C2026C00122VOL04.pdf",
    49	    "130-40": "C2026C00122VOL04.pdf",
    50	    "130-60": "C2026C00122VOL04.pdf",
    51	    "294-80": "C2026C00122VOL06.pdf",
    52	    "376-135": "C2026C00122VOL07.pdf",
    53	    "727-550": "C2026C00122VOL09.pdf",
    54	    "832-615": "C2026C00122VOL09.pdf",
    55	}
    56	
    57	EXTRACTOR = REPO / "scripts" / "extract_itaa_tables_pdf.py"
    58	
    59	# Sections whose tables are too corrupted for auto-rebuild (multi-page
    60	# 4-column tables with interleaved headers) — handled manually.
    61	SKIP_AUTO = {"30-25", "118-300", "832-615"}
    62	
    63	# Sections where the +1 continuation page leaks the NEXT section's table
    64	# (e.g. 40-305's 'In this case: The amount is:' after 40-300). Map section
    65	# -> required header prefix.
    66	HEADER_FILTER = {
    67	    "40-300": "For this balancing adjustment event:",
    68	}
    69	
    70	
    71	def extract_tables(section: str) -> list[dict]:
    72	    """Run the extractor in --json mode and parse."""
    73	    pdf = PDFDIR / SECTIONS[section]
    74	    py = _find_python_with_fitz()
    75	    r = subprocess.run(
    76	        py + [str(EXTRACTOR), str(pdf), section, "--json"],
    77	        capture_output=True, text=True, timeout=120,
    78	    )
    79	    if r.returncode != 0:
    80	        print(f"  extractor failed for {section}: {r.stderr.strip()}", file=sys.stderr)
    81	        return []
    82	    return json.loads(r.stdout)
    83	
    84	
    85	def find_section_file(section: str) -> Path | None:
    86	    hits = list(DATA.rglob(f"{section}.md"))
    87	    return hits[0] if hits else None
    88	
    89	
    90	def md_table(t: dict) -> str:
    91	    """Render a clean markdown table from an extracted table dict."""
    92	    header = ["Item"] + t["header"]
    93	    ncols = len(header)
    94	    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
    95	    for r in t["rows"]:
    96	        cells = [r["item"]]
    97	        for i in range(len(t["header"])):
    98	            cells.append(r["cols"].get(str(i + 1), ""))
    99	        out.append("| " + " | ".join(cells) + " |")
   100	    return "\n".join(out)
   101	
   102	
   103	def validate_md(txt: str, section: str) -> list[str]:
   104	    """Structural integrity checks. Returns a list of problems (empty = ok).
   105	
   106	    Guards the exact class of corruption that CDN-0171's driver introduced:
   107	    table rows jammed into the YAML frontmatter (which silently breaks page
   108	    rendering — keys split, frontmatter never closes). Also catches rows
   109	    whose column count disagrees with the separator (renders broken).
   110	    """
   111	    problems = []
   112	    # 1. frontmatter must parse as clean YAML-ish keys with NO pipe lines
   113	    m = re.match(r"^---\n(.*?)\n---", txt, re.DOTALL)
   114	    if not m:
   115	        problems.append("no YAML frontmatter")
   116	        return problems
   117	    fm = m.group(1)
   118	    for i, ln in enumerate(fm.splitlines(), start=2):
   119	        if ln.strip().startswith("|"):
   120	            problems.append(f"frontmatter line {i} contains table pipe")
   121	    # required keys present
   122	    for k in ("act", "part", "division", "section", "compilation_no"):
   123	        if not re.search(rf"^{re.escape(k)}:", fm, re.M):
   124	            problems.append(f"frontmatter missing key '{k}'")
   125	    # 2. heading present
   126	    if not re.search(rf"^#\s+{re.escape(section)}\b", txt, re.M):
   127	        problems.append(f"section heading '# {section}' missing")
   128	    # 3. every table structurally sound (separator, col counts)
   129	    lines = txt.splitlines()
   130	    i = 0
   131	    while i < len(lines):
   132	        ln = lines[i].strip()
   133	        if ln.startswith("|") and ln.count("|") >= 2:
   134	            # find separator
   135	            j = i
   136	            ncols = None
   137	            while j < len(lines) and not ncols:
   138	                s = lines[j].strip()
   139	                if s.startswith("|") and "---" in s:
   140	                    ncols = len([c for c in s.strip().strip("|").split("|") if c.strip() or True])
   141	                    break
   142	                j += 1
   143	            if ncols is None:
   144	                problems.append(f"line {i+1}: table has no separator row")
   145	                # skip to next non-pipe
   146	                while i < len(lines) and lines[i].strip().startswith("|"):
   147	                    i += 1
   148	                continue
   149	            # header row (i) must match separator
   150	            hdr_n = len([c for c in lines[i].strip().strip("|").split("|")])
   151	            if hdr_n != ncols:
   152	                problems.append(f"line {i+1}: header cols {hdr_n} != separator {ncols}")
   153	            # rows until non-pipe
   154	            i = j + 1
   155	            while i < len(lines):
   156	                s = lines[i].strip()
   157	                if not (s.startswith("|") and s.count("|") >= 2):
   158	                    break
   159	                if "---" not in s:
   160	                    n = len([c for c in s.strip().strip("|").split("|")])
   161	                    if n != ncols:
   162	                        problems.append(f"line {i+1}: row cols {n} != {ncols}")
   163	                        break
   164	                i += 1
   165	            continue
   166	        i += 1
   167	    return problems
   168	
   169	
   170	def find_table_start(txt: str, header: list[str]) -> int | None:
   171	    """Line index of the first '| Item' header matching the table family.
   172	
   173	    Skips the YAML frontmatter (which can contain '|' characters).
   174	    """
   175	    lines = txt.splitlines(keepends=True)
   176	    body_start = 0
   177	    if lines and lines[0].strip() == "---":
   178	        for i in range(1, len(lines)):
   179	            if lines[i].strip() == "---":
   180	                body_start = i + 1
   181	                break
   182	    wanted = {w for w in " ".join(header).split() if len(w) > 2}
   183	    for i in range(body_start, len(lines)):
   184	        ln = lines[i]
   185	        if not re.match(r"^\s*\|?\s*Item\b", ln) or "|" not in ln:
   186	            continue
   187	        have = set(ln.split())
   188	        if wanted and wanted.issubset(have):
   189	            return i
   190	        # fallback: any Item table header if no wanted words match
   191	        if not wanted:
   192	            return i
   193	    return None
   194	
   195	
   196	def find_table_region_end(txt: str, start: int) -> int:
   197	    """Char offset of the end of the table region starting at line 'start'.
   198	
   199	    Consumes table lines ('|'), separator lines, blockquotes (mangled row
   200	    fragments), and blank lines between them, stopping at the first prose
   201	    line or a new section element (e.g. '<a id=' or '**' heading).
   202	    """
   203	    lines = txt.splitlines(keepends=True)
   204	    i = start
   205	    # find the end of the LAST consecutive table-ish block
   206	    last_table_end = start
   207	    while i < len(lines):
   208	        ln = lines[i].strip()
   209	        if ln.startswith("|") or re.match(r"^\|?\s*:?-{3,}", ln):
   210	            last_table_end = i
   211	            i += 1
   212	        elif not ln:  # blank — peek ahead: if next non-blank is table-ish
   213	            # or a heading that precedes a table, continue; else stop
   214	            j = i
   215	            while j < len(lines) and not lines[j].strip():
   216	                j += 1
   217	            if j < len(lines):
   218	                nxt = lines[j].strip()
   219	                if nxt.startswith("|") or nxt.startswith(">"):
   220	                    i = j
   221	                elif nxt.startswith("**"):
   222	                    # heading — consume only if a table line follows it
   223	                    k = j + 1
   224	                    while k < len(lines) and not lines[k].strip():
   225	                        k += 1
   226	                    if k < len(lines) and (lines[k].strip().startswith("|") or lines[k].strip().startswith(">")):
   227	                        last_table_end = j
   228	                        i = k
   229	                    else:
   230	                        break
   231	                else:
   232	                    break
   233	            else:
   234	                break
   235	        elif ln.startswith(">"):
   236	            last_table_end = i
   237	            i += 1
   238	        elif ln.startswith("**"):
   239	            # table intro heading (e.g. '**First element of the cost of a
   240	            # depreciating asset**') — consume it only if followed by a
   241	            # table line
   242	            j = i + 1
   243	            while j < len(lines) and not lines[j].strip():
   244	                j += 1
   245	            if j < len(lines) and (lines[j].strip().startswith("|") or lines[j].strip().startswith(">")):
   246	                last_table_end = i
   247	                i = j
   248	            else:
   249	                break
   250	        elif re.match(r"^<a id=", ln):
   251	            break
   252	        elif ln.startswith("#") or ln == "---":
   253	            break
   254	        elif not ln.startswith("|") and not ln.startswith(">"):
   255	            # loose text — could be mangled table cell content (row text
   256	            # with the leading '|' stripped) OR real prose. If the NEXT
   257	            # non-blank line is table-ish, treat this as mangled content;
   258	            # otherwise stop.
   259	            j = i + 1
   260	            while j < len(lines) and not lines[j].strip():
   261	                j += 1
   262	            if j < len(lines) and (lines[j].strip().startswith("|") or lines[j].strip().startswith(">") or lines[j].strip().startswith("**")):
   263	                last_table_end = i
   264	                i = j
   265	            else:
   266	                break
   267	        else:
   268	            break
   269	    end = sum(len(x) for x in lines[:last_table_end + 1])
   270	    return end
   271	
   272	
   273	def apply_fix(section: str, dry_run: bool = False) -> bool:
   274	    p = find_section_file(section)
   275	    if p is None:
   276	        print(f"{section}: NO FILE")
   277	        return False
   278	    tables = extract_tables(section)
   279	    if not tables:
   280	        print(f"{section}: NO TABLES from PDF")
   281	        return False
   282	    if section in HEADER_FILTER:
   283	        pref = HEADER_FILTER[section]
   284	        tables = [t for t in tables if t["header"] and t["header"][0].startswith(pref)]
   285	
   286	    txt = p.read_text(errors="replace")
   287	    new_txt = txt
   288	    n_replaced = 0
   289	    for t in tables:
   290	        clean = md_table(t)
   291	        # Collapse the whole page-split table region (first header line to
   292	        # the end of the LAST table block) into one clean table.
   293	        start = find_table_start(new_txt, t["header"])
   294	        if start is None:
   295	            continue
   296	        end = find_table_region_end(new_txt, start)
   297	        # convert line index to char offset
   298	        lines_so_far = new_txt.splitlines(keepends=True)
   299	        start_char = sum(len(x) for x in lines_so_far[:start])
   300	        new_txt = new_txt[:start_char] + clean + "\n" + new_txt[end:]
   301	        n_replaced += 1
   302	
   303	    if n_replaced == 0:
   304	        print(f"{section}: nothing replaced")
   305	        return False
   306	
   307	    if dry_run:
   308	        print(f"{section}: WOULD replace {n_replaced} table(s) in {p.name}")
   309	        return True
   310	
   311	    # Safety guard: never write a file whose structure we just broke.
   312	    problems = validate_md(new_txt, section)
   313	    if problems:
   314	        print(f"{section}: REFUSED TO WRITE — validation failed:")
   315	        for prob in problems[:10]:
   316	            print(f"  !! {prob}")
   317	        return False
   318	
   319	    p.write_text(new_txt)
   320	    print(f"{section}: replaced {n_replaced} table(s) in {p.name}")
   321	    return True
   322	
   323	
   324	def main() -> int:
   325	    ap = argparse.ArgumentParser()
   326	    ap.add_argument("--dry-run", action="store_true")
   327	    ap.add_argument("--only", help="comma-separated sections")
   328	    args = ap.parse_args()
   329	
   330	    sections = [s for s in SECTIONS.keys() if s not in SKIP_AUTO]
   331	    if args.only:
   332	        sections = [s.strip() for s in args.only.split(",") if s.strip()]
   333	
   334	    ok = 0
   335	    for sec in sections:
   336	        if apply_fix(sec, dry_run=args.dry_run):
   337	            ok += 1
   338	    print(f"\n{ok}/{len(sections)} sections handled")
   339	    return 0
   340	
   341	
   342	if __name__ == "__main__":
   343	    sys.exit(main())
     1	#!/usr/bin/env python3
     2	"""CDN-0171: rebuild mangled markdown tables in itaa-1997 section files from
     3	the authoritative PDF layout text (legislation.gov.au compilation volumes).
     4	
     5	The section parser flattened multi-line PDF tables into jumbled markdown rows
     6	(e.g. s40-180 items 2, 8, 9). pdftotext -layout preserves column alignment,
     7	so we reconstruct each row by character-position column slicing, then replace
     8	the broken markdown table with clean single-cell-per-row markdown.
     9	
    10	Usage:
    11	  python3 repair_itaa_tables.py --vol /tmp/vol02.txt --section 40-180 [--apply]
    12	
    13	Writes a JSON report of proposed replacements; --apply writes the files.
    14	"""
    15	from __future__ import annotations
    16	
    17	import argparse
    18	import json
    19	import re
    20	import sys
    21	from pathlib import Path
    22	
    23	DATA = Path.home() / "legislation-explorer" / "data"
    24	
    25	# Character columns observed in the ITAA 1997 compilation PDFs (pdftotext -layout)
    26	# Item | In this case: | The cost is:
    27	ITEM_COL_START = 1      # item number starts here
    28	CASE_COL_START = 11     # "In this case:" text starts ~col 11
    29	COST_COL_START = 66     # "The cost is:" column starts ~col 66
    30	
    31	TABLE_HEADER_RE = re.compile(r"^\s*Item\s+\S.*\S\s{3,}\S")
    32	
    33	
    34	def detect_anchor(header: str) -> int:
    35	    """Find the third column start from a table header line.
    36	
    37	    Header shape: "Item <col2 label...> <col3 label>". The largest whitespace
    38	    run in the header separates col2 from col3; the anchor is where col3 starts.
    39	    """
    40	    runs = []
    41	    in_txt = False
    42	    start = 0
    43	    for c, ch in enumerate(header):
    44	        if ch != " " and not in_txt:
    45	            in_txt = True
    46	            start = c
    47	        elif ch == " " and in_txt:
    48	            in_txt = False
    49	            runs.append((start, c, header[start:c]))
    50	    if in_txt:
    51	        runs.append((start, len(header), header[start:]))
    52	    best_gap = -1
    53	    best_i = -1
    54	    for i in range(len(runs) - 1):
    55	        gap = runs[i + 1][0] - runs[i][1]
    56	        if gap > best_gap:
    57	            best_gap = gap
    58	            best_i = i
    59	    if best_i >= 0 and best_gap >= 3:
    60	        return runs[best_i + 1][0]
    61	    return 66
    62	
    63	
    64	def section_pages(pdf_text: str, section: str) -> tuple[int, int]:
    65	    """Find the line range of the section's body (from its Section header to
    66	    the next section's header)."""
    67	    lines = pdf_text.splitlines()
    68	    starts = []
    69	    for i, ln in enumerate(lines):
    70	        # Body headers are left-aligned; running headers are right-aligned
    71	        # (start at col 60+). Only accept left-aligned ones.
    72	        m = re.match(r"^\s{0,2}Section\s+([0-9]+(?:-[0-9]+)?[A-Z]?)\s*$", ln)
    73	        if m:
    74	            starts.append((m.group(1), i))
    75	    # find our section, then the next section start after it
    76	    for idx, (sid, i) in enumerate(starts):
    77	        if sid == section:
    78	            end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
    79	            # Back up ~50 lines to capture tables that begin on the previous
    80	            # page (a multi-page table can start under the running header of
    81	            # the page before the section's body header).
    82	            return max(0, i - 50), end
    83	    return 0, len(lines)
    84	
    85	
    86	def section_tables(pdf_text: str, section: str) -> list[tuple[list[str], int]]:
    87	    """Extract table blocks for a section, with fallback when the section
    88	    body header is missing (section continues across a volume boundary and
    89	    only running headers appear)."""
    90	    tables = extract_table_lines(pdf_text, section)
    91	    if tables and any(len(rows_from_table(t, a)) > 0 for t, a in tables):
    92	        return tables
    93	    # Fallback: search the whole text for tables whose first item looks
    94	    # like this section's table (bounded: take tables until the next
    95	    # left-aligned Section header).
    96	    lo, hi = section_pages(pdf_text, section)
    97	    if lo == 0 and hi == len(pdf_text.splitlines()):
    98	        lines = pdf_text.splitlines()
    99	        # Find the last running header for this section, take 50 lines after
   100	        best = -1
   101	        for i, ln in enumerate(lines):
   102	            if re.search(rf"Section\s+{re.escape(section)}\s*$", ln):
   103	                best = i
   104	        if best >= 0:
   105	            lo = max(0, best - 5)
   106	            hi = min(len(lines), best + 2000)
   107	            tables2: list[tuple[list[str], int]] = []
   108	            cur: list[str] | None = None
   109	            cur_anchor = 66
   110	            for ln in lines[lo:hi]:
   111	                if TABLE_HEADER_RE.search(ln):
   112	                    if cur is not None:
   113	                        tables2.append((cur, cur_anchor))
   114	                    cur = [ln]
   115	                    cur_anchor = detect_anchor(ln)
   116	                    continue
   117	                if cur is not None:
   118	                    if ln.strip().startswith("_" * 10) or "\f" in ln or "To find definitions" in ln:
   119	                        tables2.append((cur, cur_anchor))
   120	                        cur = None
   121	                    else:
   122	                        cur.append(ln)
   123	            if cur is not None:
   124	                tables2.append((cur, cur_anchor))
   125	            return tables2
   126	    return tables
   127	
   128	
   129	def extract_table_lines(pdf_text: str, section: str) -> list[tuple[list[str], int]]:
   130	    """Find table blocks in the layout text, scoped to the section's pages.
   131	
   132	    Returns (table_lines, cost_anchor) where cost_anchor is the column of
   133	    the third column label in that block's header.
   134	    """
   135	    lo, hi = section_pages(pdf_text, section)
   136	    lines = pdf_text.splitlines()[lo:hi]
   137	    tables: list[tuple[list[str], int]] = []
   138	    cur: list[str] | None = None
   139	    cur_anchor = 66
   140	    for ln in lines:
   141	        if TABLE_HEADER_RE.search(ln):
   142	            if cur is not None:
   143	                tables.append((cur, cur_anchor))
   144	            cur = [ln]
   145	            # The anchor is the start of the third column. The header is
   146	            # "Item <col2-label...> <col3-label>" — find the largest gap.
   147	            cur_anchor = detect_anchor(ln)
   148	            continue
   149	        if cur is not None:
   150	            if ln.strip().startswith("_" * 10) or "\f" in ln or "To find definitions" in ln:
   151	                tables.append((cur, cur_anchor))
   152	                cur = None
   153	            else:
   154	                cur.append(ln)
   155	    if cur is not None:
   156	        tables.append((cur, cur_anchor))
   157	    return tables
   158	
   159	
   160	def split_columns(line: str, anchor: int = 66) -> tuple[str, str]:
   161	    """Split a table layout line into (case, cost).
   162	
   163	    anchor = expected cost column start (from the block header). The cost
   164	    column in these PDFs sits at anchor..anchor-6 across rows, so we pick
   165	    the largest whitespace gap whose split point is within anchor±8.
   166	    Falls back to the plain largest gap.
   167	    """
   168	    line = line.rstrip("\n")
   169	    if not line.strip():
   170	        return "", ""
   171	    runs = []
   172	    in_txt = False
   173	    start = 0
   174	    for c, ch in enumerate(line):
   175	        if ch != " " and not in_txt:
   176	            in_txt = True
   177	            start = c
   178	        elif ch == " " and in_txt:
   179	            in_txt = False
   180	            runs.append((start, c, line[start:c]))
   181	    if in_txt:
   182	        runs.append((start, len(line), line[start:]))
   183	    if len(runs) < 2:
   184	        # Single run: route by x position. Cost column text starts at
   185	        # anchor (or a few chars left); case column text starts far left.
   186	        if runs and runs[0][0] >= anchor - 8:
   187	            return "", line.strip()
   188	        return line.strip(), ""
   189	    # If the whole line sits in the cost column (first run at anchor),
   190	    # route it all to cost. This handles continuation lines that carry
   191	    # only "The cost is" content.
   192	    if runs[0][0] >= anchor - 8:
   193	        return "", " ".join(r[2] for r in runs)
   194	    # Candidate splits: between run i and i+1.
   195	    # Prefer the largest gap whose split point is within anchor±8; if none
   196	    # qualify, use the global largest gap.
   197	    best_gap = -1
   198	    best_i = -1
   199	    anchored_gap = -1
   200	    anchored_i = -1
   201	    global_gap = -1
   202	    global_i = -1
   203	    for i in range(len(runs) - 1):
   204	        gap = runs[i + 1][0] - runs[i][1]
   205	        split_pos = runs[i + 1][0]
   206	        if gap > global_gap:
   207	            global_gap = gap
   208	            global_i = i
   209	        if abs(split_pos - anchor) <= 8 and gap > anchored_gap:
   210	            anchored_gap = gap
   211	            anchored_i = i
   212	    if anchored_i >= 0:
   213	        best_i = anchored_i
   214	        best_gap = anchored_gap
   215	    elif global_i >= 0:
   216	        best_i = global_i
   217	        best_gap = global_gap
   218	    if best_gap < 4:  # no real column separation
   219	        return line.strip(), ""
   220	    case = " ".join(r[2] for r in runs[: best_i + 1])
   221	    cost = " ".join(r[2] for r in runs[best_i + 1 :])
   222	    return case, cost
   223	
   224	
   225	def rows_from_table(table: list[str], anchor: int = 66) -> list[dict]:
   226	    """Split layout lines into (item, case, cost) cells by column detection."""
   227	    rows: list[dict] = []
   228	    cur: dict | None = None
   229	
   230	    def flush():
   231	        nonlocal cur
   232	        if cur and cur.get("item") is not None:
   233	            rows.append(cur)
   234	        cur = None
   235	
   236	    for ln in table:
   237	        # A new row starts when the Item column has a number. Item numbers
   238	        # sit at col 1-2 (aligned tables) or ~col 12 (indented tables);
   239	        # never accept a bare year like 1996 as an item.
   240	        item_m = re.match(r"^\s{0,14}(\d+(?:\.\d+)*)\s", ln)
   241	        is_new = bool(item_m) and item_m.group(1) not in {"1936", "1997", "1999", "2001", "2003", "2006", "2013", "2014", "2016", "2020", "2026"}
   242	        if is_new:
   243	            flush()
   244	            item_tok = item_m.group(1)
   245	            cur = {"item": item_tok, "case": [], "cost": []}
   246	            # The item token ends at its position in the line; split the
   247	            # remainder at the anchor. The item may be indented up to 14
   248	            # chars, so use the anchor as-is (no shift) for the rest.
   249	            item_end = item_m.end()
   250	            rest = ln[item_end:]
   251	            case, cost = split_columns(rest, anchor)
   252	            if case:
   253	                cur["case"].append(case)
   254	            if cost:
   255	                cur["cost"].append(cost)
   256	        elif cur is not None:
   257	            case, cost = split_columns(ln, anchor)
   258	            if case:
   259	                cur["case"].append(case)
   260	            if cost:
   261	                cur["cost"].append(cost)
   262	    flush()
   263	    return rows
   264	
   265	
   266	def md_table(rows: list[dict]) -> str:
   267	    """Render rows as a clean markdown table."""
   268	    out = ["| Item | In this case: | The cost is: |", "| --- | --- | --- |"]
   269	    for r in rows:
   270	        case = " ".join(r["case"]).replace("’", "'").replace("“", '"').replace("”", '"')
   271	        cost = " ".join(r["cost"]).replace("’", "'").replace("“", '"').replace("”", '"')
   272	        out.append(f"| {r['item']} | {case} | {cost} |")
   273	    return "\n".join(out)
   274	
   275	
   276	def replace_table_in_file(md_path: Path, rows: list[dict]) -> tuple[bool, int]:
   277	    """Replace the mangled cost-table region in a section markdown file.
   278	
   279	    Strategy: find the "| Item | In this case: | The cost is: |" header line,
   280	    then consume lines until the table footer ("| --- | --- | --- |") that
   281	    belongs to a *later* header, or until a new non-table block starts.
   282	    The existing mangled rows may span dozens of lines; we replace everything
   283	    from the header to the last line that still looks like table debris.
   284	    """
   285	    txt = md_path.read_text(errors="replace")
   286	    header_re = re.compile(r"^\s*\|?\s*Item\s*\|\s*In this case:\s*\|.*The cost is:\s*\|?\s*$")
   287	    lines = txt.splitlines()
   288	    header_idx = None
   289	    for i, ln in enumerate(lines):
   290	        if header_re.match(ln):
   291	            header_idx = i
   292	            break
   293	    if header_idx is None:
   294	        return False, 0
   295	
   296	    # Consume until a blank line followed by a non-table line, or a new
   297	    # "Item ... The cost is" header, or an explicit footer separator.
   298	    end = header_idx + 1
   299	    saw_any_row = False
   300	    while end < len(lines):
   301	        ln = lines[end]
   302	        if header_re.match(ln):
   303	            break
   304	        stripped = ln.strip()
   305	        if not stripped:
   306	            # Blank line: stop if we've already consumed table rows and the
   307	            # next non-blank line is not table debris.
   308	            nxt = end + 1
   309	            while nxt < len(lines) and not lines[nxt].strip():
   310	                nxt += 1
   311	            if nxt >= len(lines):
   312	                end = nxt
   313	                break
   314	            if lines[nxt].lstrip().startswith("|") or re.match(r"^\s*\|?\s*\d+\s*\|", lines[nxt]) or re.match(r"^\s*[-*_]{3,}\s*$", lines[nxt]):
   315	                end += 1
   316	                continue
   317	            break
   318	        if stripped == "| --- | --- | --- |" or stripped == "|--- | --- | --- |" or re.match(r"^\|?\s*-{3,}\s*\|\s*-{3,}", stripped):
   319	            # Footer separator: only belongs to this table if followed by
   320	            # more table rows; otherwise it's the end.
   321	            nxt = end + 1
   322	            while nxt < len(lines) and not lines[nxt].strip():
   323	                nxt += 1
   324	            if nxt < len(lines) and (lines[nxt].lstrip().startswith("|") or re.match(r"^\s*\d+\s*\|", lines[nxt])):
   325	                end += 1
   326	                continue
   327	            end += 1
   328	            break
   329	        if stripped.startswith("|") or re.match(r"^\s*\d+\s*\|", stripped) or stripped.startswith(">") or stripped.startswith("**"):
   330	            saw_any_row = True
   331	            end += 1
   332	            continue
   333	        break
   334	    if not saw_any_row:
   335	        return False, 0
   336	
   337	    new_table = md_table(rows)
   338	    new_lines = lines[:header_idx] + new_table.splitlines() + lines[end:]
   339	    md_path.write_text("\n".join(new_lines) + "\n")
   340	    return True, end - header_idx
   341	
   342	
   343	def find_section_file(section: str) -> Path | None:
   344	    for p in (DATA / "itaa-1997" / "sections").rglob(f"{section}.md"):
   345	        return p
   346	    return None
   347	
   348	
   349	def main() -> None:
   350	    ap = argparse.ArgumentParser()
   351	    ap.add_argument("--vol", required=True, help="pdftotext -layout output file")
   352	    ap.add_argument("--section", required=True, help="section id, e.g. 40-180")
   353	    ap.add_argument("--apply", action="store_true")
   354	    args = ap.parse_args()
   355	
   356	    pdf_text = Path(args.vol).read_text(errors="replace")
   357	    tables = extract_table_lines(pdf_text, args.section)
   358	    print(f"found {len(tables)} candidate table blocks")
   359	
   360	    allrows: list[dict] = []
   361	    for i, (t, anchor) in enumerate(tables):
   362	        rows = rows_from_table(t, anchor)
   363	        allrows.extend(rows)
   364	        print(f"--- table {i}: {len(rows)} rows (anchor {anchor}) ---")
   365	    print(f"TOTAL: {len(allrows)} rows")
   366	    print()
   367	    print(md_table(allrows))
   368	
   369	
   370	if __name__ == "__main__":
   371	    main()
     1	#!/usr/bin/env python3
     2	"""Corpus-wide scan against previously-identified error classes (bug register).
     3	
     4	Each check maps to a CDN ticket class and scans the FULL corpus, not just the
     5	reported instance. Emits machine-readable findings: class, act/path, detail.
     6	"""
     7	from __future__ import annotations
     8	
     9	import json
    10	import os
    11	import re
    12	import sys
    13	import unicodedata
    14	from collections import Counter
    15	from pathlib import Path
    16	
    17	DATA = Path("/home/harrison/legislation-explorer/data")
    18	findings: list[dict] = []
    19	
    20	
    21	def add(cls: str, path: str, detail: str):
    22	    findings.append({"class": cls, "path": path, "detail": detail})
    23	
    24	
    25	# ── C1 (CDN-0053/0070): compilation_no type consistency ─────────────────────
    26	def scan_compilation_no():
    27	    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
    28	        try:
    29	            t = json.loads((DATA / act / "tree.json").read_text())
    30	        except Exception as e:
    31	            add("C1_compilation_no", f"data/{act}/tree.json", f"unreadable: {e}")
    32	            continue
    33	        cn = t.get("compilation_no")
    34	        if isinstance(cn, str):
    35	            add("C1_compilation_no", f"data/{act}/tree.json",
    36	                f"compilation_no is str ({cn!r}), others are int")
    37	        if not t.get("compilation_date"):
    38	            add("C1_compilation_no", f"data/{act}/tree.json", "missing compilation_date")
    39	
    40	
    41	# ── C2 (CDN-0069): empty parts/divisions/leaves in trees ────────────────────
    42	def scan_empty_tree_nodes():
    43	    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
    44	        try:
    45	            t = json.loads((DATA / act / "tree.json").read_text())
    46	        except Exception:
    47	            continue
    48	        for pi, p in enumerate(t.get("parts", [])):
    49	            if not p.get("sections") and not p.get("divisions"):
    50	                add("C2_empty_node", f"data/{act}/tree.json", f"empty part: {p.get('id')}")
    51	            for di, d in enumerate(p.get("divisions", [])):
    52	                if not d.get("sections") and not d.get("subdivisions"):
    53	                    add("C2_empty_node", f"data/{act}/tree.json",
    54	                        f"empty division: {p.get('id')}/{d.get('id')}")
    55	                for si, s in enumerate(d.get("subdivisions", [])):
    56	                    if not s.get("sections"):
    57	                        add("C2_empty_node", f"data/{act}/tree.json",
    58	                            f"empty subdivision: {p.get('id')}/{d.get('id')}/{s.get('id')}")
    59	
    60	
    61	# ── C3 (CDN-0054): title truncation heuristics ──────────────────────────────
    62	# A truncated title typically: ends mid-word with a hyphen, or ends '…'/'..',
    63	# or ends with a standalone trailing word that indicates a cut (and/the/of/to
    64	# as the LAST word, e.g. 'Rules applying to particular gifts of'). Words that
    65	# merely CONTAIN those letters as suffixes ('demand', 'land') are NOT cuts.
    66	def scan_tree_titles():
    67	    suspicious_end = re.compile(r"[\w]-\s*$|\.\.\s*$|…\s*$|\b(?:and|the|of|to)\s*$")
    68	    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
    69	        try:
    70	            t = json.loads((DATA / act / "tree.json").read_text())
    71	        except Exception:
    72	            continue
    73	        stack = []
    74	        for p in t.get("parts", []):
    75	            stack.append(p)
    76	            for d in p.get("divisions", []):
    77	                stack.append(d)
    78	                for s in d.get("subdivisions", []):
    79	                    stack.append(s)
    80	        for node in stack:
    81	            title = node.get("title", "")
    82	            if not title:
    83	                continue
    84	            if suspicious_end.search(title.strip()) and len(title.strip()) > 3:
    85	                add("C3_title_truncation", f"data/{act}/tree.json",
    86	                    f"node {node.get('id')}: title ends suspiciously: {title!r}")
    87	
    88	
    89	# ── C4 (CDN-0006/0049): asterisk footnote lines in section bodies ───────────
    90	ASTERISK_LINE = re.compile(r"^\s*\*{2,}\s*$|^\s*\*[^*].*footnote|^\s*\*+ *[A-Za-z]+\s*\*+", re.M)
    91	def scan_body_fragments():
    92	    """Body text split into one-line fragments (treaties & any markdown).
    93	    Fragment lines: bare (N), (a), a quote char, or a lone dash/em-dash.
    94	    A file with more than 5 such lines is corrupted display-level text."""
    95	    frag_re = re.compile(r"^\((?:\d+|[a-z])\)$|^\"$|^[-—]$")
    96	    for base in [DATA / "treaties", DATA]:
    97	        if base == DATA:
    98	            dirs = [d for d in DATA.iterdir() if (d / "sections").is_dir()]
    99	        else:
   100	            dirs = [base]
   101	        for d in dirs:
   102	            for p in sorted((d / "sections").rglob("*.md")) if base == DATA else sorted(d.rglob("*.md")):
   103	                if p.name.startswith("."):
   104	                    continue
   105	                try:
   106	                    body = open(p, encoding="utf-8").read().split("---", 2)[-1]
   107	                except Exception:
   108	                    continue
   109	                frags = [ln.strip() for ln in body.splitlines() if frag_re.match(ln.strip())]
   110	                kinds = set()
   111	                for f in frags:
   112	                    if f == '"':
   113	                        kinds.add("quote")
   114	                    elif re.match(r"^[-—]$", f):
   115	                        kinds.add("dash")
   116	                    else:
   117	                        kinds.add("mark")
   118	                # Mono-pattern fragments are legitimate table cells (grid tables
   119	                # use bare dashes; ATO guides use bare table-category codes).
   120	                # Real fragmentation mixes quote/dash/marker kinds per file.
   121	                if len(frags) > 5 and len(kinds) >= 2:
   122	                    findings.append({"class": "C5_body_fragments", "path": str(p),
   123	                                     "detail": f"{len(frags)} fragment lines ({', '.join(sorted(kinds))}) e.g. {frags[0]!r} {frags[1]!r}"})
   124	
   125	
   126	# ── C4 (CDN-0006/0049): asterisk footnote lines in section bodies ───────────
   127	def scan_asterisk_noise():
   128	    for p in sorted((DATA / "itaa-1997" / "sections").rglob("*.md")):
   129	        text = p.read_text(errors="replace")
   130	        for m in ASTERISK_LINE.finditer(text):
   131	            line = text.count("\n", 0, m.start()) + 1
   132	            add("C4_asterisk_noise", str(p.relative_to(DATA)), f"line {line}: {m.group(0).strip()[:60]}")
   133	
   134	
   135	# ── C5 (CDN-0045/0167): sentence fragments / mid-sentence cut at end of section ─
   136	# Fragment signal: section body ends with a lowercase word right after content,
   137	# or a lone short word on the final line (no period), i.e. truncated at cut point.
   138	STRAY_TAIL = re.compile(r"^\s*[a-z]{2,10}\s*$")
   139	def scan_section_fragments():
   140	    for act_dir in DATA.iterdir():
   141	        sec_dir = act_dir / "sections"
   142	        if not sec_dir.is_dir():
   143	            continue
   144	        for p in sorted(sec_dir.rglob("*.md")):
   145	            text = p.read_text(errors="replace")
   146	            lines = [l.strip() for l in text.splitlines() if l.strip()]
   147	            if not lines:
   148	                continue
   149	            last = lines[-1]
   150	            # section bodies normally end with a period/heading/anchor
   151	            if STRAY_TAIL.match(last) and not last.endswith((".", ":", ")", "#")):
   152	                add("C5_fragment_tail", str(p.relative_to(DATA)), f"ends with lone word: {last!r}")
   153	            # fragment markers inside: '… of the' / 'the the' / double-space orphan
   154	            for m in re.finditer(r"\b(the the|of the of|and the and)\b", text, re.I):
   155	                ln = text.count("\n", 0, m.start()) + 1
   156	                add("C5_fragment_inline", str(p.relative_to(DATA)), f"line {ln}: {m.group(0)}")
   157	
   158	
   159	# ── C11 (CDN-0186/0187): table cell coherence — mid-word splits, glyph junk ─
   160	# Tables are the audit's blind spot: C5 skips anything inside '|' pipe rows,
   161	# so words cut across cells, PDF formula glyphs, and truncated rows all pass.
   162	# This class parses pipe-table cells:
   163	#   (a) mid-word split: a cell ends with a short lowercase fragment (<=4 chars,
   164	#       not itself a whole word preceded by a space) and the next cell starts
   165	#       lowercase — e.g. '| ... ast | erisked terms ... |' (whole word cut)
   166	#   (b) extraction glyphs: ç ÷ ´ ê ú æ û etc. inside any cell (formula junk)
   167	#   (c) dangling end: a table row's final cell ends with a bare connector
   168	#       ('the |', 'and |') — content truncated at the old page boundary
   169	EXTRACT_GLYPH = re.compile(r"[ç÷´êëûüàáâãäåæôöòóõøèéíìîïñšžÿý]")
   170	
   171	# A flagged char is NOT corruption when it is a normal diacritic inside an
   172	# alphabetic word in natural-language text (e.g. "Fédération Internationale").
   173	# Formula-font junk always shows up as a lone symbol, or as a prefix glued to
   174	# the following word ("êTotal", "ç1", "´ fringe benefits") — never with letters
   175	# on BOTH sides whose accent-folded form is a real word.
   176	_ASCII_FOLD = lambda w: "".join(
   177	    c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c)
   178	)
   179	
   180	
   181	def _is_natural_word_accent(line: str, m: re.Match) -> bool:
   182	    i = m.start()
   183	    if i == 0 or not line[i - 1].isalpha() or i + 1 >= len(line) or not line[i + 1].isalpha():
   184	        return False
   185	    s = i
   186	    while s > 0 and (line[s - 1].isalpha() or line[s - 1] in "'’"):
   187	        s -= 1
   188	    e = i + 1
   189	    while e < len(line) and line[e].isalpha():
   190	        e += 1
   191	    word = line[s:e]
   192	    if len(word) < 4:
   193	        return False
   194	    if _WORDS is None:
   195	        return False
   196	    return _ASCII_FOLD(word).lower() in _WORDS
   197	
   198	DANGLE_CELL_END = re.compile(r"\s(the|and|a|an|or|of|to|for|in|on|was|is|you|if|that|which|with|by|as|at|when)\s*\|\s*$", re.I)
   199	
   200	# /usr/share/dict/words (lowercase, ~104k) for the mid-word split test:
   201	# flag cell boundary only if NEITHER side is a word but their concatenation is
   202	# ('ast | erisked' -> 'asterisked'). Whole words on either side ('asset | when')
   203	# are legitimate cell boundaries and are skipped.
   204	try:
   205	    _WORDS = set(open("/usr/share/dict/words", encoding="utf-8").read().split())
   206	except Exception:
   207	    _WORDS = None
   208	
   209	
   210	def _tail_word(cell: str):
   211	    """Last whitespace-separated token of a cell, stripped of leading markers."""
   212	    t = cell.strip().split()[-1] if cell.strip().split() else ""
   213	    return t.strip(",*'\"()") if t else ""
   214	
   215	
   216	def _head_word(cell: str):
   217	    """First whitespace token of a cell, stripped of leading markers."""
   218	    parts = cell.strip().split()
   219	    if not parts:
   220	        return ""
   221	    t = parts[0]
   222	    return t.strip(",*'\"()") if t else ""
   223	
   224	
   225	def scan_table_coherence():
   226	    for act_dir in DATA.iterdir():
   227	        sec_dir = act_dir / "sections"
   228	        if not sec_dir.is_dir():
   229	            continue
   230	        for p in sorted(sec_dir.rglob("*.md")):
   231	            try:
   232	                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
   233	            except Exception:
   234	                continue
   235	            for ln_no, ln in enumerate(lines, 1):
   236	                if not ln.startswith("|") or re.match(r"^\|\s*---", ln):
   237	                    continue
   238	                # (b) glyph junk (ignore natural-language accents, e.g. "Fédération")
   239	                gm = next((m for m in EXTRACT_GLYPH.finditer(ln)
   240	                           if not _is_natural_word_accent(ln, m)), None)
   241	                if gm:
   242	                    add("C11_table_glyph", str(p.relative_to(DATA)),
   243	                        f"line {ln_no}: extraction glyph {gm.group(0)!r}: {ln.strip()[:90]}")
   244	                    continue
   245	                # (c) dangling connector end
   246	                if DANGLE_CELL_END.search(ln):
   247	                    add("C11_table_truncated", str(p.relative_to(DATA)),
   248	                        f"line {ln_no}: row ends on bare connector: {ln.strip()[:90]}")
   249	                    continue
   250	                # (a) mid-word split across adjacent cells — wordlist test
   251	                if _WORDS is None:
   252	                    continue
   253	                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
   254	                for ci in range(len(cells) - 1):
   255	                    left, right = cells[ci], cells[ci + 1]
   256	                    tw = _tail_word(left).lower()
   257	                    hw = _head_word(right).lower()
   258	                    if len(tw) < 1 or len(hw) < 1:
   259	                        continue
   260	                    joined = tw + hw
   261	                    # A boundary is only legitimate when BOTH sides are whole
   262	                    # words ('asset | when'). If either half is a fragment, the
   263	                    # word was cut across cells ('d | efinitions' too — a
   264	                    # single-letter half is still a fragment, not a cell).
   265	                    if joined in _WORDS and not (tw in _WORDS and hw in _WORDS):
   266	                        add("C11_table_midword", str(p.relative_to(DATA)),
   267	                            f"line {ln_no}: '{tw}|{hw}' = '{joined}' cut across cells {ci+1}|{ci+2}: {ln.strip()[:100]}")
   268	                        break
   269	
   270	
   271	# ── C6 (CDN-0081): stray trailing token at cut point (e.g. "payments") ──────
   272	# In tree titles or section H1: title that is a single fragment word repeated.
   273	def scan_stray_cut_tokens():
   274	    for act_dir in DATA.iterdir():
   275	        sec_dir = act_dir / "sections"
   276	        if not sec_dir.is_dir():
   277	            continue
   278	        for p in sorted(sec_dir.rglob("*.md")):
   279	            text = p.read_text(errors="replace")
   280	            # H1 then immediately a very short H2 identical-ish (cut artifact)
   281	            m = re.search(r"^# (.+)\n\n## (.+)$", text, re.M)
   282	            if m:
   283	                h1, h2 = m.group(1).strip(), m.group(2).strip()
   284	                if h2.lower().startswith(h1.lower().split()[0][:5]) and len(h2.split()) <= 2:
   285	                    add("C6_cut_token", str(p.relative_to(DATA)),
   286	                        f"H1={h1!r} H2={h2!r} looks like cut remnant")
   287	
   288	
   289	# ── C7 (CDN-0124): chapeau dropped — section body missing opening paragraph ──
   290	# If the first body paragraph after frontmatter starts with a subsection marker
   291	# or is empty → chapeau likely dropped.
   292	def scan_chapeau():
   293	    for act_dir in DATA.iterdir():
   294	        sec_dir = act_dir / "sections"
   295	        if not sec_dir.is_dir():
   296	            continue
   297	        for p in sorted(sec_dir.rglob("*.md")):
   298	            text = p.read_text(errors="replace")
   299	            m = re.search(r"^---\n.*?\n---\n(.*)$", text, re.S)
   300	            if not m:
   301	                continue
   302	            body = m.group(1).strip()
   303	            if not body:
   304	                add("C7_chapeau", str(p.relative_to(DATA)), "empty body")
   305	                continue
   306	            first_par = body.split("\n\n", 1)[0].strip()
   307	            if re.match(r"^\(\d+\)", first_par) and len(first_par) < 80:
   308	                add("C7_chapeau", str(p.relative_to(DATA)),
   309	                    f"body starts with subsection ({first_par[:60]!r}) — chapeau may be missing")
   310	
   311	
   312	# ── C8 (CDN-0095/0096/0097): formatting artifacts in bodies ─────────────────
   313	ARTIFACT_PATS = {
   314	    "header_slash": re.compile(r"/header/|/footer/|/content/"),
   315	    "md_link_junk": re.compile(r"\]\(\s*\)|!\[\]\(\)"),
   316	    "double_heading": re.compile(r"^##\s*$", re.M),
   317	    "stray_bullet": re.compile(r"^\s*[-*]\s*$", re.M),
   318	}
   319	def scan_formatting_artifacts():
   320	    for act_dir in DATA.iterdir():
   321	        sec_dir = act_dir / "sections"
   322	        if not sec_dir.is_dir():
   323	            continue
   324	        for p in sorted(sec_dir.rglob("*.md")):
   325	            text = p.read_text(errors="replace")
   326	            for name, pat in ARTIFACT_PATS.items():
   327	                m = pat.search(text)
   328	                if m:
   329	                    ln = text.count("\n", 0, m.start()) + 1
   330	                    add(f"C8_{name}", str(p.relative_to(DATA)), f"line {ln}: {m.group(0)[:40]!r}")
   331	                    break
   332	
   333	
   334	# ── C9 (CDN-0007/0048/0071): definitions index quality ──────────────────────
   335	def scan_definitions():
   336	    try:
   337	        store = json.loads((DATA / "definitions_all.json").read_text())
   338	    except Exception as e:
   339	        add("C9_definitions", "data/definitions_all.json", f"unreadable: {e}")
   340	        return
   341	    for act, act_data in store.items():
   342	        terms = act_data.get("terms", {})
   343	        # term keys that look truncated (end with 'the'/'of'/hyphen)
   344	        for term in terms:
   345	            if re.search(r"\b(the|of|and|to)\s*$", term, re.I) and len(term) > 8:
   346	                add("C9_definitions", "data/definitions_all.json",
   347	                    f"{act}: term looks truncated: {term!r}")
   348	        # terms without anchor (index entry that can't resolve)
   349	        for term, info in terms.items():
   350	            if not info.get("anchor") and not info.get("section"):
   351	                add("C9_definitions", "data/definitions_all.json",
   352	                    f"{act}: term {term!r} missing anchor+section")
   353	
   354	
   355	# ── C10 (CDN-0051/0073/0120): case citations year-collision / name issues ───
   356	def scan_case_citations():
   357	    # NOTE: FCAFC case numbers restart every year, so "[2018] FCAFC 122" and
   358	    # "[2024] FCAFC 122" are DIFFERENT cases — normalizing the year away and
   359	    # counting repeats is a false-positive factory. Only flag:
   360	    #   (a) the exact same citation appearing more than once (true duplicate),

exec
/bin/bash -lc "nl -ba scripts/apply_itaa_table_fixes.py | sed -n '1,360p'; nl -ba scripts/repair_itaa_tables.py | sed -n '1,390p'; tail -80 scripts/scan_corpus_error_classes.py" in /home/harrison/legislation-explorer
 succeeded in 0ms:
     1	#!/usr/bin/env python3
     2	"""CDN-0171 driver: extract ITAA 1997 tables from the authoritative PDFs and
     3	replace the mangled table regions in the section markdown files.
     4	
     5	Usage:
     6	  python3 scripts/apply_itaa_table_fixes.py [--dry-run] [--only SECT,SECT]
     7	"""
     8	
     9	import argparse
    10	import importlib.util
    11	import json
    12	import re
    13	import subprocess
    14	import sys
    15	from pathlib import Path
    16	
    17	REPO = Path("/home/harrison/legislation-explorer")
    18	DATA = REPO / "data" / "itaa-1997" / "sections"
    19	PDFDIR = Path("/home/harrison/legislation-explorer-staging/source/itaa-1997")
    20	
    21	# PyMuPDF lives in python3.12 (/usr/bin/python3); python3 (3.11) lacks fitz.
    22	# The extractor subprocess must use an interpreter that can import fitz.
    23	def _find_python_with_fitz() -> list[str]:
    24	    import shutil
    25	    for cand in ("python3.12", "/usr/bin/python3"):
    26	        path = shutil.which(cand) or (cand if Path(cand).exists() else None)
    27	        if not path:
    28	            continue
    29	        try:
    30	            r = subprocess.run(
    31	                [path, "-c", "import fitz"], capture_output=True, text=True, timeout=20,
    32	            )
    33	            if r.returncode == 0:
    34	                return [path]
    35	        except Exception:
    36	            continue
    37	    return ["python3"]  # fall back; extraction will fail loudly if fitz absent
    38	
    39	SECTIONS = {
    40	    "30-25": "C2026C00122VOL01.pdf",
    41	    "40-180": "C2026C00122VOL02.pdf",
    42	    "40-190": "C2026C00122VOL02.pdf",
    43	    "40-300": "C2026C00122VOL02.pdf",
    44	    "118-300": "C2026C00122VOL03.pdf",
    45	    "122-25": "C2026C00122VOL04.pdf",
    46	    "109-55": "C2026C00122VOL03.pdf",
    47	    "115-30": "C2026C00122VOL03.pdf",
    48	    "126-15": "C2026C00122VOL04.pdf",
    49	    "130-40": "C2026C00122VOL04.pdf",
    50	    "130-60": "C2026C00122VOL04.pdf",
    51	    "294-80": "C2026C00122VOL06.pdf",
    52	    "376-135": "C2026C00122VOL07.pdf",
    53	    "727-550": "C2026C00122VOL09.pdf",
    54	    "832-615": "C2026C00122VOL09.pdf",
    55	}
    56	
    57	EXTRACTOR = REPO / "scripts" / "extract_itaa_tables_pdf.py"
    58	
    59	# Sections whose tables are too corrupted for auto-rebuild (multi-page
    60	# 4-column tables with interleaved headers) — handled manually.
    61	SKIP_AUTO = {"30-25", "118-300", "832-615"}
    62	
    63	# Sections where the +1 continuation page leaks the NEXT section's table
    64	# (e.g. 40-305's 'In this case: The amount is:' after 40-300). Map section
    65	# -> required header prefix.
    66	HEADER_FILTER = {
    67	    "40-300": "For this balancing adjustment event:",
    68	}
    69	
    70	
    71	def extract_tables(section: str) -> list[dict]:
    72	    """Run the extractor in --json mode and parse."""
    73	    pdf = PDFDIR / SECTIONS[section]
    74	    py = _find_python_with_fitz()
    75	    r = subprocess.run(
    76	        py + [str(EXTRACTOR), str(pdf), section, "--json"],
    77	        capture_output=True, text=True, timeout=120,
    78	    )
    79	    if r.returncode != 0:
    80	        print(f"  extractor failed for {section}: {r.stderr.strip()}", file=sys.stderr)
    81	        return []
    82	    return json.loads(r.stdout)
    83	
    84	
    85	def find_section_file(section: str) -> Path | None:
    86	    hits = list(DATA.rglob(f"{section}.md"))
    87	    return hits[0] if hits else None
    88	
    89	
    90	def md_table(t: dict) -> str:
    91	    """Render a clean markdown table from an extracted table dict."""
    92	    header = ["Item"] + t["header"]
    93	    ncols = len(header)
    94	    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
    95	    for r in t["rows"]:
    96	        cells = [r["item"]]
    97	        for i in range(len(t["header"])):
    98	            cells.append(r["cols"].get(str(i + 1), ""))
    99	        out.append("| " + " | ".join(cells) + " |")
   100	    return "\n".join(out)
   101	
   102	
   103	def validate_md(txt: str, section: str) -> list[str]:
   104	    """Structural integrity checks. Returns a list of problems (empty = ok).
   105	
   106	    Guards the exact class of corruption that CDN-0171's driver introduced:
   107	    table rows jammed into the YAML frontmatter (which silently breaks page
   108	    rendering — keys split, frontmatter never closes). Also catches rows
   109	    whose column count disagrees with the separator (renders broken).
   110	    """
   111	    problems = []
   112	    # 1. frontmatter must parse as clean YAML-ish keys with NO pipe lines
   113	    m = re.match(r"^---\n(.*?)\n---", txt, re.DOTALL)
   114	    if not m:
   115	        problems.append("no YAML frontmatter")
   116	        return problems
   117	    fm = m.group(1)
   118	    for i, ln in enumerate(fm.splitlines(), start=2):
   119	        if ln.strip().startswith("|"):
   120	            problems.append(f"frontmatter line {i} contains table pipe")
   121	    # required keys present
   122	    for k in ("act", "part", "division", "section", "compilation_no"):
   123	        if not re.search(rf"^{re.escape(k)}:", fm, re.M):
   124	            problems.append(f"frontmatter missing key '{k}'")
   125	    # 2. heading present
   126	    if not re.search(rf"^#\s+{re.escape(section)}\b", txt, re.M):
   127	        problems.append(f"section heading '# {section}' missing")
   128	    # 3. every table structurally sound (separator, col counts)
   129	    lines = txt.splitlines()
   130	    i = 0
   131	    while i < len(lines):
   132	        ln = lines[i].strip()
   133	        if ln.startswith("|") and ln.count("|") >= 2:
   134	            # find separator
   135	            j = i
   136	            ncols = None
   137	            while j < len(lines) and not ncols:
   138	                s = lines[j].strip()
   139	                if s.startswith("|") and "---" in s:
   140	                    ncols = len([c for c in s.strip().strip("|").split("|") if c.strip() or True])
   141	                    break
   142	                j += 1
   143	            if ncols is None:
   144	                problems.append(f"line {i+1}: table has no separator row")
   145	                # skip to next non-pipe
   146	                while i < len(lines) and lines[i].strip().startswith("|"):
   147	                    i += 1
   148	                continue
   149	            # header row (i) must match separator
   150	            hdr_n = len([c for c in lines[i].strip().strip("|").split("|")])
   151	            if hdr_n != ncols:
   152	                problems.append(f"line {i+1}: header cols {hdr_n} != separator {ncols}")
   153	            # rows until non-pipe
   154	            i = j + 1
   155	            while i < len(lines):
   156	                s = lines[i].strip()
   157	                if not (s.startswith("|") and s.count("|") >= 2):
   158	                    break
   159	                if "---" not in s:
   160	                    n = len([c for c in s.strip().strip("|").split("|")])
   161	                    if n != ncols:
   162	                        problems.append(f"line {i+1}: row cols {n} != {ncols}")
   163	                        break
   164	                i += 1
   165	            continue
   166	        i += 1
   167	    return problems
   168	
   169	
   170	def find_table_start(txt: str, header: list[str]) -> int | None:
   171	    """Line index of the first '| Item' header matching the table family.
   172	
   173	    Skips the YAML frontmatter (which can contain '|' characters).
   174	    """
   175	    lines = txt.splitlines(keepends=True)
   176	    body_start = 0
   177	    if lines and lines[0].strip() == "---":
   178	        for i in range(1, len(lines)):
   179	            if lines[i].strip() == "---":
   180	                body_start = i + 1
   181	                break
   182	    wanted = {w for w in " ".join(header).split() if len(w) > 2}
   183	    for i in range(body_start, len(lines)):
   184	        ln = lines[i]
   185	        if not re.match(r"^\s*\|?\s*Item\b", ln) or "|" not in ln:
   186	            continue
   187	        have = set(ln.split())
   188	        if wanted and wanted.issubset(have):
   189	            return i
   190	        # fallback: any Item table header if no wanted words match
   191	        if not wanted:
   192	            return i
   193	    return None
   194	
   195	
   196	def find_table_region_end(txt: str, start: int) -> int:
   197	    """Char offset of the end of the table region starting at line 'start'.
   198	
   199	    Consumes table lines ('|'), separator lines, blockquotes (mangled row
   200	    fragments), and blank lines between them, stopping at the first prose
   201	    line or a new section element (e.g. '<a id=' or '**' heading).
   202	    """
   203	    lines = txt.splitlines(keepends=True)
   204	    i = start
   205	    # find the end of the LAST consecutive table-ish block
   206	    last_table_end = start
   207	    while i < len(lines):
   208	        ln = lines[i].strip()
   209	        if ln.startswith("|") or re.match(r"^\|?\s*:?-{3,}", ln):
   210	            last_table_end = i
   211	            i += 1
   212	        elif not ln:  # blank — peek ahead: if next non-blank is table-ish
   213	            # or a heading that precedes a table, continue; else stop
   214	            j = i
   215	            while j < len(lines) and not lines[j].strip():
   216	                j += 1
   217	            if j < len(lines):
   218	                nxt = lines[j].strip()
   219	                if nxt.startswith("|") or nxt.startswith(">"):
   220	                    i = j
   221	                elif nxt.startswith("**"):
   222	                    # heading — consume only if a table line follows it
   223	                    k = j + 1
   224	                    while k < len(lines) and not lines[k].strip():
   225	                        k += 1
   226	                    if k < len(lines) and (lines[k].strip().startswith("|") or lines[k].strip().startswith(">")):
   227	                        last_table_end = j
   228	                        i = k
   229	                    else:
   230	                        break
   231	                else:
   232	                    break
   233	            else:
   234	                break
   235	        elif ln.startswith(">"):
   236	            last_table_end = i
   237	            i += 1
   238	        elif ln.startswith("**"):
   239	            # table intro heading (e.g. '**First element of the cost of a
   240	            # depreciating asset**') — consume it only if followed by a
   241	            # table line
   242	            j = i + 1
   243	            while j < len(lines) and not lines[j].strip():
   244	                j += 1
   245	            if j < len(lines) and (lines[j].strip().startswith("|") or lines[j].strip().startswith(">")):
   246	                last_table_end = i
   247	                i = j
   248	            else:
   249	                break
   250	        elif re.match(r"^<a id=", ln):
   251	            break
   252	        elif ln.startswith("#") or ln == "---":
   253	            break
   254	        elif not ln.startswith("|") and not ln.startswith(">"):
   255	            # loose text — could be mangled table cell content (row text
   256	            # with the leading '|' stripped) OR real prose. If the NEXT
   257	            # non-blank line is table-ish, treat this as mangled content;
   258	            # otherwise stop.
   259	            j = i + 1
   260	            while j < len(lines) and not lines[j].strip():
   261	                j += 1
   262	            if j < len(lines) and (lines[j].strip().startswith("|") or lines[j].strip().startswith(">") or lines[j].strip().startswith("**")):
   263	                last_table_end = i
   264	                i = j
   265	            else:
   266	                break
   267	        else:
   268	            break
   269	    end = sum(len(x) for x in lines[:last_table_end + 1])
   270	    return end
   271	
   272	
   273	def apply_fix(section: str, dry_run: bool = False) -> bool:
   274	    p = find_section_file(section)
   275	    if p is None:
   276	        print(f"{section}: NO FILE")
   277	        return False
   278	    tables = extract_tables(section)
   279	    if not tables:
   280	        print(f"{section}: NO TABLES from PDF")
   281	        return False
   282	    if section in HEADER_FILTER:
   283	        pref = HEADER_FILTER[section]
   284	        tables = [t for t in tables if t["header"] and t["header"][0].startswith(pref)]
   285	
   286	    txt = p.read_text(errors="replace")
   287	    new_txt = txt
   288	    n_replaced = 0
   289	    for t in tables:
   290	        clean = md_table(t)
   291	        # Collapse the whole page-split table region (first header line to
   292	        # the end of the LAST table block) into one clean table.
   293	        start = find_table_start(new_txt, t["header"])
   294	        if start is None:
   295	            continue
   296	        end = find_table_region_end(new_txt, start)
   297	        # convert line index to char offset
   298	        lines_so_far = new_txt.splitlines(keepends=True)
   299	        start_char = sum(len(x) for x in lines_so_far[:start])
   300	        new_txt = new_txt[:start_char] + clean + "\n" + new_txt[end:]
   301	        n_replaced += 1
   302	
   303	    if n_replaced == 0:
   304	        print(f"{section}: nothing replaced")
   305	        return False
   306	
   307	    if dry_run:
   308	        print(f"{section}: WOULD replace {n_replaced} table(s) in {p.name}")
   309	        return True
   310	
   311	    # Safety guard: never write a file whose structure we just broke.
   312	    problems = validate_md(new_txt, section)
   313	    if problems:
   314	        print(f"{section}: REFUSED TO WRITE — validation failed:")
   315	        for prob in problems[:10]:
   316	            print(f"  !! {prob}")
   317	        return False
   318	
   319	    p.write_text(new_txt)
   320	    print(f"{section}: replaced {n_replaced} table(s) in {p.name}")
   321	    return True
   322	
   323	
   324	def main() -> int:
   325	    ap = argparse.ArgumentParser()
   326	    ap.add_argument("--dry-run", action="store_true")
   327	    ap.add_argument("--only", help="comma-separated sections")
   328	    args = ap.parse_args()
   329	
   330	    sections = [s for s in SECTIONS.keys() if s not in SKIP_AUTO]
   331	    if args.only:
   332	        sections = [s.strip() for s in args.only.split(",") if s.strip()]
   333	
   334	    ok = 0
   335	    for sec in sections:
   336	        if apply_fix(sec, dry_run=args.dry_run):
   337	            ok += 1
   338	    print(f"\n{ok}/{len(sections)} sections handled")
   339	    return 0
   340	
   341	
   342	if __name__ == "__main__":
   343	    sys.exit(main())
     1	#!/usr/bin/env python3
     2	"""CDN-0171: rebuild mangled markdown tables in itaa-1997 section files from
     3	the authoritative PDF layout text (legislation.gov.au compilation volumes).
     4	
     5	The section parser flattened multi-line PDF tables into jumbled markdown rows
     6	(e.g. s40-180 items 2, 8, 9). pdftotext -layout preserves column alignment,
     7	so we reconstruct each row by character-position column slicing, then replace
     8	the broken markdown table with clean single-cell-per-row markdown.
     9	
    10	Usage:
    11	  python3 repair_itaa_tables.py --vol /tmp/vol02.txt --section 40-180 [--apply]
    12	
    13	Writes a JSON report of proposed replacements; --apply writes the files.
    14	"""
    15	from __future__ import annotations
    16	
    17	import argparse
    18	import json
    19	import re
    20	import sys
    21	from pathlib import Path
    22	
    23	DATA = Path.home() / "legislation-explorer" / "data"
    24	
    25	# Character columns observed in the ITAA 1997 compilation PDFs (pdftotext -layout)
    26	# Item | In this case: | The cost is:
    27	ITEM_COL_START = 1      # item number starts here
    28	CASE_COL_START = 11     # "In this case:" text starts ~col 11
    29	COST_COL_START = 66     # "The cost is:" column starts ~col 66
    30	
    31	TABLE_HEADER_RE = re.compile(r"^\s*Item\s+\S.*\S\s{3,}\S")
    32	
    33	
    34	def detect_anchor(header: str) -> int:
    35	    """Find the third column start from a table header line.
    36	
    37	    Header shape: "Item <col2 label...> <col3 label>". The largest whitespace
    38	    run in the header separates col2 from col3; the anchor is where col3 starts.
    39	    """
    40	    runs = []
    41	    in_txt = False
    42	    start = 0
    43	    for c, ch in enumerate(header):
    44	        if ch != " " and not in_txt:
    45	            in_txt = True
    46	            start = c
    47	        elif ch == " " and in_txt:
    48	            in_txt = False
    49	            runs.append((start, c, header[start:c]))
    50	    if in_txt:
    51	        runs.append((start, len(header), header[start:]))
    52	    best_gap = -1
    53	    best_i = -1
    54	    for i in range(len(runs) - 1):
    55	        gap = runs[i + 1][0] - runs[i][1]
    56	        if gap > best_gap:
    57	            best_gap = gap
    58	            best_i = i
    59	    if best_i >= 0 and best_gap >= 3:
    60	        return runs[best_i + 1][0]
    61	    return 66
    62	
    63	
    64	def section_pages(pdf_text: str, section: str) -> tuple[int, int]:
    65	    """Find the line range of the section's body (from its Section header to
    66	    the next section's header)."""
    67	    lines = pdf_text.splitlines()
    68	    starts = []
    69	    for i, ln in enumerate(lines):
    70	        # Body headers are left-aligned; running headers are right-aligned
    71	        # (start at col 60+). Only accept left-aligned ones.
    72	        m = re.match(r"^\s{0,2}Section\s+([0-9]+(?:-[0-9]+)?[A-Z]?)\s*$", ln)
    73	        if m:
    74	            starts.append((m.group(1), i))
    75	    # find our section, then the next section start after it
    76	    for idx, (sid, i) in enumerate(starts):
    77	        if sid == section:
    78	            end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
    79	            # Back up ~50 lines to capture tables that begin on the previous
    80	            # page (a multi-page table can start under the running header of
    81	            # the page before the section's body header).
    82	            return max(0, i - 50), end
    83	    return 0, len(lines)
    84	
    85	
    86	def section_tables(pdf_text: str, section: str) -> list[tuple[list[str], int]]:
    87	    """Extract table blocks for a section, with fallback when the section
    88	    body header is missing (section continues across a volume boundary and
    89	    only running headers appear)."""
    90	    tables = extract_table_lines(pdf_text, section)
    91	    if tables and any(len(rows_from_table(t, a)) > 0 for t, a in tables):
    92	        return tables
    93	    # Fallback: search the whole text for tables whose first item looks
    94	    # like this section's table (bounded: take tables until the next
    95	    # left-aligned Section header).
    96	    lo, hi = section_pages(pdf_text, section)
    97	    if lo == 0 and hi == len(pdf_text.splitlines()):
    98	        lines = pdf_text.splitlines()
    99	        # Find the last running header for this section, take 50 lines after
   100	        best = -1
   101	        for i, ln in enumerate(lines):
   102	            if re.search(rf"Section\s+{re.escape(section)}\s*$", ln):
   103	                best = i
   104	        if best >= 0:
   105	            lo = max(0, best - 5)
   106	            hi = min(len(lines), best + 2000)
   107	            tables2: list[tuple[list[str], int]] = []
   108	            cur: list[str] | None = None
   109	            cur_anchor = 66
   110	            for ln in lines[lo:hi]:
   111	                if TABLE_HEADER_RE.search(ln):
   112	                    if cur is not None:
   113	                        tables2.append((cur, cur_anchor))
   114	                    cur = [ln]
   115	                    cur_anchor = detect_anchor(ln)
   116	                    continue
   117	                if cur is not None:
   118	                    if ln.strip().startswith("_" * 10) or "\f" in ln or "To find definitions" in ln:
   119	                        tables2.append((cur, cur_anchor))
   120	                        cur = None
   121	                    else:
   122	                        cur.append(ln)
   123	            if cur is not None:
   124	                tables2.append((cur, cur_anchor))
   125	            return tables2
   126	    return tables
   127	
   128	
   129	def extract_table_lines(pdf_text: str, section: str) -> list[tuple[list[str], int]]:
   130	    """Find table blocks in the layout text, scoped to the section's pages.
   131	
   132	    Returns (table_lines, cost_anchor) where cost_anchor is the column of
   133	    the third column label in that block's header.
   134	    """
   135	    lo, hi = section_pages(pdf_text, section)
   136	    lines = pdf_text.splitlines()[lo:hi]
   137	    tables: list[tuple[list[str], int]] = []
   138	    cur: list[str] | None = None
   139	    cur_anchor = 66
   140	    for ln in lines:
   141	        if TABLE_HEADER_RE.search(ln):
   142	            if cur is not None:
   143	                tables.append((cur, cur_anchor))
   144	            cur = [ln]
   145	            # The anchor is the start of the third column. The header is
   146	            # "Item <col2-label...> <col3-label>" — find the largest gap.
   147	            cur_anchor = detect_anchor(ln)
   148	            continue
   149	        if cur is not None:
   150	            if ln.strip().startswith("_" * 10) or "\f" in ln or "To find definitions" in ln:
   151	                tables.append((cur, cur_anchor))
   152	                cur = None
   153	            else:
   154	                cur.append(ln)
   155	    if cur is not None:
   156	        tables.append((cur, cur_anchor))
   157	    return tables
   158	
   159	
   160	def split_columns(line: str, anchor: int = 66) -> tuple[str, str]:
   161	    """Split a table layout line into (case, cost).
   162	
   163	    anchor = expected cost column start (from the block header). The cost
   164	    column in these PDFs sits at anchor..anchor-6 across rows, so we pick
   165	    the largest whitespace gap whose split point is within anchor±8.
   166	    Falls back to the plain largest gap.
   167	    """
   168	    line = line.rstrip("\n")
   169	    if not line.strip():
   170	        return "", ""
   171	    runs = []
   172	    in_txt = False
   173	    start = 0
   174	    for c, ch in enumerate(line):
   175	        if ch != " " and not in_txt:
   176	            in_txt = True
   177	            start = c
   178	        elif ch == " " and in_txt:
   179	            in_txt = False
   180	            runs.append((start, c, line[start:c]))
   181	    if in_txt:
   182	        runs.append((start, len(line), line[start:]))
   183	    if len(runs) < 2:
   184	        # Single run: route by x position. Cost column text starts at
   185	        # anchor (or a few chars left); case column text starts far left.
   186	        if runs and runs[0][0] >= anchor - 8:
   187	            return "", line.strip()
   188	        return line.strip(), ""
   189	    # If the whole line sits in the cost column (first run at anchor),
   190	    # route it all to cost. This handles continuation lines that carry
   191	    # only "The cost is" content.
   192	    if runs[0][0] >= anchor - 8:
   193	        return "", " ".join(r[2] for r in runs)
   194	    # Candidate splits: between run i and i+1.
   195	    # Prefer the largest gap whose split point is within anchor±8; if none
   196	    # qualify, use the global largest gap.
   197	    best_gap = -1
   198	    best_i = -1
   199	    anchored_gap = -1
   200	    anchored_i = -1
   201	    global_gap = -1
   202	    global_i = -1
   203	    for i in range(len(runs) - 1):
   204	        gap = runs[i + 1][0] - runs[i][1]
   205	        split_pos = runs[i + 1][0]
   206	        if gap > global_gap:
   207	            global_gap = gap
   208	            global_i = i
   209	        if abs(split_pos - anchor) <= 8 and gap > anchored_gap:
   210	            anchored_gap = gap
   211	            anchored_i = i
   212	    if anchored_i >= 0:
   213	        best_i = anchored_i
   214	        best_gap = anchored_gap
   215	    elif global_i >= 0:
   216	        best_i = global_i
   217	        best_gap = global_gap
   218	    if best_gap < 4:  # no real column separation
   219	        return line.strip(), ""
   220	    case = " ".join(r[2] for r in runs[: best_i + 1])
   221	    cost = " ".join(r[2] for r in runs[best_i + 1 :])
   222	    return case, cost
   223	
   224	
   225	def rows_from_table(table: list[str], anchor: int = 66) -> list[dict]:
   226	    """Split layout lines into (item, case, cost) cells by column detection."""
   227	    rows: list[dict] = []
   228	    cur: dict | None = None
   229	
   230	    def flush():
   231	        nonlocal cur
   232	        if cur and cur.get("item") is not None:
   233	            rows.append(cur)
   234	        cur = None
   235	
   236	    for ln in table:
   237	        # A new row starts when the Item column has a number. Item numbers
   238	        # sit at col 1-2 (aligned tables) or ~col 12 (indented tables);
   239	        # never accept a bare year like 1996 as an item.
   240	        item_m = re.match(r"^\s{0,14}(\d+(?:\.\d+)*)\s", ln)
   241	        is_new = bool(item_m) and item_m.group(1) not in {"1936", "1997", "1999", "2001", "2003", "2006", "2013", "2014", "2016", "2020", "2026"}
   242	        if is_new:
   243	            flush()
   244	            item_tok = item_m.group(1)
   245	            cur = {"item": item_tok, "case": [], "cost": []}
   246	            # The item token ends at its position in the line; split the
   247	            # remainder at the anchor. The item may be indented up to 14
   248	            # chars, so use the anchor as-is (no shift) for the rest.
   249	            item_end = item_m.end()
   250	            rest = ln[item_end:]
   251	            case, cost = split_columns(rest, anchor)
   252	            if case:
   253	                cur["case"].append(case)
   254	            if cost:
   255	                cur["cost"].append(cost)
   256	        elif cur is not None:
   257	            case, cost = split_columns(ln, anchor)
   258	            if case:
   259	                cur["case"].append(case)
   260	            if cost:
   261	                cur["cost"].append(cost)
   262	    flush()
   263	    return rows
   264	
   265	
   266	def md_table(rows: list[dict]) -> str:
   267	    """Render rows as a clean markdown table."""
   268	    out = ["| Item | In this case: | The cost is: |", "| --- | --- | --- |"]
   269	    for r in rows:
   270	        case = " ".join(r["case"]).replace("’", "'").replace("“", '"').replace("”", '"')
   271	        cost = " ".join(r["cost"]).replace("’", "'").replace("“", '"').replace("”", '"')
   272	        out.append(f"| {r['item']} | {case} | {cost} |")
   273	    return "\n".join(out)
   274	
   275	
   276	def replace_table_in_file(md_path: Path, rows: list[dict]) -> tuple[bool, int]:
   277	    """Replace the mangled cost-table region in a section markdown file.
   278	
   279	    Strategy: find the "| Item | In this case: | The cost is: |" header line,
   280	    then consume lines until the table footer ("| --- | --- | --- |") that
   281	    belongs to a *later* header, or until a new non-table block starts.
   282	    The existing mangled rows may span dozens of lines; we replace everything
   283	    from the header to the last line that still looks like table debris.
   284	    """
   285	    txt = md_path.read_text(errors="replace")
   286	    header_re = re.compile(r"^\s*\|?\s*Item\s*\|\s*In this case:\s*\|.*The cost is:\s*\|?\s*$")
   287	    lines = txt.splitlines()
   288	    header_idx = None
   289	    for i, ln in enumerate(lines):
   290	        if header_re.match(ln):
   291	            header_idx = i
   292	            break
   293	    if header_idx is None:
   294	        return False, 0
   295	
   296	    # Consume until a blank line followed by a non-table line, or a new
   297	    # "Item ... The cost is" header, or an explicit footer separator.
   298	    end = header_idx + 1
   299	    saw_any_row = False
   300	    while end < len(lines):
   301	        ln = lines[end]
   302	        if header_re.match(ln):
   303	            break
   304	        stripped = ln.strip()
   305	        if not stripped:
   306	            # Blank line: stop if we've already consumed table rows and the
   307	            # next non-blank line is not table debris.
   308	            nxt = end + 1
   309	            while nxt < len(lines) and not lines[nxt].strip():
   310	                nxt += 1
   311	            if nxt >= len(lines):
   312	                end = nxt
   313	                break
   314	            if lines[nxt].lstrip().startswith("|") or re.match(r"^\s*\|?\s*\d+\s*\|", lines[nxt]) or re.match(r"^\s*[-*_]{3,}\s*$", lines[nxt]):
   315	                end += 1
   316	                continue
   317	            break
   318	        if stripped == "| --- | --- | --- |" or stripped == "|--- | --- | --- |" or re.match(r"^\|?\s*-{3,}\s*\|\s*-{3,}", stripped):
   319	            # Footer separator: only belongs to this table if followed by
   320	            # more table rows; otherwise it's the end.
   321	            nxt = end + 1
   322	            while nxt < len(lines) and not lines[nxt].strip():
   323	                nxt += 1
   324	            if nxt < len(lines) and (lines[nxt].lstrip().startswith("|") or re.match(r"^\s*\d+\s*\|", lines[nxt])):
   325	                end += 1
   326	                continue
   327	            end += 1
   328	            break
   329	        if stripped.startswith("|") or re.match(r"^\s*\d+\s*\|", stripped) or stripped.startswith(">") or stripped.startswith("**"):
   330	            saw_any_row = True
   331	            end += 1
   332	            continue
   333	        break
   334	    if not saw_any_row:
   335	        return False, 0
   336	
   337	    new_table = md_table(rows)
   338	    new_lines = lines[:header_idx] + new_table.splitlines() + lines[end:]
   339	    md_path.write_text("\n".join(new_lines) + "\n")
   340	    return True, end - header_idx
   341	
   342	
   343	def find_section_file(section: str) -> Path | None:
   344	    for p in (DATA / "itaa-1997" / "sections").rglob(f"{section}.md"):
   345	        return p
   346	    return None
   347	
   348	
   349	def main() -> None:
   350	    ap = argparse.ArgumentParser()
   351	    ap.add_argument("--vol", required=True, help="pdftotext -layout output file")
   352	    ap.add_argument("--section", required=True, help="section id, e.g. 40-180")
   353	    ap.add_argument("--apply", action="store_true")
   354	    args = ap.parse_args()
   355	
   356	    pdf_text = Path(args.vol).read_text(errors="replace")
   357	    tables = extract_table_lines(pdf_text, args.section)
   358	    print(f"found {len(tables)} candidate table blocks")
   359	
   360	    allrows: list[dict] = []
   361	    for i, (t, anchor) in enumerate(tables):
   362	        rows = rows_from_table(t, anchor)
   363	        allrows.extend(rows)
   364	        print(f"--- table {i}: {len(rows)} rows (anchor {anchor}) ---")
   365	    print(f"TOTAL: {len(allrows)} rows")
   366	    print()
   367	    print(md_table(allrows))
   368	
   369	
   370	if __name__ == "__main__":
   371	    main()
        for term, info in terms.items():
            if not info.get("anchor") and not info.get("section"):
                add("C9_definitions", "data/definitions_all.json",
                    f"{act}: term {term!r} missing anchor+section")


# ── C10 (CDN-0051/0073/0120): case citations year-collision / name issues ───
def scan_case_citations():
    # NOTE: FCAFC case numbers restart every year, so "[2018] FCAFC 122" and
    # "[2024] FCAFC 122" are DIFFERENT cases — normalizing the year away and
    # counting repeats is a false-positive factory. Only flag:
    #   (a) the exact same citation appearing more than once (true duplicate),
    #   (b) the same court+number with NO year at all (year-less citation —
    #       the CDN-0120 class that year-blind enrichment produced).
    for f in ["fcafc_tax_cases.json", "case_section_refs.json"]:
        p = DATA / f
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else list(data.values())
        seen_exact = Counter()
        seen_courtnum = Counter()
        for it in items:
            if isinstance(it, dict):
                c = it.get("citation", "")
                if not c:
                    continue
                # (a) exact duplicates
                seen_exact[c] += 1
                # (b) year-less court+number (only when the citation has a
                # court prefix like 'FCAFC 122' but no [year])
                if re.match(r"^FCAFC\s+\d+", c):
                    seen_courtnum[c] += 1
        for cit, cnt in seen_exact.items():
            if cnt > 1:
                add("C10_citation_collision", f"data/{f}",
                    f"{cit!r} appears {cnt} times — exact duplicate")
        for cit, cnt in seen_courtnum.items():
            if cnt > 1:
                add("C10_citation_collision", f"data/{f}",
                    f"{cit!r} appears {cnt} times — year-less citation (CDN-0120 class)")


def main():
    scan_compilation_no()
    scan_empty_tree_nodes()
    scan_tree_titles()
    scan_asterisk_noise()
    scan_section_fragments()
    scan_stray_cut_tokens()
    scan_chapeau()
    scan_formatting_artifacts()
    scan_definitions()
    scan_case_citations()
    scan_table_coherence()

    # summarize
    by_class = Counter(f["class"] for f in findings)
    print(f"TOTAL FINDINGS: {len(findings)}")
    for cls, cnt in sorted(by_class.items()):
        print(f"  {cls}: {cnt}")
    print()
    # print first 3 per class for context
    seen = set()
    for f in findings:
        if f["class"] not in seen:
            print(f"--- {f['class']} ---")
            seen.add(f["class"])
        print(f"  {f['path']}: {f['detail'][:100]}")

    out = Path("/tmp/corpus_scan_20260826.json")
    out.write_text(json.dumps(findings, indent=2))
    print(f"\nfull JSON: {out}")


if __name__ == "__main__":
    main()

codex
The extractor claims are substantially grounded in code: capitalized `Item` is hard-coded, the final row is capped at 55pt, footer-band words are unconditionally dropped, and the driver launches an extractor subprocess per section. I’m now checking whether the claimed source compilations and scope classifications actually match disk; this is where the plan’s wording already appears internally inconsistent for SIS/FBT staging PDFs.
exec
/bin/bash -lc 'python3 scripts/scan_corpus_error_classes.py' in /home/harrison/legislation-explorer
 succeeded in 13356ms:
TOTAL FINDINGS: 771
  C11_table_glyph: 152
  C11_table_midword: 115
  C11_table_truncated: 504

--- C11_table_truncated ---
  itaa-1997/sections/part-2-1/division-20/20-105.md: line 19: row ends on bare connector: | This Subdivision | It applies when you lease the car, | It is
  gst-1999/sections/part-4-4/division-129/129-75.md: line 28: 'sec|tion' = 'section' cut across cells 2|3: | *To find definitions of asterisked terms, se
  gst-1999/sections/part-4-4/division-131/131-40.md: line 39: extraction glyph '´': | Full input ´ | Extent of | ´ Extent of |
  gst-1999/sections/part-4-4/division-132/132-5.md: line 36: extraction glyph 'è': | 11 | è | Full input tax credit ø |
  gst-1999/sections/part-4-6/division-159/159-10.md: line 43: row ends on bare connector: | Invoice | Part of payment | You cease to | Remainder of |
  gst-1999/sections/part-4-6/division-159/159-5.md: line 42: row ends on bare connector: | issued for | account on a | received for |
  gst-1999/sections/part-4-7/division-162/162-175.md: line 48: extraction glyph 'ê': | ê Your *annual GST | The *appropriate | ú | GST already |
  gst-1999/sections/part-4-7/division-162/162-175.md: line 50: extraction glyph 'ê': | êliability for the        ´ | percentage for the | ú – | payable |
  gst-1999/sections/part-4-7/division-162/162-175.md: line 51: extraction glyph 'ê': | ê*instalment   tax period | *GST  instalment  quarter | ú |  |
  gst-1999/sections/part-4-7/division-162/162-175.md: line 52: extraction glyph 'ë': | ë |  | û |  |
  gst-1999/sections/part-4-7/division-162/162-180.md: line 54: extraction glyph 'ê': | ê*instalment tax period | instalment quarter | ú GST instalment qua
  gst-1999/sections/part-4-7/division-162/162-180.md: line 56: extraction glyph 'ë': | ë |  | û |
  gst-1999/sections/part-4-7/division-162/162-195.md: line 39: extraction glyph 'ê': | ê Your *annual GST | The *appropriate | ú | Notified and |
  gst-1999/sections/part-4-7/division-162/162-195.md: line 41: extraction glyph 'ê': | ê liability for the    ´ | percentage for the | ú – | other amounts
  gst-1999/sections/part-4-7/division-162/162-195.md: line 42: extraction glyph 'ê': | ê*instalment tax period * | GST instalment quarter | ú |  |
  gst-1999/sections/part-4-7/division-162/162-195.md: line 43: extraction glyph 'ë': | ë |  | û |  |
  gst-1999/sections/part-4-7/division-162/162-5.md: line 71: row ends on bare connector: | Item | If your *current GST | Take into account this period t
  gst-1999/sections/part-4-7/division-162/162-5.md: line 73: row ends on bare connector: | 1 | at least 13 months | the 12 months preceding the current 
  gst-1999/sections/part-4-7/division-162/162-5.md: line 79: row ends on bare connector: | Item | If your *current GST | Take into account this period t
  gst-1999/sections/part-4-7/division-162/162-70.md: line 51: row ends on bare connector: | Item | If the GST instalment | Pay the GST instalment to |
  gst-1999/sections/part-4-7/division-162/162-70.md: line 55: 'aste|risked' = 'asterisked' cut across cells 1|2: | *To find definitions of aste | risked 
  gst-1999/sections/part-4-7/division-162/162-70.md: line 60: row ends on bare connector: | Item | If the GST instalment | Pay the GST instalment to |
  gst-1999/sections/part-6-3/division-195/195-1.md: line 812: 'paymen|ts' = 'payments' cut across cells 2|3: | 4AA       Sect | ion 78-18        Paymen 
  gst-1999/sections/part-6-3/division-195/195-1.md: line 813: 'inc|luding' = 'including' cut across cells 1|2: | (inc | luding as it     polici | es or 
  gst-1999/sections/part-6-3/division-195/195-1.md: line 814: 'appl|ies' = 'applies' cut across cells 1|2: | appl | ies in           scheme | s |
  gst-1999/sections/part-6-3/division-195/195-1.md: line 815: 'acco|rdance' = 'accordance' cut across cells 1|2: | acco | rdance with |  |
  gst-1999/sections/part-6-3/division-195/195-1.md: line 817: 'asteris|ked' = 'asterisked' cut across cells 1|2: | *To find definitions of asteris | ked
  gst-1999/sections/part-6-3/division-195/195-1.md: line 1643: 'de|finitions' = 'definitions' cut across cells 1|2: | *To find de | finitions of asteris
  gst-1999/sections/part-6-3/division-195/195-1.md: line 2213: row ends on bare connector: | Tax and Superannuation | 75, 2012 | 27 June | Sch 1 and 2: 
  gst-1999/sections/part-6-3/division-195/195-1.md: line 2300: row ends on bare connector: | Customs and Other | 41, 2015 | 20 May | Sch 6 (items 1, 2) 
  fbt-1986/sections/part-iia/division-1/5B.md: line 28: extraction glyph '´': | ´ fringe benefits | æ | ö æ | ö |
  fbt-1986/sections/part-iia/division-1/5B.md: line 30: extraction glyph 'ç': | amount | ç1 – FBT rate è | ÷ ´ ç1 + GST rate ø è | ÷ ´ FBT rate ø |
  fbt-1986/sections/part-iia/division-1/5B.md: line 69: extraction glyph 'æ': | non-exempt amount | æ | ö æ | ö FBT |
  fbt-1986/sections/part-iia/division-1/5B.md: line 76: extraction glyph 'æ': | amount | æ | ö |
  fbt-1986/sections/part-iii/division-10a/39GB.md: line 20: extraction glyph 'é': | é | ù | Number of days in car |
  fbt-1986/sections/part-iii/division-10a/39GB.md: line 22: extraction glyph 'ê': | êTotal value of car parking ´ 52 | ú ´ pa | rking availability peri
  fbt-1986/sections/part-iii/division-10a/39GB.md: line 23: extraction glyph 'ê': | ê   benefits  register      12 | ú | 366 |
  fbt-1986/sections/part-iii/division-10a/39GB.md: line 24: extraction glyph 'ë': | ëê | ûú |  |
  fbt-1986/sections/part-iii/division-13/58Q.md: line 34: extraction glyph 'æ': | æ | æ | öö |
  fbt-1986/sections/part-iii/division-13/58Q.md: line 36: extraction glyph 'ç': | $1,000 + ç $100 ´ | ç RLS - 15 | ÷ ÷ |
  fbt-1986/sections/part-iii/division-13/58Q.md: line 37: extraction glyph 'è': | è | è | øø |
  fbt-1986/sections/part-iii/division-13/58Q.md: line 38: 'wh|ole' = 'whole' cut across cells 2|3: | where RLS is the n | umber of wh | ole years in 
  fbt-1986/sections/part-iii/division-13/58Q.md: line 39: row ends on bare connector: | long service perio | d of the em | ployee that was recognised
  fbt-1986/sections/part-iii/division-13/58Q.md: line 40: row ends on bare connector: | the provision of t | he current | long service award benefit;
  fbt-1986/sections/part-iii/division-2/9.md: line 22: extraction glyph 'ç': | ç | Number of days | ÷ |
  fbt-1986/sections/part-iii/division-2/9.md: line 24: extraction glyph 'ç': | ç                        duri | ng  that year of tax | ÷ |
  fbt-1986/sections/part-iii/division-2/9.md: line 25: extraction glyph '÷': | on which | the car fringe benefits | ÷   Amount |
  fbt-1986/sections/part-iii/division-2/9.md: line 26: extraction glyph 'ç': | ç |  | (if any) |
  fbt-1986/sections/part-iii/division-2/9.md: line 27: extraction glyph 'ç': | ç 0.2 ´ Base value ´  were pr | ovided   by the provider | ÷ - of t
  fbt-1986/sections/part-iii/division-2/9.md: line 28: extraction glyph 'ç': | ç        of the car | Number of days | ÷  recipient's |
  fbt-1986/sections/part-iii/division-2/9.md: line 29: extraction glyph 'ç': | ç                           i | n that year of tax | ÷   payment |
  fbt-1986/sections/part-iii/division-2/9.md: line 30: extraction glyph 'ç': | ç |  | ÷ |
  fbt-1986/sections/part-iii/division-2/9.md: line 31: extraction glyph 'ç': | çç |  | ÷÷ |
  fbt-1986/sections/part-iii/division-2/9.md: line 32: extraction glyph 'è': | è |  | ø |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 33: row ends on bare connector: | 1 | a registered charity covered by item 1.1 of the table in 
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 52: row ends on bare connector: | 2 | a scientific institution covered by item 1.3 of the table
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 211: extraction glyph 'æ': | Rebatable æ | ö | days in |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 214: extraction glyph '´': | FBT ´ ç Gross tax - non-rebatable | ÷ ´ | year |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 215: extraction glyph 'ç': | rate  ç | ÷   T | otal days |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 216: extraction glyph 'ç': | ç               amount ÷ |  |  |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 217: extraction glyph 'è': | è | ø | in year |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 238: extraction glyph 'æ': | non-rebatable | æ | ö æ | ö |
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 240: extraction glyph 'ç': | amount | ç1 – FBT rate è | ÷ ´ ç1 + GST rate ø è | ÷ ´ FBT rate ø 
  fbt-1986/sections/part-iiia/division-unknown/65J.md: line 246: extraction glyph 'æ': | amount | æ | ö |
  fbt-1986/sections/part-vii/division-2/103.md: line 37: row ends on bare connector: | Item | If subsection (2) | the instalment is due and |
  fbt-1986/sections/part-vii/division-2/110.md: line 29: row ends on bare connector: | 4 | The notional tax amount would otherwise be worked out und
  fbt-1986/sections/part-vii/division-2/111.md: line 24: extraction glyph 'é': | é | ù | é | ù |
  fbt-1986/sections/part-vii/division-2/111.md: line 26: extraction glyph 'ê': | ê Notional ´ Relevant | ú – | ê Previous – Previous | ú |
  fbt-1986/sections/part-vii/division-2/111.md: line 27: extraction glyph 'ê': | ê tax amount fraction | ú | êinstalments  credits | ú |
  fbt-1986/sections/part-vii/division-2/111.md: line 28: extraction glyph 'ë': | ë | û | ë | û |
  fbt-1986/sections/part-vii/division-2/111.md: line 29: 'instal|ment' = 'instalment' cut across cells 2|3: | Otherwise, the amount | of the instal 
  fbt-1986/sections/part-vii/division-2/112B.md: line 42: extraction glyph 'é': | é | ù | é | ù |
  fbt-1986/sections/part-vii/division-2/112B.md: line 44: extraction glyph 'ê': | ê Minimum ´ Relevant ú | – | ê Previous – Previous | ú |
  fbt-1986/sections/part-vii/division-2/112B.md: line 45: extraction glyph 'ê': | ê tax amount fraction | ú | êinstalments  credits | ú |
  fbt-1986/sections/part-vii/division-2/112B.md: line 46: extraction glyph 'ë': | ë | û | ë | û |
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 59: extraction glyph 'ê': | ê Individual fringe | Individual ú | 1 |
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 61: extraction glyph 'ê': | ê benefits amount + qu | asi-fringe ú ´ |  |
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 62: extraction glyph 'ê': | ê                   be | nefits amount ú 1 – Ra | te of tax |
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 63: extraction glyph 'ë': | ë | û |  |
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 65: 'bene|fits' = 'benefits' cut across cells 1|2: | individual fringe bene | fits amount is th
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 66: row ends on bare connector: | fringe benefits amount | (if any) for the year | of tax in re
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 69: row ends on bare connector: | individual quasi-fring | e benefits amount for | the year of 
  fbt-1986/sections/part-xib/division-unknown/135Q.md: line 70: 'employe|e's' = 'employee's' cut across cells 1|2: | respect of the employe | e's employmen
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 24: 'ins|talments' = 'instalments' cut across cells 1|2: | Amount actually + amount of the - in
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 25: row ends on bare connector: | assessed           State or     by | the State or of | the St
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 26: 'terr|itory' = 'territory' cut across cells 1|2: | Territory body Terr | itory body   Ter |
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 28: row ends on bare connector: | amount actually assessed means the am | ount of the tax | ass
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 29: 'i|mmediately' = 'immediately' cut across cells 2|3: | respect of the State or Territory in
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 31: row ends on bare connector: | notional tax amount of the State or T | erritory body me | an
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 32: row ends on bare connector: | notional tax amount of the nominated | State or Territo | ry 
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 35: row ends on bare connector: | previous credits of the State or Terr | itory body means | th
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 37: row ends on bare connector: | instalments of tax of the nominated S | tate or Territor | y 
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 39: row ends on bare connector: | previous instalments by the State or | Territory body m | ean
  fbt-1986/sections/part-xic/division-unknown/135W.md: line 40: 'th|e' = 'the' cut across cells 1|2: | total of any instalments of tax of th | e nominated 
  fbt-1986/sections/part-xii/division-unknown/140.md: line 106: extraction glyph 'ç': | ç Total kilometres | ÷ | Total kilometres |
  fbt-1986/sections/part-xii/division-unknown/140.md: line 108: extraction glyph 'ç': | ç of the surface route ´ 2 | ÷ + o | f the surface route |
  fbt-1986/sections/part-xii/division-unknown/140.md: line 109: extraction glyph 'ç': | ç that are by water | ÷ | that are by land |
  fbt-1986/sections/part-xii/division-unknown/140.md: line 110: extraction glyph 'è': | è | ø |  |
  fbt-1986/sections/part-xii/division-unknown/167.md: line 192: row ends on bare connector: | Taxation Laws | 56, 1994 | 7 Apr 1994 | s 3–12: 7 Apr 1994(s
  fbt-1986/sections/part-xii/division-unknown/167.md: line 194: row ends on bare connector: | Taxation Laws | 82, 1994 | 23 June | s 3–6, 128–131: 23 June
  fbt-1986/sections/part-xii/division-unknown/167.md: line 392: row ends on bare connector: | Taxation Laws | 167, 2001 | 1 Oct 2001 | Sch 1 and Sch 4 | S
  fbt-1986/sections/part-xii/division-unknown/167.md: line 443: row ends on bare connector: | Tax Laws Amendment | 83, 2004 | 25 June | Sch 4 and Sch 8 | 
  fbt-1986/sections/part-xii/division-unknown/167.md: line 467: row ends on bare connector: | Tax Laws Amendment | 41, 2005 | 1 Apr 2005 | Sch 4 and Sch 1
  fbt-1986/sections/part-xii/division-unknown/167.md: line 537: row ends on bare connector: | (2007 Measures No. 4) |  | 2007 | 225, 226) and Sch 7 | 225,
  taa-1953/sections/part-iii/division-2/8W.md: line 43: extraction glyph 'ê': |  | Tax on | ê | setting amount | ú |
  taa-1953/sections/part-iii/division-2/8W.md: line 45: extraction glyph 'ê': | ca | pital gain | Origina ê ë | l reset cost base asset setting amo
  taa-1953/sections/part-iii/division-2/8W.md: line 47: 'adj|usted' = 'adjusted' cut across cells 1|2: | adj | usted reset c | ost base ass | et se
  taa-1953/sections/part-schedule1/division-111/111-50.md: line 25: row ends on bare connector: |  | Item | Decision | Provision of |
  taa-1953/sections/part-schedule1/division-112/112-50.md: line 27: row ends on bare connector: | Item | Decision | Provision of the |
  taa-1953/sections/part-schedule1/division-112/112-50.md: line 29: 'm|aking' = 'making' cut across cells 1|2: | 2       m | aking a declaration to negate or r
  taa-1953/sections/part-schedule1/division-112/112-50.md: line 30: 'd|isadvantage' = 'disadvantage' cut across cells 1|2: | d | isadvantage |  |
  taa-1953/sections/part-schedule1/division-112/112-50.md: line 32: 'defin|ition' = 'definition' cut across cells 1|2: | *For defin | ition, see section 995-1 
  taa-1953/sections/part-schedule1/division-112/112-50.md: line 37: row ends on bare connector: | Item | Decision | Provision of the |
  taa-1953/sections/part-schedule1/division-128/128-25.md: line 51: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1 
  taa-1953/sections/part-schedule1/division-128/128-25.md: line 59: row ends on bare connector: | 3 | unincorporated *GloBE JV Subsidiary of a *GloBE Joint Ven
  taa-1953/sections/part-schedule1/division-128/128-25.md: line 64: row ends on bare connector: | 5 | unincorporated *Group Entity of an *Applicable MNE Group 
  taa-1953/sections/part-schedule1/division-135/135-10.md: line 41: row ends on bare connector: | 4 | You become liable to pay | The amount of your | On the gi
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 25: extraction glyph '´': |  | Shortfall interest charge rate ´ ç Amount of + | Sum of earlier 
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 28: 'cont|ribution' = 'contribution' cut across cells 2|3: | a | mount of contribution means th
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 30: 's|hortfall' = 'shortfall' cut across cells 1|2: | s | hortfall interest charge rate means 
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 31: 's|ubsection' = 'subsection' cut across cells 1|2: | s | ubsection 280-105(2), for the day.
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 33: 'w|orked' = 'worked' cut across cells 1|2: | w | orked out for the contribution under the f
  taa-1953/sections/part-schedule1/division-138/138-40.md: line 34: 'e|arlier' = 'earlier' cut across cells 1|2: | e | arlier days (if any) during the period f
  taa-1953/sections/part-schedule1/division-16/16-75.md: line 25: row ends on bare connector: | Item | If the amount is withheld on this | It must be paid to
  taa-1953/sections/part-schedule1/division-16/16-75.md: line 65: row ends on bare connector: | Item | If the amount is withheld during | the amount must be 
  taa-1953/sections/part-schedule1/division-260/260-45.md: line 49: extraction glyph 'ç': |  | ç | Notified | ÷ |
  taa-1953/sections/part-schedule1/division-260/260-45.md: line 51: extraction glyph 'ç': | Total value of assets | ç | amount | ÷ |
  taa-1953/sections/part-schedule1/division-260/260-45.md: line 52: extraction glyph '´': | available to pay ordinary debts ´ | ç ç Notified ç amount è | Amoun
  taa-1953/sections/part-schedule1/division-260/260-45.md: line 55: 'outst|anding' = 'outstanding' cut across cells 2|3: | company's ordinary debts other than 
  taa-1953/sections/part-schedule1/division-260/260-75.md: line 49: extraction glyph 'ç': |  | ç | Notified | ÷ |
  taa-1953/sections/part-schedule1/division-260/260-75.md: line 51: extraction glyph 'ç': | Total value of assets | ç | amount | ÷ |
  taa-1953/sections/part-schedule1/division-260/260-75.md: line 52: extraction glyph '´': | ´ | ç |  |  |
  taa-1953/sections/part-schedule1/division-260/260-75.md: line 53: extraction glyph 'ç': | available to pay ordinary debts | ç Notified ç amount è | Amount of
  taa-1953/sections/part-schedule1/division-260/260-75.md: line 56: 'outst|anding' = 'outstanding' cut across cells 2|3: | company's ordinary debts other than 
  taa-1953/sections/part-schedule1/division-268/268-90.md: line 90: row ends on bare connector: | 2 | a body corporate | (a) in the case of a company that has 
  taa-1953/sections/part-schedule1/division-268/268-90.md: line 99: row ends on bare connector: | 3 | a body politic | an individual prescribed by the |
  taa-1953/sections/part-schedule1/division-268/268-90.md: line 102: row ends on bare connector: | 5 | any other unincorporated association or body of persons 
  taa-1953/sections/part-schedule1/division-268/268-90.md: line 112: row ends on bare connector: | 6 | a trust | (a) the trustee of the trust; or |
  taa-1953/sections/part-schedule1/division-268/268-90.md: line 118: row ends on bare connector: | 7 | a *superannuation fund or an | (a) the trustee of the fu
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 36: row ends on bare connector: | 1 | an amount in accordance with Subdivision 16-B (obligation
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 44: row ends on bare connector: | 3        s | uperannuation            th | e due day,        
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 45: 'g|uarantee' = 'guarantee' cut across cells 1|2: | g | uarantee charge for | before th | e 
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 47: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1 
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 64: row ends on bare connector: | 5 | an *assessed net amount for a *tax period | the last day 
  taa-1953/sections/part-schedule1/division-269/269-30.md: line 66: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1 
  taa-1953/sections/part-schedule1/division-284/284-150.md: line 34: extraction glyph 'ê': |  | Tax on | ê | setting amount | ú |
  taa-1953/sections/part-schedule1/division-284/284-150.md: line 36: extraction glyph 'ê': | ca | pital gain | Origina ê ë | l reset cost base asset setting amo
  taa-1953/sections/part-schedule1/division-284/284-150.md: line 38: 'adj|usted' = 'adjusted' cut across cells 1|2: | adj | usted reset c | ost base ass | et se
  taa-1953/sections/part-schedule1/division-284/284-160.md: line 44: row ends on bare connector: | 1 | having regard to any relevant matters, it is reasonable t
  taa-1953/sections/part-schedule1/division-284/284-80.md: line 31: extraction glyph 'ê': |  | Tax on | ê | setting amount | ú |
  taa-1953/sections/part-schedule1/division-284/284-80.md: line 33: extraction glyph 'ê': | ca | pital gain | Origina ê ë | l reset cost base asset setting amo
  taa-1953/sections/part-schedule1/division-284/284-80.md: line 35: 'adj|usted' = 'adjusted' cut across cells 1|2: | adj | usted reset c | ost base ass | et se
  taa-1953/sections/part-schedule1/division-288/288-80.md: line 40: extraction glyph '´': |  | *Corporate tax rate ´ | Excess mentioned ´ | interests |
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 48: row ends on bare connector: | 2 | any entity, court or tribunal | is for the purpose of the
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 53: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1 
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 69: row ends on bare connector: | 6 | any entity | is for the purpose of enabling the entity to
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 71: row ends on bare connector: | 7 | the Secretary of the Department | (a) is of information t
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 80: row ends on bare connector: | 8 | any board or member of a board | is for the purpose of pe
  taa-1953/sections/part-schedule1/division-355/355-50.md: line 93: row ends on bare connector: | 11 | a payer (within the meaning of Part VA of the Income Tax
  taa-1953/sections/part-schedule1/division-355/355-55.md: line 45: row ends on bare connector: | 2 | the Minister | (a) is about an entity; and |
  taa-1953/sections/part-schedule1/division-355/355-55.md: line 79: row ends on bare connector: | 6 | a Minister responsible for: | (a) is of information conta
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 43: row ends on bare connector: | 5        ( | a) the *Student Assistance          is for Secre
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 58: row ends on bare connector: | 5AA | the Secretary of the Department | is for the purpose of
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 128: row ends on bare connector: | 7 | an individual who is or was an employee (within the mean
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 134: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 229: row ends on bare connector: | 12 | An employer (within the meaning of the Superannuation G
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 256: row ends on bare connector: | 8 | the Secretary of the Department | (a) is of information 
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 304: row ends on bare connector: | 3 | an authority of a State or Territory that administers a 
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 318: row ends on bare connector: | 3 | the Australian Renewable Energy Agency | (a) is of infor
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 333: row ends on bare connector: | 2A       t | he Electoral Commissioner | (a) is of informati
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 334: row ends on bare connector: | ( | within the meaning of the | obtained by, the Commissione
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 336: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 356: row ends on bare connector: | 5 | the Fair Work Ombudsman | (a) is of the fact of an entit
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 363: row ends on bare connector: | 5AB | (a) the Fair Work Commission | (a) is of information t
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 378: row ends on bare connector: | 6 | (a) the Commissioner of the Australian Charities and Not
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 390: row ends on bare connector: | 6A | the Secretary of the Department | is for the purpose of
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 392: row ends on bare connector: | 7 | the Secretary of a Department administered by a Minister
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 413: row ends on bare connector: | 8 | a *foreign government agency of | (a) is of information 
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 416: 'defini|tion' = 'definition' cut across cells 1|2: | *For defini | tion, see section 995-1
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 434: row ends on bare connector: | 9 | an *Australian government | is for the purpose of admini
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 437: row ends on bare connector: | 10A | an *Australian government agency | (a) is of informati
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 443: row ends on bare connector: | 12 | an *Australian government | is for the purpose of admin
  taa-1953/sections/part-schedule1/division-355/355-65.md: line 503: row ends on bare connector: | 15 | a professional disciplinary body | (a) is of informatio
  taa-1953/sections/part-schedule1/division-355/355-70.md: line 49: row ends on bare connector: | 1 | an *authorised law enforcement agency officer, or a court
  taa-1953/sections/part-schedule1/division-355/355-70.md: line 57: row ends on bare connector: | 3 | a *Project Wickenby officer, or a court or tribunal | (a)
  taa-1953/sections/part-schedule1/division-355/355-70.md: line 60: row ends on bare connector: | 4 | a *taskforce officer of a | (a) is for or in connection w
  taa-1953/sections/part-schedule1/division-355/355-70.md: line 72: row ends on bare connector: | 6 | one or more of the following bodies: | is for the purpose
  taa-1953/sections/part-schedule1/division-359/359-50.md: line 33: row ends on bare connector: | Item | If the Commissioner, during | The 60 day period is ext
  taa-1953/sections/part-schedule1/division-359/359-50.md: line 41: row ends on bare connector: | Item | If the Commissioner, during | The 60 day period is ext
  taa-1953/sections/part-schedule1/division-362/362-50.md: line 33: row ends on bare connector: | Item | If *Industry Innovation and | The 60 day period is ext
  taa-1953/sections/part-schedule1/division-389/389-5.md: line 49: row ends on bare connector: | 2A | An amount that consists of either or both of the followi
  taa-1953/sections/part-schedule1/division-396/396-55.md: line 41: row ends on bare connector: | 2 | a government related entity (within the meaning of the *G
  taa-1953/sections/part-schedule1/division-396/396-55.md: line 47: row ends on bare connector: | 3 | a State or Territory | the transfer of a freehold or leas
  taa-1953/sections/part-schedule1/division-396/396-55.md: line 120: row ends on bare connector: | 14 | an entity that makes a *supply of an information techno
  taa-1953/sections/part-schedule1/division-45/45-230.md: line 29: extraction glyph 'é': |  | é | Rate | ´ Your *instalment income ù + | Credit |
  taa-1953/sections/part-schedule1/division-45/45-230.md: line 32: row ends on bare connector: | r | ate di | screpanc | y means the difference between th | e
  taa-1953/sections/part-schedule1/division-45/45-230.md: line 33: 'les|ser' = 'lesser' cut across cells 2|3: | t | he les | ser of: |  |  |
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 49: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your ins
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 51: row ends on bare connector: | 1 | the first in that income year for which you are liable to
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 59: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your ins
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 61: row ends on bare connector: | 2 | the second in that income year for which you are liable t
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 76: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your ins
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 78: row ends on bare connector: | 4 | the fourth in that income year for which you are liable t
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 95: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your ins
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 133: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your in
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 171: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your in
  taa-1953/sections/part-schedule1/division-45/45-232.md: line 184: row ends on bare connector: | Item | If the *instalment | The acceptable amount of your in
  taa-1953/sections/part-schedule1/division-45/45-610.md: line 48: row ends on bare connector: | 4 | A variation GIC component is the *general interest charge
  taa-1953/sections/part-schedule1/division-45/45-610.md: line 62: row ends on bare connector: |  | For this component: | The amount of | The amount of |
  taa-1953/sections/part-schedule1/division-45/45-935.md: line 30: row ends on bare connector: | 2 | Subsection 45-885(2) | A reference to paragraph 45-760(2)
  itaa-1936/sections/part-iii/division-1/23AF.md: line 199: extraction glyph '´': |  | Apportionable ´  | Other taxable income |  |
  itaa-1936/sections/part-iii/division-1/23AF.md: line 202: row ends on bare connector: | A | pportionable deductions | means the number of whole | do
  itaa-1936/sections/part-iii/division-1/23AF.md: line 203: 'taxpa|yer' = 'taxpayer' cut across cells 3|4: | t | he apportionable deduct | ions allowa
  itaa-1936/sections/part-iii/division-1/23AF.md: line 205: 'o|ther' = 'other' cut across cells 1|2: | O | ther taxable income mea | ns the amount tha
  itaa-1936/sections/part-iii/division-1/23AF.md: line 206: 'p|aragraph' = 'paragraph' cut across cells 1|2: | p | aragraph (17A)(f), woul | d be repr
  itaa-1936/sections/part-iii/division-1/23AF.md: line 207: 't|axable' = 'taxable' cut across cells 1|2: | t | axable income in subsec | tion (17A). |
  itaa-1936/sections/part-iii/division-1/23AF.md: line 208: 'n|otional' = 'notional' cut across cells 1|2: | N | otional gross taxable i | ncome means
  itaa-1936/sections/part-iii/division-1/23AF.md: line 209: 't|axable' = 'taxable' cut across cells 3|4: | i | n the amount that would | have been the
  itaa-1936/sections/part-iii/division-1/23AG.md: line 133: extraction glyph '´': |  | Apportionable ´  | Other taxable income |  |
  itaa-1936/sections/part-iii/division-5/94.md: line 131: row ends on bare connector: |  | Item | production income | Value of A |
  itaa-1936/sections/part-iii/division-5/94.md: line 138: row ends on bare connector: |  | Item | production income | Value of A |
  itaa-1936/sections/part-iii/division-5/94.md: line 140: 'th|e' = 'the' cut across cells 3|4: | B | is the n | umber of whole dollars in th | e eli
  itaa-1936/sections/part-iii/division-5/94.md: line 141: 'th|e' = 'the' cut across cells 3|4: | C | is the n | umber of whole dollars in th | e tax
  itaa-1936/sections/part-iii/division-5/94.md: line 142: row ends on bare connector: | o | f the tax | payer of the year of income; | and |
  itaa-1936/sections/part-iii/division-5/94.md: line 143: 'th|e' = 'the' cut across cells 3|4: | D | is the n | umber of whole dollars in th | e dif
  itaa-1936/sections/part-iii/division-5/94.md: line 144: 'b|etween' = 'between' cut across cells 1|2: | b | etween th | e taxpayer's primary produc
  itaa-1936/sections/part-iii/division-5/94.md: line 145: 'ye|ar' = 'year' cut across cells 2|3: | f | or the ye | ar of income and the taxpaye | r'
  itaa-1936/sections/part-iii/division-5/94.md: line 146: row ends on bare connector: | p | rimary pr | oduction income for that yea | r; and |
  itaa-1936/sections/part-iii/division-6aaa/102AAM.md: line 82: extraction glyph 'é': |  | é Taxpayer's portion of | ´ | Applicable ù – FITO |
  itaa-1936/sections/part-iii/division-6aaa/102AAM.md: line 107: extraction glyph 'é': |  | é Taxpayer's portion of | ´ | Applicable ù – FITO |
  itaa-1936/sections/part-iii/division-6aaa/102AAM.md: line 126: extraction glyph '´': |  | the distributed amount | ´ | Applicable |
  itaa-1936/sections/part-iii/division-6aaa/102AAZD.md: line 94: extraction glyph 'ê': |  | of the transfer | êë | úû |
  itaa-1936/sections/part-iii/division-6aaa/102AAZD.md: line 101: extraction glyph 'é': |  | Adjusted net | é Weighted | ù |
  itaa-1936/sections/part-iii/division-6aaa/102AAZD.md: line 103: extraction glyph '´': | w | orth of trust   ´ estate | ê statutory interest êë    rate + 5
  itaa-1936/sections/part-iii/division-7a/109E.md: line 105: extraction glyph 'ç': |  | ç | 1 | ÷ |
  itaa-1936/sections/part-iii/division-7a/109E.md: line 107: extraction glyph 'ç': | 1 – | ç çç 1 +     Cur è     benchma | rent year's rk interest rat
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 29: extraction glyph '´': | (d), 121AK(1)( | c) or (d) or 121AL(1)(c) or (d).                  
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 54: 'bon|us' = 'bonus' cut across cells 1|2: | is a bon | us share mentioned in Division 8 of  
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 55: extraction glyph '´': | former P | art IIIA and any of the Total demu | ´              amou
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 57: row ends on bare connector: | shares m | entioned in that Division. | shares ; and |
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 108: extraction glyph '´': |  | in such a share, where the share is a bonus | ´ | Net tangible 
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 111: row ends on bare connector: | to thi | s item, if any of the original shares              
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 112: 'mentio|ned' = 'mentioned' cut across cells 1|2: | mentio | ned in that section is a demut
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 181: 'c|alled' = 'called' cut across cells 1|2: | share, it is c | alled a demutualisation orig
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 184: 'compan|y' = 'company' cut across cells 1|2: | holding compan | y are those mentioned in |
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 188: 'atta|ching' = 'attaching' cut across cells 1|2: | The rights atta | ching to the special 
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 189: 'bec|ome' = 'become' cut across cells 1|2: | the trustee bec | ome the same as those attac
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 194: 'th|e' = 'the' cut across cells 1|2: | The trustee (th | e disposer):                     
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 202: row ends on bare connector: | share) | in the company as mentioned in            (b) to ha
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 203: row ends on bare connector: | paragr | aph 121AG(1)(d), 121AI(1)(f),                    th
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 204: 'o|ther' = 'other' cut across cells 2|3: | 121AJ( | 1)(d), 121AK(1)(d) or 121AL(1)(d);    
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 205: row ends on bare connector: | or | 2. The modifications in i | tem 5 apply to the sale of 
  itaa-1936/sections/part-iii/division-9aa/121AS.md: line 256: extraction glyph '´': |  | demutualisation method concerned | ´ | on behalf of, persons in
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 24: row ends on bare connector: | 1 | Event described in item 1 of Table 1. | No amount is incl
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 45: row ends on bare connector: | 3 | Event that would be described in item 5 of Table 1 if | 1
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 78: row ends on bare connector: | 4 | Event that would be described in item 6 of Table 1 if | 1
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 114: row ends on bare connector: | 7 | Event that would be described in item 9 of Table 1 if th
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 125: 'woul|d' = 'would' cut across cells 1|2: | 8      Event that woul | d be described in item
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 127: 'mentione|d' = 'mentioned' cut across cells 1|2: | shares mentione | d in section 130-20 (
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 129: 'referen|ces' = 'references' cut across cells 1|2: | instead referen | ces to bonus shares
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 130: 'se|ction' = 'section' cut across cells 1|2: | mentioned in se | ction 6BA. |  |
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 132: 'busin|ess' = 'business' cut across cells 1|2: | insurance busin | ess of a life insurance
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 135: row ends on bare connector: | 10     An ordinary sha | re is issued or distributed to a pe
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 136: 'th|e' = 'the' cut across cells 2|3: | in the policyho | lder/member group as mentioned in
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 159: 'aff|iliate' = 'affiliate' cut across cells 1|2: | mutual aff | iliate company. |  |
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 160: 'bef|ore' = 'before' cut across cells 1|2: | Immediately bef | ore the demutualisation res
  itaa-1936/sections/part-iii/division-9aa/121AT.md: line 174: row ends on bare connector: | 13 | A resolution is passed to proceed with the | No frankin
  itaa-1936/sections/part-iv/division-unknown/170B.md: line 63: row ends on bare connector: | 1 | The statement is made in a return lodged on or before 14 
  itaa-1936/sections/part-iv/division-unknown/170B.md: line 68: row ends on bare connector: | 3 | All of the following apply: | The statement relates to th
  itaa-1936/sections/part-iv/division-unknown/171A.md: line 53: row ends on bare connector: | 3 | The taxpayer had a tax loss in a nil | The Commissioner c
  itaa-1936/sections/part-iv/division-unknown/171A.md: line 68: row ends on bare connector: | 4 | (a) the taxpayer had a tax loss in a nil year, some or al
  itaa-1936/sections/part-x/division-7/419.md: line 26: row ends on bare connector: | 1 | A resident of a listed country at the time of the trigger
  itaa-1936/sections/part-x/division-7/419.md: line 37: row ends on bare connector: | 3 | A resident of an unlisted country at the time of the trig
  itaa-1936/sections/part-x/division-8/446.md: line 66: extraction glyph '´': | Adjusted passive ´ | outsta | nding claims | amount |
  itaa-1936/sections/part-x/division-8/446.md: line 67: 'tot|al' = 'total' cut across cells 2|3: | income | Tot | al assets |  |
  itaa-1936/sections/part-x/division-8/446.md: line 79: extraction glyph 'é': |  | é | ù | é | ù |
  itaa-1936/sections/schedule-2f/division-265/265-10.md: line 24: 'w|ork' = 'work' cut across cells 1|2: | w | ork out its net | from earlier               m
  itaa-1936/sections/schedule-2f/division-265/265-10.md: line 25: row ends on bare connector: | i | ncome and tax loss for the | income years -certain amount
  itaa-1936/sections/schedule-2f/division-266/266-10.md: line 21: 'unli|sted' = 'unlisted' cut across cells 3|4: | Subdivision | 266-C | 266-D               
  itaa-1936/sections/schedule-2f/division-266/266-10.md: line 23: 'u|nlisted' = 'unlisted' cut across cells 1|2: | U | nlisted widely            L | isted wi
  itaa-1936/sections/schedule-2f/division-266/266-10.md: line 27: row ends on bare connector: |  | Change in | some cases end | trading with |
  itaa-1936/sections/schedule-2f/division-266/266-10.md: line 29: 'ow|nership' = 'ownership' cut across cells 1|2: | ow | nership of the trust * | of income 
  itaa-1936/sections/schedule-2f/division-266/266-145.md: line 24: 't|ogether' = 'together' cut across cells 1|2: | t | ogether with change in ownership happe
  itaa-1936/sections/schedule-2f/division-266/266-145.md: line 25: row ends on bare connector: | b | etween earlier income          t | ogether with change in
  itaa-1936/sections/schedule-2h/division-326/326-145.md: line 40: extraction glyph 'ç': |  | ç | + | ÷´ |
  itaa-1936/sections/schedule-2h/division-326/326-90.md: line 40: extraction glyph 'ç': |  | ç Undeducted | value | ÷ |
  sis-1993/sections/part-1/division-1/6.md: line 34: row ends on bare connector: | 7 | Part 3, to the extent it is not covered by item 7A, 8 or 
  sis-1993/sections/part-1/division-1/6.md: line 68: row ends on bare connector: | 14 | Part 4 | accounts, audit and | (a) the Commissioner of |
  sis-1993/sections/part-1/division-1/6.md: line 72: row ends on bare connector: | 15 | Part 5, to the extent it is | notices about | (a) the Co
  sis-1993/sections/part-1/division-1/6.md: line 98: row ends on bare connector: | 17 | Part 6, to the extent it is | governing rules of | (a) A
  sis-1993/sections/part-1/division-1/6.md: line 114: row ends on bare connector: | 20 | Section 54A | prescribed covenants | (a) the Commission
  sis-1993/sections/part-1/division-1/6.md: line 119: row ends on bare connector: | 21A | Part 6A, to the extent it is not covered by item 21B, 
  sis-1993/sections/part-1/division-1/6.md: line 132: row ends on bare connector: | 22 | Part 7, to the extent it is not covered by items 23 to 
  sis-1993/sections/part-1/division-1/6.md: line 135: row ends on bare connector: | 23 | Sections 62 and 68 | sole purpose test; | (a) the Commi
  sis-1993/sections/part-1/division-1/6.md: line 141: row ends on bare connector: | 26 | Section 68B | promotion of illegal early release scheme
  sis-1993/sections/part-1/division-1/6.md: line 146: row ends on bare connector: | extent 27 | Part 8 | in-house asset rules | (a) the Commissi
  sis-1993/sections/part-1/division-1/6.md: line 162: row ends on bare connector: | 33 | Part 12, to the extent it is not covered by items 34 to
  sis-1993/sections/part-1/division-1/6.md: line 165: row ends on bare connector: | 34 | Sections 101 and 103 | dispute resolution | (a) the Com
  sis-1993/sections/part-1/division-1/6.md: line 171: row ends on bare connector: | extent 35 | Section 105 | duty to keep reports | (a) ASIC, t
  sis-1993/sections/part-1/division-1/6.md: line 186: row ends on bare connector: | 37 | Part 14 | other provisions applying to superannuation e
  sis-1993/sections/part-1/division-1/6.md: line 189: row ends on bare connector: | 38 | Part 15, to the extent it | standards for trustees, | (
  sis-1993/sections/part-1/division-1/6.md: line 193: row ends on bare connector: | 39 | Section 126K | disqualified persons | (a) the Commissio
  sis-1993/sections/part-1/division-1/6.md: line 204: row ends on bare connector: | 40 | Part 16, to the extent it is not covered by items 41 to
  sis-1993/sections/part-1/division-1/6.md: line 213: row ends on bare connector: | 43 | Division 2 of Part 16 | actuaries and auditors—obligati
  sis-1993/sections/part-1/division-1/6.md: line 223: row ends on bare connector: | 43A | Sections 130D and 130E | disqualifying and removing ac
  sis-1993/sections/part-1/division-1/6.md: line 231: row ends on bare connector: | 45 | Part 17, to the extent it is not covered by item 46 of 
  sis-1993/sections/part-1/division-1/6.md: line 239: row ends on bare connector: | 50 | Part 21 | civil and criminal consequences of contraveni
  sis-1993/sections/part-1/division-1/6.md: line 257: row ends on bare connector: | 53 | Part 24, to the extent it is not covered by item 54 of 
  sis-1993/sections/part-1/division-1/6.md: line 272: row ends on bare connector: | 59 | Part 25A, to the extent it is not covered by item 60 of
  sis-1993/sections/part-1/division-1/6.md: line 275: row ends on bare connector: | 60 | Divisions 1 and 3A of | tax file numbers | the Commissi
  sis-1993/sections/part-32/division-unknown/381.md: line 35: row ends on bare connector: | Superannuation Industry | 78, 1993 | 30 Nov | s 30–116, 118–1
  sis-1993/sections/part-32/division-unknown/381.md: line 354: row ends on bare connector: | Tax Laws Amendment | 56, 2010 | 3 June 2010 | Sch 1 (items 6
  sis-1993/sections/part-32/division-unknown/381.md: line 386: row ends on bare connector: | Tax Laws Amendment | 41, 2011 | 27 June | Sch 2 and Sch 3 | 
  sis-1993/sections/part-32/division-unknown/381.md: line 683: row ends on bare connector: | Financial Sector Reform | 135, 2020 | 17 Dec | Sch 8: 1 July
  sis-1993/sections/part-32/division-unknown/381.md: line 767: row ends on bare connector: | Treasury Laws | 67, 2024 | 9 July 2024 | Sch 1 (items 1–3) a
  sis-1993/sections/part-8/division-3/82.md: line 34: extraction glyph 'é': | é Market value ratio of fund's | ù | Value of fund's |
  sis-1993/sections/part-8/division-3/82.md: line 36: extraction glyph 'ê': | êin-house assets as at the end of – 5% | ú           ´ asset | s as
  sis-1993/sections/part-8/division-3/82.md: line 37: extraction glyph 'ë': | ëê     that year of income | úû | year of income |

full JSON: /tmp/corpus_scan_20260826.json

exec
/bin/bash -lc "python3 - <<'PY'
import json,collections
fs=json.load(open('/tmp/corpus_scan_20260826.json'))
for a in sorted({f['path'].split('/')[0] for f in fs}):
 c=collections.Counter(f['class'] for f in fs if f['path'].split('/')[0]==a)
 files={f['path'] for f in fs if f['path'].split('/')[0]==a}
 print(a,len(files),dict(c),sum(c.values()))
PY
for a in itaa-1997 gst-1999 sis-1993 taa-1953 fbt-1986 itaa-1936; do echo \"ACT "'$a"; find "data/$a/raw" -maxdepth 1 -type f -printf '"'%f\\n' | sort; done
find /home/harrison/legislation-explorer-staging/source -maxdepth 2 -type f -printf '%P\\n' | sort | rg '"'^(itaa-1997|gst-1999|sis-1993|taa-1953|fbt-1986|itaa-1936)/'"'" in /home/harrison/legislation-explorer
 succeeded in 0ms:
fbt-1986 13 {'C11_table_glyph': 45, 'C11_table_midword': 8, 'C11_table_truncated': 21} 74
gst-1999 23 {'C11_table_truncated': 21, 'C11_table_midword': 15, 'C11_table_glyph': 29} 65
itaa-1936 17 {'C11_table_glyph': 18, 'C11_table_truncated': 25, 'C11_table_midword': 33} 76
itaa-1997 133 {'C11_table_truncated': 340, 'C11_table_midword': 37, 'C11_table_glyph': 41} 418
sis-1993 3 {'C11_table_truncated': 29, 'C11_table_glyph': 3} 32
taa-1953 27 {'C11_table_glyph': 16, 'C11_table_midword': 22, 'C11_table_truncated': 68} 106
ACT itaa-1997
vol01.txt
vol02.txt
vol03.txt
vol04.txt
vol05.txt
vol06.txt
vol07.txt
vol08.txt
vol09.txt
vol10.txt
vol11.txt
vol12.txt
ACT gst-1999
vol01.txt
vol02.txt
ACT sis-1993
part1.txt
part2.txt
ACT taa-1953
vol01.txt
vol02.txt
vol03.txt
vol04.txt
ACT fbt-1986
part1.txt
part2.txt
ACT itaa-1936
vol01.txt
vol02.txt
vol03.txt
vol04.txt
vol05.txt
vol06.txt
vol07.txt
fbt-1986/part1.pdf
fbt-1986/part2.pdf
itaa-1936/C2026C00165VOL01.pdf
itaa-1936/C2026C00165VOL02.pdf
itaa-1936/C2026C00165VOL03.pdf
itaa-1936/C2026C00165VOL04.pdf
itaa-1936/C2026C00165VOL05.pdf
itaa-1936/C2026C00165VOL06.pdf
itaa-1936/C2026C00165VOL07.pdf
itaa-1997/C2026C00122VOL01.pdf
itaa-1997/C2026C00122VOL02.pdf
itaa-1997/C2026C00122VOL03.pdf
itaa-1997/C2026C00122VOL04.pdf
itaa-1997/C2026C00122VOL05.pdf
itaa-1997/C2026C00122VOL06.pdf
itaa-1997/C2026C00122VOL07.pdf
itaa-1997/C2026C00122VOL08.pdf
itaa-1997/C2026C00122VOL09.pdf
itaa-1997/C2026C00122VOL10.pdf
itaa-1997/C2026C00122VOL11.pdf
itaa-1997/C2026C00122VOL12.pdf
sis-1993/part1.pdf
sis-1993/part2.pdf
taa-1953/vol01.pdf
taa-1953/vol02.pdf
taa-1953/vol03.pdf
taa-1953/vol04.pdf

exec
/bin/bash -lc 'for a in itaa-1997 gst-1999 sis-1993 taa-1953 fbt-1986 itaa-1936; do echo "ACT $a frontmatter/tree"; rg -h '"'"'^compilation_no:'"' \"data/"'$a/sections" -g '"'*.md' | sort | uniq -c; rg '\"compilation_no\"' \"data/"'$a/tree.json" | head -1; echo raw; rg -n -m3 -i '"'Compilation No\\.?|Compilation date|This compilation' \"data/"'$a/raw"; done' in /home/harrison/legislation-explorer
 succeeded in 0ms:
ACT itaa-1997 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 266,
raw
data/itaa-1997/raw/vol05.txt:5:Compilation No. 263
data/itaa-1997/raw/vol05.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol05.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol07.txt:5:Compilation No. 263
data/itaa-1997/raw/vol07.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol07.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol04.txt:5:Compilation No. 263
data/itaa-1997/raw/vol04.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol04.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol03.txt:5:Compilation No. 263
data/itaa-1997/raw/vol03.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol03.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol09.txt:5:Compilation No. 263
data/itaa-1997/raw/vol09.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol09.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol01.txt:5:Compilation No. 263
data/itaa-1997/raw/vol01.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol01.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol11.txt:5:Compilation No. 263
data/itaa-1997/raw/vol11.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol11.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol02.txt:5:Compilation No. 263
data/itaa-1997/raw/vol02.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol02.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol12.txt:5:Compilation No. 263
data/itaa-1997/raw/vol12.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol12.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol08.txt:5:Compilation No. 263
data/itaa-1997/raw/vol08.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol08.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol06.txt:5:Compilation No. 263
data/itaa-1997/raw/vol06.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol06.txt:11:This compilation is in 12 volumes
data/itaa-1997/raw/vol10.txt:5:Compilation No. 263
data/itaa-1997/raw/vol10.txt:7:Compilation date:            1 April 2026
data/itaa-1997/raw/vol10.txt:11:This compilation is in 12 volumes
ACT gst-1999 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 96,
raw
data/gst-1999/raw/vol01.txt:8:Compilation No. 96
data/gst-1999/raw/vol01.txt:10:Compilation date:            1 January 2026
data/gst-1999/raw/vol01.txt:14:This compilation is in 2 volumes
data/gst-1999/raw/vol02.txt:8:Compilation No. 96
data/gst-1999/raw/vol02.txt:10:Compilation date:            1 January 2026
data/gst-1999/raw/vol02.txt:14:This compilation is in 2 volumes
ACT sis-1993 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 126,
raw
data/sis-1993/raw/part2.txt:8:Compilation No. 126
data/sis-1993/raw/part2.txt:10:Compilation date:            9 January 2025
data/sis-1993/raw/part2.txt:14:This compilation is in 2 volumes
data/sis-1993/raw/part1.txt:8:Compilation No. 126
data/sis-1993/raw/part1.txt:10:Compilation date:            9 January 2025
data/sis-1993/raw/part1.txt:14:This compilation is in 2 volumes
ACT taa-1953 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 222,
raw
data/taa-1953/raw/vol01.txt:7:Compilation No. 222
data/taa-1953/raw/vol01.txt:9:Compilation date:            1 April 2026
data/taa-1953/raw/vol01.txt:13:This compilation is in 4 volumes
data/taa-1953/raw/vol03.txt:7:Compilation No. 222
data/taa-1953/raw/vol03.txt:9:Compilation date:            1 April 2026
data/taa-1953/raw/vol03.txt:13:This compilation is in 4 volumes
data/taa-1953/raw/vol04.txt:7:Compilation No. 222
data/taa-1953/raw/vol04.txt:9:Compilation date:            1 April 2026
data/taa-1953/raw/vol04.txt:13:This compilation is in 4 volumes
data/taa-1953/raw/vol02.txt:7:Compilation No. 222
data/taa-1953/raw/vol02.txt:9:Compilation date:            1 April 2026
data/taa-1953/raw/vol02.txt:13:This compilation is in 4 volumes
ACT fbt-1986 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 96,
raw
data/fbt-1986/raw/part2.txt:7:Compilation No. 96
data/fbt-1986/raw/part2.txt:9:Compilation date:            1 April 2025
data/fbt-1986/raw/part2.txt:13:This compilation is in 2 volumes
data/fbt-1986/raw/part1.txt:7:Compilation No. 96
data/fbt-1986/raw/part1.txt:9:Compilation date:            1 April 2025
data/fbt-1986/raw/part1.txt:13:This compilation is in 2 volumes
ACT itaa-1936 frontmatter/tree
     12 
      1   --auto-hybrid-regex             (DEPRECATED) Use PCRE2 if appropriate.
      1   --binary                        Search binary files.
      1   --block-buffered                Force block buffering.
      1   --color=WHEN                    When to use color.
      1   --colors=COLOR_SPEC             Configure color settings and styles.
      1   --column                        Show column numbers.
      1   --context-separator=SEP         Set the separator for contextual chunks.
      1   --count-matches                 Show count of every match for each file.
      1   --crlf                          Use CRLF line terminators (nice for Windows).
      1   --debug                         Show debug messages.
      1   --dfa-size-limit=NUM            The upper size limit of the regex DFA.
      1   --engine=ENGINE                 Specify which regex engine to use.
      1   --field-context-separator=SEP   Set the field context separator.
      1   --field-match-separator=SEP     Set the field match separator.
      1   --files                         Print each file that would be searched.
      1   --files-without-match           Print the paths that contain zero matches.
      1   --generate=KIND                 Generate man pages and completion scripts.
      1   --glob-case-insensitive         Process all glob patterns case insensitively.
      1   --heading                       Print matches grouped by each file.
      1   --hostname-bin=COMMAND          Run a program to get this system's hostname.
      1   --hyperlink-format=FORMAT       Set the format of hyperlinks.
      1   --iglob=GLOB                    Include/exclude paths case insensitively.
      1   --ignore-file-case-insensitive  Process ignore files case insensitively.
      1   --ignore-file=PATH              Specify additional ignore files.
      1   --include-zero                  Include zero matches in summary output.
      1   --json                          Show search results in a JSON Lines format.
      1   --line-buffered                 Force line buffering.
      1   --max-columns-preview           Show preview for lines exceeding the limit.
      1   --max-filesize=NUM              Ignore files larger than NUM in size.
      1   --mmap                          Search with memory maps when possible.
      1   --multiline-dotall              Make '.' match line terminators.
      1   --no-config                     Never read configuration files.
      1   --no-ignore                     Don't use ignore files.
      1   --no-ignore-dot                 Don't use .ignore or .rgignore files.
      1   --no-ignore-exclude             Don't use local exclusion files.
      1   --no-ignore-files               Don't use --ignore-file arguments.
      1   --no-ignore-global              Don't use global ignore files.
      1   --no-ignore-messages            Suppress gitignore parse error messages.
      1   --no-ignore-parent              Don't use ignore files in parent directories.
      1   --no-ignore-vcs                 Don't use ignore files from source control.
      1   --no-messages                   Suppress some error messages.
      1   --no-pcre2-unicode              (DEPRECATED) Disable Unicode mode for PCRE2.
      1   --no-require-git                Use .gitignore outside of git repositories.
      1   --no-unicode                    Disable Unicode mode.
      1   --null-data                     Use NUL as a line terminator.
      1   --one-file-system               Skip directories on other file systems.
      1   --passthru                      Print both matching and non-matching lines.
      1   --path-separator=SEP            Set the path separator for printing paths.
      1   --pcre2-version                 Print the version of PCRE2 that ripgrep uses.
      1   --pre-glob=GLOB                 Include or exclude files from a preprocessor.
      1   --pre=COMMAND                   Search output of COMMAND for each PATH.
      1   --regex-size-limit=NUM          The size limit of the compiled regex.
      1   --sort-files                    (DEPRECATED) Sort results by file path.
      1   --sort=SORTBY                   Sort results in ascending order.
      1   --sortr=SORTBY                  Sort results in descending order.
      1   --stats                         Print statistics about the search.
      1   --stop-on-nonmatch              Stop searching after a non-match.
      1   --trace                         Show trace messages.
      1   --trim                          Trim prefix whitespace from matches.
      1   --type-add=TYPESPEC             Add a new glob for a file type.
      1   --type-clear=TYPE               Clear globs for a file type.
      1   --type-list                     Show all supported file types.
      1   --vimgrep                       Print results in a vim compatible format.
      1   -., --hidden                    Search hidden files and directories.
      1   -0, --null                      Print a NUL byte after file paths.
      1   -A, --after-context=NUM         Show NUM lines after each match.
      1   -B, --before-context=NUM        Show NUM lines before each match.
      1   -C, --context=NUM               Show NUM lines before and after each match.
      1   -E, --encoding=ENCODING         Specify the text encoding of files to search.
      1   -F, --fixed-strings             Treat all patterns as literals.
      1   -H, --with-filename             Print the file path with each matching line.
      1   -I, --no-filename               Never print the path with each matching line.
      1   -L, --follow                    Follow symbolic links.
      1   -M, --max-columns=NUM           Omit lines longer than this limit.
      1   -N, --no-line-number            Suppress line numbers.
      1   -P, --pcre2                     Enable PCRE2 matching.
      1   -S, --smart-case                Smart case search.
      1   -T, --type-not=TYPE             Do not search files matching TYPE.
      1   -U, --multiline                 Enable searching across multiple lines.
      1   -V, --version                   Print ripgrep's version.
      1   -a, --text                      Search binary files as if they were text.
      1   -b, --byte-offset               Print the byte offset for each matching line.
      1   -c, --count                     Show count of matching lines for each file.
      1   -d, --max-depth=NUM             Descend at most NUM directories.
      1   -e, --regexp=PATTERN            A pattern to search for.
      1   -f, --file=PATTERNFILE          Search for patterns from the given file.
      1   -g, --glob=GLOB                 Include or exclude file paths.
      1   -h, --help                      Show help output.
      1   -i, --ignore-case               Case insensitive search.
      1   -j, --threads=NUM               Set the approximate number of threads to use.
      1   -l, --files-with-matches        Print the paths with at least one match.
      1   -m, --max-count=NUM             Limit the number of matching lines.
      1   -n, --line-number               Show line numbers.
      1   -o, --only-matching             Print only matched parts of a line.
      1   -p, --pretty                    Alias for colors, headings and line numbers.
      1   -q, --quiet                     Do not print anything to stdout.
      1   -r, --replace=TEXT              Replace matches with the given text.
      1   -s, --case-sensitive            Search case sensitively (default).
      1   -t, --type=TYPE                 Only search files matching TYPE.
      1   -u, --unrestricted              Reduce the level of "smart" filtering.
      1   -v, --invert-match              Invert matching.
      1   -w, --word-regexp               Show matches surrounded by word boundaries.
      1   -x, --line-regexp               Show matches surrounded by line boundaries.
      1   -z, --search-zip                Search in compressed files.
      1   <PATH>...   A file or directory to search.
      1   <PATTERN>   A regular expression used for searching.
      1   rg [OPTIONS] PATTERN [PATH ...]
      1 Andrew Gallant <jamslam@gmail.com>
      1 FILTER OPTIONS:
      1 INPUT OPTIONS:
      1 LOGGING OPTIONS:
      1 OTHER BEHAVIORS:
      1 OUTPUT MODES:
      1 OUTPUT OPTIONS:
      1 POSITIONAL ARGUMENTS:
      1 Project home page: https://github.com/BurntSushi/ripgrep
      1 SEARCH OPTIONS:
      1 USAGE:
      1 Use -h for short descriptions and --help for more details.
      1 a regex pattern. By default, ripgrep will respect gitignore rules and
      1 automatically skip hidden files/directories and binary files.
      1 ripgrep (rg) recursively searches the current directory for lines matching
      1 ripgrep 15.2.0 (rev e89fff89ac)
  "compilation_no": 191,
raw
data/itaa-1936/raw/vol05.txt:7:Compilation No. 191
data/itaa-1936/raw/vol05.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol05.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol01.txt:7:Compilation No. 191
data/itaa-1936/raw/vol01.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol01.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol06.txt:7:Compilation No. 191
data/itaa-1936/raw/vol06.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol06.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol07.txt:7:Compilation No. 191
data/itaa-1936/raw/vol07.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol07.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol02.txt:7:Compilation No. 191
data/itaa-1936/raw/vol02.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol02.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol03.txt:7:Compilation No. 191
data/itaa-1936/raw/vol03.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol03.txt:13:This compilation is in 7 volumes
data/itaa-1936/raw/vol04.txt:7:Compilation No. 191
data/itaa-1936/raw/vol04.txt:9:Compilation date:            1 April 2026
data/itaa-1936/raw/vol04.txt:13:This compilation is in 7 volumes

exec
/bin/bash -lc 'for a in itaa-1997 gst-1999 sis-1993 taa-1953 fbt-1986 itaa-1936; do echo "ACT $a"; rg --no-filename '"'"'^compilation_no:'"' \"data/"'$a/sections" -g '"'*.md' | sort | uniq -c; done
for p in /home/harrison/legislation-explorer-staging/source/itaa-1997/*01.pdf /home/harrison/legislation-explorer-staging/source/taa-1953/vol01.pdf /home/harrison/legislation-explorer-staging/source/fbt-1986/part1.pdf /home/harrison/legislation-explorer-staging/source/itaa-1936/*01.pdf /home/harrison/legislation-explorer-staging/source/sis-1993/part1.pdf; do echo \"PDF "'$p"; pdfinfo "$p" | rg '"'"'^(Title|CreationDate|ModDate|Pages)'"'; pdftotext -f 1 -l 3 \""'$p" - | rg -m3 -i '"'Compilation No\\.?|Compilation date|This compilation'; done" in /home/harrison/legislation-explorer
 succeeded in 292ms:
Title:           Income Tax Assessment Act 1997
CreationDate:    Tue Apr  7 11:37:00 2026 AEST
ModDate:         Fri Apr 10 09:31:33 2026 AEST
Pages:           421
Compilation No. 263
Compilation date:
This compilation is in 12 volumes
PDF /home/harrison/legislation-explorer-staging/source/taa-1953/vol01.pdf
ModDate:         Tue Apr 28 15:24:48 2026 AEST
Pages:           451
Compilation No. 222
Compilation date:
This compilation is in 4 volumes
PDF /home/harrison/legislation-explorer-staging/source/fbt-1986/part1.pdf
Title:           Fringe Benefits Tax Assessment Act 1986
CreationDate:    Tue Apr  1 13:09:00 2025 AEST
ModDate:         Tue Apr  1 13:11:45 2025 AEST
Pages:           242
Compilation No. 96
Compilation date:
This compilation is in 2 volumes
PDF /home/harrison/legislation-explorer-staging/source/itaa-1936/C2026C00165VOL01.pdf
Title:           Income Tax Assessment Act 1936
CreationDate:    Tue Apr 21 15:36:00 2026 AEST
ModDate:         Wed Apr 22 09:06:45 2026 AEST
Pages:           258
Compilation No. 191
Compilation date:
This compilation is in 7 volumes
PDF /home/harrison/legislation-explorer-staging/source/sis-1993/part1.pdf
Title:           Superannuation Industry (Supervision) Act 1993
CreationDate:    Sat Jan 11 14:01:00 2025 AEST
ModDate:         Sat Jan 11 14:23:51 2025 AEST
Pages:           428
Compilation No. 126
Compilation date:
This compilation is in 2 volumes

codex
The source-version audit found a critical blocker: the staging PDFs are not newer as the plan says. Their own first pages identify ITAA 1997 as compilation 263 (not 266), TAA 222 (not 225), FBT 96 (not 97), ITAA 1936 191 (not 192), and SIS 126. Thus the proposed ITAA-first source is stale and cannot lawfully rebuild the comp-266 corpus. I’m completing the scope-method and gate audit before issuing the verdict.
exec
/bin/bash -lc "python3 - <<'PY'
from pathlib import Path
orig_w,orig_m=Path.write_text,Path.mkdir
Path.write_text=lambda *a,**k: 0
Path.mkdir=lambda *a,**k: None
import scripts.scan_truncation_scope as s
s.main()
Path.write_text,Path.mkdir=orig_w,orig_m
PY
git status --short --branch
nl -ba scripts/scan_truncation_scope.py | sed -n '1,180p'
nl -ba .hermes/plans/2026-09-07_table-corruption-rebuild.md | sed -n '35,250p'" in /home/harrison/legislation-explorer
 succeeded in 8672ms:
C11_table_truncated findings: 504
  parser-side recoverable from repo raw : 338
  split at PDF page boundary (needs PDF): 117
  probe not located in raw              : 49

fbt-1986       total=  21  recoverable=  18  page_split=   2  not_found=   1
gst-1999       total=  21  recoverable=  16  page_split=   5  not_found=   0
itaa-1936      total=  25  recoverable=  13  page_split=   8  not_found=   4
itaa-1997      total= 340  recoverable= 238  page_split=  71  not_found=  31
sis-1993       total=  29  recoverable=  14  page_split=  12  not_found=   3
taa-1953       total=  68  recoverable=  39  page_split=  19  not_found=  10

--- example recoverable (parser-side) ---
  itaa-1997/sections/part-2-1/division-20/20-105.md:19 tail='more complicated than the' cont='applies in 2 acquire it and then dispose of it: usual case because it '
  itaa-1997/sections/part-2-1/division-20/20-105.md:28 tail='you dispose of an' cont='more leases of the car: disposal of the car before see section 20-145 '
  itaa-1997/sections/part-2-10/division-40/40-40.md:49 tail='The partnership and' cont='not any particular'
  itaa-1997/sections/part-2-10/division-40/40-95.md:252 tail='or, if there is' cont='To find definitions of asterisked terms, see the Dictionary, starting '
  itaa-1997/sections/part-2-10/division-43/43-140.md:24 tail='some time in the' cont='works begin works income year'
  itaa-1997/sections/part-2-10/division-43/43-140.md:29 tail='for the purpose of' cont='producing assessable income.'
  itaa-1997/sections/part-2-10/division-43/43-140.md:41 tail='some time in the' cont='works begin works income year'
  itaa-1997/sections/part-2-10/division-43/43-140.md:43 tail='for the purpose of' cont='producing assessable income.'

written: /home/harrison/legislation-explorer/.hermes/plans/cdn-0193-scope.json
## master...origin/master
 M .hermes/plans/2026-09-07_table-corruption-rebuild.md
?? .hermes/plans/cdn-0193-scope.json
?? .hermes/plans/codex-review-prompt-20260826.txt
?? .hermes/plans/opus-audit-prompt-20260825.txt
?? data/definitions_all.json.bak-2026-08-22
?? data/table_sections_inventory.json
?? data/table_sections_list.md
?? scripts/_cron_probe.py
?? scripts/_cron_probe2.py
?? scripts/_cron_probe3.py
?? scripts/_cron_probe4.py
?? scripts/_cron_probe5.py
?? scripts/_cron_probe6.py
?? scripts/_cron_probe7.py
?? scripts/_cron_probe8.py
?? scripts/_cron_probe9.py
?? scripts/_cron_probe_citidx.py
?? scripts/_cron_probe_cw.py
?? scripts/_cron_probe_linkage.py
?? scripts/_cron_probe_taa.py
?? scripts/_probe_graph.py
?? scripts/_probe_graph2.py
?? scripts/_probe_outcomes.py
?? scripts/_probe_rulings.py
?? scripts/_probe_section_index.py
?? scripts/_tmp_ingest_oecd.py
?? scripts/scan_truncation_scope.py
     1	#!/usr/bin/env python3
     2	"""Size the CDN-0193 C11_table_truncated class.
     3	
     4	For every C11_table_truncated finding, probe the act's raw extraction text
     5	(data/<act>/raw/*.txt) for the offending cell's tail. If the raw line that
     6	carries the tail CONTINUES onto a following raw line that is body text (not a
     7	page footer/header, not a fresh table row), the loss is parser-side and the
     8	text is recoverable from the repo raw. If the raw line also stops there, the
     9	row was split at a PDF page boundary and recovery needs the source PDF.
    10	"""
    11	from __future__ import annotations
    12	
    13	import json
    14	import re
    15	import sys
    16	from pathlib import Path
    17	
    18	REPO = Path("/home/harrison/legislation-explorer")
    19	DATA = REPO / "data"
    20	FINDINGS = Path("/tmp/corpus_scan_20260826.json")
    21	
    22	FOOTER = re.compile(
    23	    r"compilation no|authorised version|^\s*\d+\s*$|"
    24	    r"^\s*(income tax assessment act|taxation administration act|"
    25	    r"a new tax system|fringe benefits tax assessment act|"
    26	    r"superannuation industry \(supervision\) act)",
    27	    re.I,
    28	)
    29	# a fresh table row / header starts a new logical row, not a continuation
    30	NEWROW = re.compile(r"^\s*(item\b|\d+(\.\d+)*[A-Z]?\s|\(\w+\))", re.I)
    31	
    32	
    33	def norm(s: str) -> str:
    34	    s = re.sub(r"[*_`]", "", s)
    35	    s = re.sub(r"\s+", " ", s)
    36	    return s.strip()
    37	
    38	
    39	def raw_lines(act: str):
    40	    out = []
    41	    for p in sorted((DATA / act / "raw").glob("*.txt")):
    42	        for ln in p.read_text(errors="replace").splitlines():
    43	            out.append(norm(ln))
    44	    return out
    45	
    46	
    47	def main() -> int:
    48	    findings = json.loads(FINDINGS.read_text())
    49	    trunc = [f for f in findings if f["class"] == "C11_table_truncated"]
    50	
    51	    cache: dict[str, list[str]] = {}
    52	    stats = {"parser_side_recoverable": 0, "page_split": 0, "probe_not_found": 0}
    53	    per_act: dict[str, dict] = {}
    54	    detail_examples: dict[str, list[str]] = {k: [] for k in stats}
    55	
    56	    for f in trunc:
    57	        path = f["path"]  # e.g. itaa-1997/sections/...
    58	        act = path.split("/", 1)[0]
    59	        m = re.search(r"line (\d+)", f["detail"])
    60	        if not m:
    61	            continue
    62	        ln_no = int(m.group(1))
    63	        md = DATA / path
    64	        try:
    65	            md_line = md.read_text(errors="replace").splitlines()[ln_no - 1]
    66	        except Exception:
    67	            continue
    68	        cells = [c.strip() for c in md_line.strip().strip("|").split("|")]
    69	        if not cells:
    70	            continue
    71	        tail = norm(cells[-1])
    72	        probe = " ".join(tail.split()[-4:])
    73	        if not probe:
    74	            continue
    75	        if act not in cache:
    76	            cache[act] = raw_lines(act)
    77	        lines = cache[act]
    78	
    79	        hit_idx = None
    80	        for i in range(len(lines) - 1, -1, -1):
    81	            if lines[i].endswith(probe):
    82	                hit_idx = i
    83	                break
    84	        bucket = "probe_not_found"
    85	        if hit_idx is not None:
    86	            nxt = None
    87	            for j in range(hit_idx + 1, min(hit_idx + 4, len(lines))):
    88	                if lines[j]:
    89	                    nxt = j
    90	                    break
    91	            if nxt is None or FOOTER.search(lines[nxt]) or NEWROW.match(lines[nxt]):
    92	                bucket = "page_split"
    93	            else:
    94	                bucket = "parser_side_recoverable"
    95	                if len(detail_examples[bucket]) < 8:
    96	                    detail_examples[bucket].append(
    97	                        f"{path}:{ln_no} tail={probe!r} cont={lines[nxt][:70]!r}"
    98	                    )
    99	        stats[bucket] += 1
   100	        pa = per_act.setdefault(act, {"total": 0, "parser_side_recoverable": 0,
   101	                                      "page_split": 0, "probe_not_found": 0})
   102	        pa["total"] += 1
   103	        pa[bucket] += 1
   104	
   105	    print(f"C11_table_truncated findings: {len(trunc)}")
   106	    print(f"  parser-side recoverable from repo raw : {stats['parser_side_recoverable']}")
   107	    print(f"  split at PDF page boundary (needs PDF): {stats['page_split']}")
   108	    print(f"  probe not located in raw              : {stats['probe_not_found']}")
   109	    print()
   110	    for act, pa in sorted(per_act.items()):
   111	        print(f"{act:14s} total={pa['total']:4d}  recoverable={pa['parser_side_recoverable']:4d}"
   112	              f"  page_split={pa['page_split']:4d}  not_found={pa['probe_not_found']:4d}")
   113	    print()
   114	    print("--- example recoverable (parser-side) ---")
   115	    for e in detail_examples["parser_side_recoverable"]:
   116	        print("  " + e)
   117	
   118	    out = REPO / ".hermes/plans/cdn-0193-scope.json"
   119	    out.parent.mkdir(parents=True, exist_ok=True)
   120	    out.write_text(json.dumps({"stats": stats, "per_act": per_act}, indent=2))
   121	    print(f"\nwritten: {out}")
   122	    return 0
   123	
   124	
   125	if __name__ == "__main__":
   126	    sys.exit(main())
    35	## Evidence (manual, verified)
    36	
    37	- ITAA 115-30: raw vol03 shows a clean 3-col, 10-row table; committed .md has
    38	  rows split into blockquote shards + truncated cells; cron's WIP flatten
    39	  merged cells and lost text (row 2 ends `...replacement asset for a |`).
    40	- ITAA 109-55: raw vol03 clean; committed file's rows 9/15A/17 truncated.
    41	- GST 9-69/29-39/31-99: `*To find definitions of ast | erisked terms` — the
    42	  dictionary footnote itself is tableised and split.
    43	- FBT 135W/9: formula glyph garbage `ç 0.2 ´ Base value ´ were pr | ovided`.
    44	- Cron WIP (10 itaa files, uncommitted, timestamped 07:53) was **lossy**:
    45	  applied `apply_itaa_table_fixes.py` output which validated structure but not
    46	  content; files reverted to HEAD (snapshot in /tmp/cron-wip-tables-20260907/).
    47	
    48	## Why the existing repair tool is not enough
    49	
    50	`extract_itaa_tables_pdf.py` / `apply_itaa_table_fixes.py` (CDN-0171 era)
    51	reconstruct tables from PyMuPDF word x-positions. It fixed ~9 sections but the
    52	driver's `validate_md()` checks ONLY structural soundness (frontmatter, column
    53	counts) — never that the extracted text equals the PDF text. Lossy output
    54	passes. Any rebuild MUST gate on content fidelity, not just structure.
    55	
    56	## Approach — three-act rebuild, act-gated, content-verified
    57	
    58	### Phase 0 — tooling audit + fidelity gate (before touching corpus)
    59	
    60	1. For each act, inventory flagged files + locate source PDF volume mapping
    61	   (frontmatter `compilation_no` → staging source).
    62	2. **Source-version audit (CRITICAL — discovered 2026-09-07):**
    63	   | act       | corpus fm | repo raw (data/<act>/raw)      | staging raw has              | rebuild source |
    64	   |-----------|-----------|--------------------------------|------------------------------|----------------|
    65	   | itaa-1997 | 266       | comp **263** (STALE)           | comp266 vol01-12.pdf + .txt  | **comp266 PDFs** (word-pos extractor) |
    66	   | gst-1999  | 96        | vol01-02.txt comp 96 ✓         | vol01-02.txt comp 96         | repo txt (layout slicer) — no PDFs |
    67	   | sis-1993  | 126       | part1-2.txt comp 126 ✓         | part1-2.txt comp 126         | repo txt (layout slicer) — no PDFs |
    68	   | taa-1953  | 222       | vol01-04.txt comp 222 ✓        | comp225 PDFs (NEWER)         | repo txt 222 (or comp225 PDFs only if prose diff shows tables unchanged) |
    69	   | fbt-1986  | 96        | part1/2 + vol txt comp 96 ✓    | comp97 PDFs (NEWER)          | repo txt 96 (or comp97 PDFs only if prose diff shows tables unchanged) |
    70	   | itaa-1936 | 191       | vol01-07.txt comp 191 ✓        | comp192 vol01-07 PDFs (NEWER)| repo txt 191 (or comp192 PDFs only if prose diff shows tables unchanged) |
    71	   Only itaa-1997 has corpus-comp PDFs. All other acts' staging PDFs are ONE
    72	   comp newer than the corpus — do NOT rebuild from them blindly or the law
    73	   text can regress/advance (fbt 96→97, itaa36 191→192, taa 222→225 are real
    74	   comp jumps). Per flagged section: diff section prose between corpus file
    75	   and the newer comp's text; only if prose is identical AND the table region
    76	   text is identical may the newer PDF be used; otherwise fall back to the
    77	   layout slicer on the repo raw (comp matches corpus).
    78	3. Extend/extract tool with a **fidelity gate**: for every rebuilt table,
    79	   compare reconstructed cell text against the PDF page's own text layer
    80	   (normalised whitespace/punctuation, allow link-marker `*...*` stripping and
    81	   smartquote normalisation). Reject + record any table where coverage < 98%
    82	   or where reconstructed words are absent from the source page.
    83	   Calibrate against a KNOWN-GOOD table first (clean section should score
    84	   ≥99.5%); if the gate falsely rejects >2% of known-good cells, relax the
    85	   threshold or extend normalisation (asterisked-term italics, smart quotes,
    86	   [links](url) vs raw text — Kimi R7).
    87	4. **Fix the extractor's known defects BEFORE scaling (Kimi R3-R6, R10; same
    88	   defects found by main-agent read):**
    89	   - R4/page-break continuation: `collect_tables()` merge (line ~312) only
    90	     joins blocks with identical headers; a row that begins on page P and
    91	     continues on P+1 is truncated. Detect same item number as last row of
    92	     block N / first row of block N+1 and REJOIN cell text — single biggest
    93	     truncation cause.
    94	   - R5/55pt row cap: `build_rows()` caps last row at item_y+55pt (line
    95	     ~223). Legal rows run 6-8 lines (~80pt+). Make the cap adaptive from
    96	     actual word positions (next block start / next header), not static.
    97	   - R6/asterisk footnote: `is_footer_word()` y≥600 drops the "*To find
    98	     definitions of asterisked terms…" line when it sits in a table's
    99	     vertical flow — treat that line as table metadata, keep it out of cells
   100	     but don't lose it.
   101	   - R3/generalise: `table_blocks()` keys off a capitalised 'Item' first word
   102	     (line ~97). GST/FBT/SIS tables use other header shapes (column-letter
   103	     tables, no-Item tables, roman-numeral identifiers). Parameterise or add
   104	     act-specific block/header detection; smoke-test ONE flagged file per act
   105	     in Phase 0.
   106	   - R10/performance: call `collect_tables()` in-process (library import)
   107	     instead of subprocess-per-file for 240+ rebuilds.
   108	5. Extend `validate_md()` (or a new wrapper) with content checks:
   109	   - no mid-word split signatures (run `scan_table_coherence` on the rebuilt
   110	     file → 0 C11 hits),
   111	   - no glyph chars,
   112	   - row text present in source page (fidelity above).
   113	5. Smoke-test on 3 known-bad sections (115-30, 109-55, FBT 135W): rebuild,
   114	   verify fidelity gate passes AND rendered HTML looks right.
   115	   For txt-only acts, smoke-test the txt-layout slicer (extend
   116	   `repair_itaa_tables.py` column-slice approach to general headers) on a
   117	   known-bad GST + SIS section.
   118	
   119	### Phase 1 — rebuild itaa-1997 (largest, 416 findings)
   120	
   121	Priority order within act: divisions with the most flags first (43-*, 40-*,
   122	109-115, 296-* etc — derive exact ranking from C11 JSON).
   123	
   124	For each flagged file:
   125	1. Locate section pages in the right compilation volume.
   126	2. Rebuild all tables in the file from PDF word positions with proper cell
   127	   reflow + row continuation across page breaks (fix the extractor's known
   128	   gaps rather than hand-editing).
   129	3. Run fidelity gate + C11 rescan on the rebuilt file. 0 C11 + gate pass =
   130	   done; else keep the file on the reject list with the diff.
   131	4. Human/agent spot-read of a sample (Harry's rule: blind 0.0% is not done).
   132	
   133	### Phase 2 — rebuild remaining acts
   134	
   135	Same procedure for taa-1953, gst-1999, fbt-1986, itaa-1936, sis-1993 (each
   136	act-gated; stop and review after every act).
   137	
   138	### Phase 3 — regression verification (per act, per rebuild batch)
   139	
   140	1. `python3 scripts/verify_data_integrity.py --domain all` — PASS.
   141	2. C11 content phase re-run: flagged files for the act → 0.
   142	3. API read-back: `GET /api/section/<act>/<sec>` returns the rebuilt table
   143	   (curl a sample, confirm cell text is present and unbroken).
   144	4. Service restart before final verification (files are read live, but the
   145	   running process caches act lists).
   146	
   147	### Phase 4 — commit + ticket close
   148	
   149	- Logical commits per act: `fix(data): rebuild <act> tables from compilation
   150	  PDFs (C11 table-coherence class)` — corpus changes only, scripts committed
   151	  separately if modified.
   152	- After all acts: run the full `final_data_audit.py` (NEW random seed) —
   153	  C11 must be the only reduced class; verdict PASS.
   154	- Close CDN tickets for the table class (CDN-0186/0187 + any auto-synced C11
   155	  ticket) with `note || '; Fixed 2026-09-07 (raw-PDF table rebuild)'`.
   156	- Update `BUGS_NEXT_TIME.md` / patch owning skills if procedure changed.
   157	
   158	## Gates / abort conditions
   159	
   160	- Any act whose fidelity gate rejects >5% of files → STOP, review extractor,
   161	  do not proceed to next act.
   162	- Do NOT commit a file whose C11 rescan still flags it.
   163	- Do NOT run over uncommitted WIP — repo is clean at 79a649408 except
   164	  approved commits; re-check `git status` before Phase 1.
   165	- Rebuild scripts run with python3.12 + fitz (venv/interp as per existing
   166	  apply script). Never use python3 (3.11) for fitz code.
   167	
   168	## Risks / mitigations
   169	
   170	- **Extractor gaps on complex tables** (multi-level headers, merged cells,
   171	  formulas): formulas (FBT 9, 135W) may need manual reconstruction from raw —
   172	  keep a manual-fix list, do NOT auto-apply questionable rebuilds.
   173	- **Volume mapping drift**: frontmatter `source_pdf` may be stale (comp 263
   174	  vs 266 era). Verify section presence in the PDF page set before trusting
   175	  extraction; prefer the compilation volume matching frontmatter
   176	  `compilation_no` and fall back to searching all vols of the act.
   177	- **Size**: ~240 files. Parallelise with subagents per division, main agent
   178	  owns gates/commits. Subagent fixes are READ-ONLY-plan + execute + verify per
   179	  the mandated chain; do not let subagents commit.
   180	- **Renderer-side**: verify at least one table per act in a real browser
   181	  (markdown table renders with correct columns), not just file-level checks.
   182	
   183	## Scope measured 2026-09-12 (nightly bug-squash run) — CDN-0193
   184	
   185	The randomised corpus audit (seed 39878977) opened **CDN-0193 = this plan's
   186	`C11_table_truncated` signature**. Live C11 rescan on 2026-09-12:
   187	**152 glyph / 115 midword / 504 truncated = 771 findings**, i.e. the truncated
   188	class is the largest single remaining data-loss class in the corpus.
   189	
   190	`scripts/scan_truncation_scope.py` (new, committed with this addendum) probes
   191	each truncated finding's offending cell tail in the act's repo raw text and
   192	splits it by *where the lost text can be recovered from*:
   193	
   194	| act       | truncated findings | tail continues in repo raw | split at PDF page boundary | tail not located | repo raw comp | corpus comp | staging source present |
   195	|-----------|--------------------|----------------------------|----------------------------|------------------|---------------|-------------|------------------------|
   196	| itaa-1997 | 340                | 238                        | 71                         | 31               | **263 (STALE)** | 266       | comp266 vol01-12 PDFs ✓ |
   197	| taa-1953  | 68                 | 39                         | 19                         | 10               | 222 ✓         | 222         | comp225 vol01-04 PDFs  |
   198	| sis-1993  | 29                 | 14                         | 12                         | 3                | 126 ✓         | 126         | part1-2 PDFs ✓         |
   199	| itaa-1936 | 25                 | 13                         | 8                          | 4                | 191 ✓         | 191         | comp192 vol01-07 PDFs  |
   200	| gst-1999  | 21                 | 16                         | 5                          | 0                | 96 ✓          | 96          | (repo raw txt only)    |
   201	| fbt-1986  | 21                 | 18                         | 2                          | 1                | 96 ✓          | 96          | part1-2 PDFs ✓         |
   202	| **total** | **504**            | **338**                    | **117**                    | **49**           |               |             |                        |
   203	
   204	Read this table as *text availability*, not as a licence to patch from raw:
   205	
   206	- "tail continues in repo raw" (338) means the lost cell text exists in the
   207	  repo's own extraction text — no new download needed for those *acts whose raw
   208	  matches the corpus compilation*. For itaa-1997 the repo raw is the STALE
   209	  comp 263 while the corpus is comp 266 (the 238-column above), so itaa-1997
   210	  must still be rebuilt from the staging comp266 PDFs as this plan requires.
   211	- "split at PDF page boundary" (117) needs the source PDF / next page join —
   212	  exactly the extractor defect R4/§Phase0.4 (row continuation across page
   213	  breaks), plus R5 (row cap). This is the single biggest truncation cause, as
   214	  this plan predicted.
   215	- "tail not located" (49) is a probe artefact or in-file scramble (the
   216	  multi-column band interleave, e.g. `itaa-1936/schedule-2f/266-10`,
   217	  `itaa-1997/30-15`, `sis-1993/part-1/6`), not a detector false positive: every
   218	  sampled finding is genuinely cut mid-clause. No detector-tightening fix is
   219	  available for this class (unlike CDN-0191's accent-fold exemption).
   220	
   221	Execution gate status as of 2026-09-12: **not satisfied** — no opus/codex review
   222	artefacts for this plan exist in the repo, and the repo's own history shows an
   223	earlier cron attempt at this class was lossy and had to be reverted
   224	(§Evidence, 2026-09-07). Held for Harry's sign-off; do not execute piecemeal.
   225	
   226	## Out of scope (this pass)
   227	
   228	- NZ IT 2007 (0 flags), OECD/treaties/proposed-law (not flagged).
   229	- `spec` fixture tables (clean; detector has 0 hits there).
   230	- Non-table truncation classes (CDN-0182 30-212 etc) — separate tickets.

codex
VERDICT: REJECT

BLOCKERS:

1. Staging-source versions are materially wrong. PDF first-page text reports:

   - ITAA-1997 staging `C2026C00122VOL01.pdf`: compilation **263**, not 266.
   - TAA staging `vol01.pdf`: **222**, not 225.
   - FBT staging `part1.pdf`: **96**, not 97.
   - ITAA-1936 staging `C2026C00165VOL01.pdf`: **191**, not 192.
   - SIS staging `part1.pdf`: **126**.

   Corpus frontmatter is uniformly 266/222/96/191/126 respectively; repo raw is 263/222/96/191/126. This refutes plan lines 63–76 and 194–210. Exact change: obtain and independently verify comp-266 ITAA PDFs before any ITAA rebuild; correct every source-table entry using document-internal compilation metadata, not filenames.

2. ITAA-1997 must not run first. Its only present PDF source is stale comp 263 while corpus is comp 266. Rebuilding it risks silently reverting law. Exact change: begin calibration with a matching-source act such as TAA-1953 or SIS-1993; hold ITAA until comp-266 sources exist.

3. The proposed ≥98% fidelity gate permits loss. A large rebuild could omit 2% of legal text, an entire short cell, qualifiers, footnotes, or formula terms and still pass. Plan lines 78–86 also contemplate relaxing the threshold. Exact change: require 100% normalized token recall and 100% output-token provenance per table/cell, with no relaxation. Any mismatch rejects the file for manual review.

4. No gate proves that only intended table regions changed. `find_table_region_end()` can consume blockquotes, headings, and loose prose ([apply_itaa_table_fixes.py:196](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:196)); replacement is an unrestricted slice ([line 300](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:300)). Exact change: byte-identical comparison outside explicitly identified table spans; abort on any non-table change.

5. C11=0 is not a completeness test. The scanner reports at most one class per row because glyph and truncation matches `continue` before midword analysis ([scan_corpus_error_classes.py:238](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:238), [line 245](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:245)). It detects only listed glyphs, dictionary-recognized splits, and final-cell connector endings ([lines 169–198](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:169)). Exact change: add independent completeness, row-count, header-count, footnote, formula, and bidirectional source-text gates.

6. The truncation triage categories are not reliable causal measurements. The probe chooses the last matching four-word suffix anywhere across concatenated volumes ([scan_truncation_scope.py:39](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:39), [lines 71–83](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:71)); “page split” is inferred solely from one of the next three nonempty raw lines ([lines 87–94](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:87)). Exact change: relabel these as heuristic buckets and validate section/page-local matches before using them to choose repair methods.

REQUIRED CHANGES BEFORE EXECUTION:

1. Produce a signed source manifest per volume: act, internal compilation number/date, checksum, corpus compilation, and approved sections. Abort on any mismatch.

2. Replace the 98% metric with:

   - Normalize Unicode NFC, whitespace, soft hyphens and line-end hyphenation.
   - Normalize smart/straight quotes only as an explicit equivalence.
   - Strip Markdown emphasis markers while retaining text.
   - Resolve `[label](URL)` to label text; do not discard labels.
   - Preserve asterisks that carry legal/formula meaning.
   - Require every reconstructed token in ordered source text and every table-region source token in output.
   - Reject, never auto-relax, on failure.

3. Add exact gates for item identifiers, row count, column/header count, repeated headers, continuation rows, table notes, asterisked-definition lines, and formula operands/operators. Formula tables require PDF visual comparison because text-layer glyphs may not encode mathematical meaning faithfully.

4. Save proposed outputs outside the live corpus; generate per-file source/output/diff reports. Require explicit review for every file with row joins, formula content, merged cells, changed row counts, or ambiguous page mapping.

5. Enforce byte-identical non-table content and unchanged frontmatter. Reject edits spanning prose, anchors, headings, blockquotes not proven to be table debris, or adjacent tables.

6. Establish rollback using a clean, recorded commit/worktree and a manifest of original hashes. Current `git status --short --branch` is already dirty, contradicting plan line 163; do not execute in this worktree.

7. Run independent post-rebuild scans on all output, not only formerly flagged files. Record before/after findings by class and file; abort if any new C11 or other integrity finding appears.

8. Make C11 report all applicable classes per row rather than mutually excluding them. Retain baseline findings so “fixed one class, exposed another” is distinguishable from regression.

9. Recalibrate on matching-source, structurally varied tables first—clean and corrupt examples from TAA/SIS/GST—then FBT formula tables. ITAA-1997 comes only after comp-266 acquisition.

RECOMMENDED (non-blocking):

- Treat subprocess-per-file as performance-only, not a correctness defect.
- Review all three SIS flagged files because one contains most SIS truncations.
- Do not use the generic ITAA layout slicer blindly for other acts: it assumes `Item` headers and essentially three-column geometry ([repair_itaa_tables.py:25](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:25), [line 31](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:31), [lines 225–263](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:225)).

VERIFIED CLAIMS:

- Confirmed R3: capitalized `Item` first-word detection is hard-coded ([extract_itaa_tables_pdf.py:26](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:26), [line 97](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:97)).
- Confirmed R5: last row is capped at `item_y + 55` ([lines 218–224](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:218)).
- Confirmed R6: all words at `y1 >= 600`, including the stated definition footer, are dropped ([lines 160–167](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:160), [line 227](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:227)).
- Partly confirmed R4: blocks merge only on identical headers and merely append rows; no cross-page cell continuation exists ([lines 311–319](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:311)). The plan’s proposed “same item number” rule is not sufficient for continuations lacking repeated item numbers.
- Confirmed R10: one subprocess is launched per section ([apply_itaa_table_fixes.py:71](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:71), [lines 334–337](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:334)).
- Confirmed structural-only validation: it checks frontmatter, headings, separators, and column counts—not content ([lines 103–167](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:103)).
- Confirmed live counts: scanner returned **152 glyph / 115 midword / 504 truncated = 771**.
- Confirmed current act totals: ITAA-1997 418, TAA 106, ITAA-1936 76, FBT 74, GST 65, SIS 32 across 216 distinct files—not the plan’s older ~240/~747 or act figures.
- Reproduced addendum truncation buckets exactly: 338/117/49 and all act rows. Their causal interpretation remains unverified due to the probe defects above.
- Could not verify the claimed comp-266 ITAA source because it is absent; the present staging PDF explicitly says comp 263.

tokens used
77,466
VERDICT: REJECT

BLOCKERS:

1. Staging-source versions are materially wrong. PDF first-page text reports:

   - ITAA-1997 staging `C2026C00122VOL01.pdf`: compilation **263**, not 266.
   - TAA staging `vol01.pdf`: **222**, not 225.
   - FBT staging `part1.pdf`: **96**, not 97.
   - ITAA-1936 staging `C2026C00165VOL01.pdf`: **191**, not 192.
   - SIS staging `part1.pdf`: **126**.

   Corpus frontmatter is uniformly 266/222/96/191/126 respectively; repo raw is 263/222/96/191/126. This refutes plan lines 63–76 and 194–210. Exact change: obtain and independently verify comp-266 ITAA PDFs before any ITAA rebuild; correct every source-table entry using document-internal compilation metadata, not filenames.

2. ITAA-1997 must not run first. Its only present PDF source is stale comp 263 while corpus is comp 266. Rebuilding it risks silently reverting law. Exact change: begin calibration with a matching-source act such as TAA-1953 or SIS-1993; hold ITAA until comp-266 sources exist.

3. The proposed ≥98% fidelity gate permits loss. A large rebuild could omit 2% of legal text, an entire short cell, qualifiers, footnotes, or formula terms and still pass. Plan lines 78–86 also contemplate relaxing the threshold. Exact change: require 100% normalized token recall and 100% output-token provenance per table/cell, with no relaxation. Any mismatch rejects the file for manual review.

4. No gate proves that only intended table regions changed. `find_table_region_end()` can consume blockquotes, headings, and loose prose ([apply_itaa_table_fixes.py:196](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:196)); replacement is an unrestricted slice ([line 300](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:300)). Exact change: byte-identical comparison outside explicitly identified table spans; abort on any non-table change.

5. C11=0 is not a completeness test. The scanner reports at most one class per row because glyph and truncation matches `continue` before midword analysis ([scan_corpus_error_classes.py:238](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:238), [line 245](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:245)). It detects only listed glyphs, dictionary-recognized splits, and final-cell connector endings ([lines 169–198](/home/harrison/legislation-explorer/scripts/scan_corpus_error_classes.py:169)). Exact change: add independent completeness, row-count, header-count, footnote, formula, and bidirectional source-text gates.

6. The truncation triage categories are not reliable causal measurements. The probe chooses the last matching four-word suffix anywhere across concatenated volumes ([scan_truncation_scope.py:39](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:39), [lines 71–83](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:71)); “page split” is inferred solely from one of the next three nonempty raw lines ([lines 87–94](/home/harrison/legislation-explorer/scripts/scan_truncation_scope.py:87)). Exact change: relabel these as heuristic buckets and validate section/page-local matches before using them to choose repair methods.

REQUIRED CHANGES BEFORE EXECUTION:

1. Produce a signed source manifest per volume: act, internal compilation number/date, checksum, corpus compilation, and approved sections. Abort on any mismatch.

2. Replace the 98% metric with:

   - Normalize Unicode NFC, whitespace, soft hyphens and line-end hyphenation.
   - Normalize smart/straight quotes only as an explicit equivalence.
   - Strip Markdown emphasis markers while retaining text.
   - Resolve `[label](URL)` to label text; do not discard labels.
   - Preserve asterisks that carry legal/formula meaning.
   - Require every reconstructed token in ordered source text and every table-region source token in output.
   - Reject, never auto-relax, on failure.

3. Add exact gates for item identifiers, row count, column/header count, repeated headers, continuation rows, table notes, asterisked-definition lines, and formula operands/operators. Formula tables require PDF visual comparison because text-layer glyphs may not encode mathematical meaning faithfully.

4. Save proposed outputs outside the live corpus; generate per-file source/output/diff reports. Require explicit review for every file with row joins, formula content, merged cells, changed row counts, or ambiguous page mapping.

5. Enforce byte-identical non-table content and unchanged frontmatter. Reject edits spanning prose, anchors, headings, blockquotes not proven to be table debris, or adjacent tables.

6. Establish rollback using a clean, recorded commit/worktree and a manifest of original hashes. Current `git status --short --branch` is already dirty, contradicting plan line 163; do not execute in this worktree.

7. Run independent post-rebuild scans on all output, not only formerly flagged files. Record before/after findings by class and file; abort if any new C11 or other integrity finding appears.

8. Make C11 report all applicable classes per row rather than mutually excluding them. Retain baseline findings so “fixed one class, exposed another” is distinguishable from regression.

9. Recalibrate on matching-source, structurally varied tables first—clean and corrupt examples from TAA/SIS/GST—then FBT formula tables. ITAA-1997 comes only after comp-266 acquisition.

RECOMMENDED (non-blocking):

- Treat subprocess-per-file as performance-only, not a correctness defect.
- Review all three SIS flagged files because one contains most SIS truncations.
- Do not use the generic ITAA layout slicer blindly for other acts: it assumes `Item` headers and essentially three-column geometry ([repair_itaa_tables.py:25](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:25), [line 31](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:31), [lines 225–263](/home/harrison/legislation-explorer/scripts/repair_itaa_tables.py:225)).

VERIFIED CLAIMS:

- Confirmed R3: capitalized `Item` first-word detection is hard-coded ([extract_itaa_tables_pdf.py:26](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:26), [line 97](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:97)).
- Confirmed R5: last row is capped at `item_y + 55` ([lines 218–224](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:218)).
- Confirmed R6: all words at `y1 >= 600`, including the stated definition footer, are dropped ([lines 160–167](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:160), [line 227](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:227)).
- Partly confirmed R4: blocks merge only on identical headers and merely append rows; no cross-page cell continuation exists ([lines 311–319](/home/harrison/legislation-explorer/scripts/extract_itaa_tables_pdf.py:311)). The plan’s proposed “same item number” rule is not sufficient for continuations lacking repeated item numbers.
- Confirmed R10: one subprocess is launched per section ([apply_itaa_table_fixes.py:71](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:71), [lines 334–337](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:334)).
- Confirmed structural-only validation: it checks frontmatter, headings, separators, and column counts—not content ([lines 103–167](/home/harrison/legislation-explorer/scripts/apply_itaa_table_fixes.py:103)).
- Confirmed live counts: scanner returned **152 glyph / 115 midword / 504 truncated = 771**.
- Confirmed current act totals: ITAA-1997 418, TAA 106, ITAA-1936 76, FBT 74, GST 65, SIS 32 across 216 distinct files—not the plan’s older ~240/~747 or act figures.
- Reproduced addendum truncation buckets exactly: 338/117/49 and all act rows. Their causal interpretation remains unverified due to the probe defects above.
- Could not verify the claimed comp-266 ITAA source because it is absent; the present staging PDF explicitly says comp 263.

CODEX_EXIT=0
