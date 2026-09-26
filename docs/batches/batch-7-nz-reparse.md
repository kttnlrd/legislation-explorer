# Batch 7 — CDN-0173 (nz amendment-history sections) + E-d (nz BOM)

Executor log. Packet: batch 7 of `docs/bug-plan-2026-09-25.md`, ids CDN-0173 and E-d (the nz half;
the aml glued-heading half of E-d belongs to batch 8). Branch `master` from `994cf3377`.
Python `/usr/bin/python3.12`. No push. `data/quotes.json` left alone (still dirty, mtime
2026-09-24 09:28; untouched by every command below).

Job order: docs/BUILD_PROCESS.md gates 1-5. Spec read from the plan's CDN-0173 (:90-109) and
E-d (:356-373) sections; both root causes were re-read in the source before anything was written.

## Fix sites and commits

| Commit | Fix site | Files |
|---|---|---|
| `73c0f9cb8` | Parser: endnote-part skip + BOM strip | `pipeline/parse_nz_it.py`, `scripts/test_c18_parse_nz_it.py` |
| `87422e62a` | Data: 445 deletions, tree rebuild, 1,939 U+FEFF | `data/nz-it-2007/**` (445 D, 710 M, tree.json), `scripts/fix_nz_amendment_parts.py`, `docs/provenance/batch7-nz-reparse-*.json`, `docs/provenance/batch7-corpus-guard-*.json` |
| `007b36828` | Derived sweeps (search + graph + embeddings) | `scripts/sweep_graph_stale_sections.py`, `scripts/openai_embed.py` |
| `65420d762` | Sweep scope check + sweep evidence | `scripts/test_embed_prune_scope.py`, `docs/provenance/batch7-derived-sweeps-*.json` |

## The checks that failed first (gate 3)

`scripts/test_c18_parse_nz_it.py` plants a miniature of the 31 MB document — the consolidated
Part A plus all three endnote containers (`div.end > div.skeletons > div.skeleton-act`,
`div.schedule-amendments`, `div.amend`) each carrying its own `div.part` with ids 1/2/3B — and a
U+FEFF between subsection brackets.

```
against HEAD's parser (PARSE_NZ_MODULE=/tmp/parse_nz_it_head.py)
  written: ['part-1/3.md', 'part-2/9.md', 'part-3B/RA-1.md', 'part-A/division-AA/AA-1.md']
  5 FAILURE(S)   (including "no U+FEFF in the served text")
against the working tree
  written: ['part-A/division-AA/AA-1.md']   7 PASS
```

Corpus-level, `scripts/scan_corpus_error_classes.py`, before → after:

```
C18_nz_amendment_part   445      ->  0
C23_invisible_char      714 (1947 occurrences) -> 0
TOTAL FINDINGS         2190      ->  1031
```

2190 − 1031 = 1159 = 445 + 714, so nothing else moved. The remaining C23 findings are
`C23_nonstandard_hyphen` 33 and `C23_soft_hyphen` 9, and every one of the 42 is non-nz
(`itaa-1997`, `regulatory-guides`, `rulings`, `scripts/cleaned/summaries`).

## What the fix site actually was

**CDN-0173.** `soup.find_all("div", class_="part")` (:195) matched the parts nested inside the
endnote copies of the amending Acts and inside `div.schedule-amendments` / `div.amend`. Their ids
reuse "1"/"2"/"3", so they overwrote each other's files and 445 amendment-history sections were
served beside the consolidated Parts A-Z. New `inside_endnote(part)` walks `part.parents` for a
`div` carrying one of `{end, skeletons, schedule-amendments, amend}` as an exact class token.

**E-d.** `clean_text` (:37) collapsed `\s+`, and U+FEFF is not `\s`, so a BOM between subsection
brackets survived. It now deletes U+FEFF rather than collapsing it to a space — "(1)\ufeff(a)" is
one citation, and a space there would invent a word break.

Re-parse to offline staging (`/tmp/batch7-staging`, never written into `data/`):

```
{"parts": 23, "subparts": 168, "sections": 2850, "skipped_endnote_parts": 12}
2850 written + 445 amendment = 3,295 = the corpus leaf count
```

## Verify pass (gate 4)

The staged re-parse vs HEAD, folded only for the two known post-parse drifts — the frontmatter
blank line and the corpus-wide cosmetic pass `a59a3285e` ("single space after **(n)** markers,
straight quotes", applied unevenly: plain numeric markers got one space, `(5B)`-style kept two,
so the marker spacing is normalised on both sides):

```
2,138 of 2,850  reproduce HEAD byte-for-byte
  709           match exactly once the BOM is removed
    3           REVIEW LIST — not applied
```

Review list: `part-C/division-CX/CX-55.md`, `part-E/division-ED/ED-2B.md`,
`part-E/division-EX/EX-31.md`. In all three HEAD is truncated mid-sentence ("...a market licensee
under") and the re-parse restores the tail (the text continues on the next line of the source).
That is a real corpus truncation, not a BOM; it is out of this batch's fix site and was not
applied.

Applied change: `text.replace("\ufeff", "")` on the 710 surviving files that carried one, nothing
else. Independent check (`/tmp/batch7-bomcheck.py`): for all 710, worktree == HEAD with U+FEFF
deleted; 0 other differences; 1,939 characters removed (714/1,947 minus the 4 files/8 occurrences
that lived inside the deleted parts).

`data/nz-it-2007/tree.json`: 19 parts → 15, 445 sections dropped, 2,850 leaves, **deletions only**
(2,253 lines removed); every surviving part is byte-identical to HEAD and keeps its order.
Written by `scripts/fix_nz_amendment_parts.py`, deliberately *not* by `pipeline/build_tree.py`: a
fresh build reorders the lettered parts (its part sort key emits I, L, C, D, M first) and rewrites
every title with `a59a3285e`'s straight quotes. Neither is this batch's fix site, so the producer's
output was not used as the writer — it was used as the cross-check: over the staged re-parse it
yields exactly those four parts dropped, 15 parts, 2,850 leaves, **0 new leaves**.

## Corpus guard (not a bypass)

`scripts/corpus_change_guard.py --json docs/provenance/batch7-corpus-guard-<stamp>.json` over the
staged set (the 445 deletions plus the 710 BOM strips):

```
1155 changed section file(s) — 710 OK, 445 WARN, 0 BLOCK     (exit 0)
```

The 445 WARNs are G-B "prose tokens no longer present" on the deletions — the guard reading a
deletion as prose loss, which is what it should say. `CORPUS_GUARD_BYPASS` was not set.

## Derived-artefact sweeps (each through its own producer)

| Store | Producer | Before → after | Removed |
|---|---|---|---|
| `search_index.db` | `scripts/rebuild_search_index.py` → `init_search_index` (reads tree.json) | sections_meta 20,842 → 20,430; nz rows 3,262 → 2,850; nz part-1/2/3/3B rows 412 → **0** | 412 rows (445 files = 412 distinct (act,section) keys) |
| `data/embeddings.db` | `scripts/openai_embed.py --prune` (new flag, `walk_corpus_files` shared with the embed path) | 281,113 → 280,665; nz 4,891 → 4,443; rows for the 445 dirs 448 → **0** | 448 rows / 445 distinct files |
| `data/graph.db` | `scripts/sweep_graph_stale_sections.py` (new; `pipeline/graph_etl.py` is upsert-only and has no sweep) | 13,722 section nodes scanned, 0 stale | **0 nodes, 0 edges** |

The rebuild took 2m33s and did not move any other act (20,842 − 412 = 20,430). The build ran with
output to a file: `REBUILD ... Done. real 2m32.779s`.

**Graph, why zero:** `pipeline/graph_etl.py:24` `ACTS` does not list `nz-it-2007`, and
`data/graph.db` holds 0 nz-it-2007 nodes (0 by `key LIKE 'section:nz-it-2007:%'`, 0 by
`content_ref LIKE 'data/nz-it-2007/%'`). The 445 ids never reached the graph. The sweep is
committed anyway, so an ETL that starts walking nz cannot leave stale nodes behind.

**Embeddings scope check before pruning:** 13,746 existing section/commentary `file_path`s vs
13,301 on disk = exactly the 445 stale files, every one under
`data/nz-it-2007/sections/part-{1,2,3,3B}/`; no other act was a candidate.
`scripts/test_embed_prune_scope.py` pins that scope (a missing file under a walked act is deleted;
a ruling row, a case row and a section row for an unwalked act are not; `commit=False` deletes
nothing; a second run is a no-op).

**Collateral, reported not fixed:** `similarity_index` (its own producer) went from 917,358 to
917,448 dangling `embedding_id` rows and 938,203 to 938,307 dangling `neighbor_id` rows — +90/+104
from this batch on top of a pre-existing ~917k/938k. `cross_references` was 187,776 dangling
before and after. Neither table is swept here.

## Verification (gate 5)

```
scripts/test_c18_nz_parts.py            PASS
scripts/test_c20_character_classes.py   PASS
scripts/test_c18_parse_nz_it.py         PASS
scripts/test_embed_prune_scope.py       PASS
tests/integration_test.py               Results: 34 passed, 0 failed
```

`systemctl --user restart legislation-explorer` → active; `GET /health` → 200; search for the
deleted id returns it no longer: `/api/search?q=80KA&act=nz-it-2007` returns only s MF-1 (which
cites "TAA ss 80KA-80KG"), and `/api/section/nz-it-2007/80KA` → 404 while
`/api/section/nz-it-2007/MF-1` → 200.

The restart triggered the vector-search service's own snapshot check ("Matrix snapshot 281,113 rows
vs DB 280,665 — rebuilding via build_vector_matrix.py"), i.e. the embeddings change is visible to
that producer; it rebuilt and the service came up clean on the second start.

## Rollback points

- `git tag batch7-rollback-20260926T124741Z` (HEAD before the batch).
- `/tmp/batch7-rollback/embeddings.db.20260926T124741Z.pre-batch7` (2,525,982,720 B, pre-sweep)
- `/tmp/batch7-rollback/graph.db.20260926T124741Z.pre-batch7` (125,607,936 B)
- `/tmp/batch7-rollback/search_index.db.20260926T124741Z.pre-batch7` (954,114,048 B)
- `/tmp/batch7-rollback/embeddings.db.pre-prune` and `openai_embed.snapshot-125326.py`
- The 445 deleted files are recoverable from `87422e62a^` (and from
  `batch7-rollback-20260926T124741Z`).
- Offline staging and reports: `/tmp/batch7-staging/`, `/tmp/batch7-verifypass.json`,
  `/tmp/batch7-bomcheck.py`, `/tmp/batch7-baseline-scan.txt`, `/tmp/batch7-after-scan.txt`.

## What I could not establish / open items

1. **A second writer was editing this working tree while this batch ran.** `scripts/openai_embed.py`
   was modified twice by session `20260926_224031_a46409` (22:52:17, 22:53:06) with its own
   `--prune`/`sweep_stale_section_files` implementation; that writer's run deleted the 448
   embeddings rows, so this executor's `--prune` then printed "pruned 0" while the row count moved
   281,113 → 280,665 (the same 448 rows). The file now holds one implementation
   (`walk_corpus_files` + `prune_stale_rows`) and commit `007b36828` was made by that writer, not
   by this executor. The two commits are consistent, but the counts in `007b36828` are this
   executor's measurements of the shared working tree. A snapshot of the file as this executor
   saw it is at `/tmp/batch7-rollback/openai_embed.snapshot-125326.py`. Treat the shared-tree
   collision as the batch's main process risk.
2. **What C18's "125 of the 132 amendment-style titles" means** was not re-measured; the detector
   counts parts, not titles, and 445 is the number it reports.
3. **`similarity_index` / `cross_references` orphanness** (above) is pre-existing and unswept.
4. **Vector-matrix snapshot** (`data/*.npy` for vector search) is rebuilt by the service on
   startup, not by this batch; it is now consistent with the pruned embeddings.
