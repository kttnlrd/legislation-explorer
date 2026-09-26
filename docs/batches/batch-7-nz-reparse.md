# Batch 7 — CDN-0173 (445 nz amendment sections) + E-d (nz BOM)

Executor log. Packet: batch 7 of `docs/bug-plan-2026-09-25.md`, two ids sharing the `pipeline/parse_nz_it.py` fix site, plus the three derived-row sweeps. Branch `master`, python `/usr/bin/python3.12`. No push. `data/quotes.json` left alone (still dirty, mtime 2026-09-24).

## Commits

| Commit | Fix site | Files |
|---|---|---|
| `73c0f9cb8` | parse_nz_it — endnote skip + BOM strip | `pipeline/parse_nz_it.py`, `scripts/test_c18_parse_nz_it.py` |
| `87422e62a` | data repair (delete 445, strip 1,939 BOM, drop 4 tree parts) | `data/nz-it-2007/…`, `scripts/fix_nz_amendment_parts.py`, `docs/provenance/batch7-*` |
| `007b36828` | derived sweeps | `scripts/openai_embed.py`, `scripts/sweep_graph_stale_sections.py`, `docs/provenance/batch7-derived-sweeps.json` |
| (this file) | batch log | `docs/batches/batch-7-nz-reparse.md` |

Rollback: `git tag batch7-rollback-20260926T124741Z` + DB file copies under `/tmp/batch7-rollback/`.

## What the fix site actually was

`parse_nz_it.py:193` ran `soup.find_all("div", class_="part")`, which also matched the parts nested
inside `div.end > div.skeletons > div.skeleton-act` (endnote copies of the amending Acts) and inside
`div.schedule-amendments` / `div.amend` (the TAA 1994 text). Their part ids reuse "1"/"2"/"3", so 445
amendment-history sections were written beside Parts A-Z and served as law. `clean_text` used `\s`,
which does not match U+FEFF, so 1,947 BOMs sat between subsection brackets ("(1)\ufeff(a)").

Fix: `inside_endnote()` rejects a `div.part` with any of the four containers as an ancestor;
`clean_text` deletes U+FEFF so the bracket pair stays adjacent.

## The check that failed first (gate 3)

`scripts/test_c18_parse_nz_it.py` plants the Act plus all three endnote containers and a BOM.

```
against HEAD's parser (PARSE_NZ_MODULE=/tmp/parse_nz_it_head.py): 5 FAILURE(S)
  writes part-1/3.md, part-2/9.md, part-3B/RA-1.md; serves "(1)\ufeff(a)"
against the working tree: PASS — one file written, no U+FEFF
```

## Data repair — surgical, not a full re-parse

A full re-parse-and-overwrite was rejected: `pipeline/build_tree.py` reorders the lettered parts
(its sort key mis-sorts single roman letters I/L/C/D/M) and rewrites every surviving title with the
a59a3285e straight quotes — ~241 unrelated title changes and a part reorder, neither this batch's
fix site. So the tree was repaired by dropping exactly the four non-letter parts, byte-identical
otherwise (`scripts/fix_nz_amendment_parts.py`). The builder was still run as the cross-check: its
output over the staged re-parse drops exactly those four parts and agrees with the repaired tree on
all 2,850 surviving leaves.

Verify pass over the surviving A-Z sections (2,850 files), folding out the known a59a3285e cosmetic
classes (straight quotes, single-space subsection markers, frontmatter blank line):

- 2,138 reproduce HEAD byte-for-byte; 709 differ only by U+FEFF removal; 3 go to review
  (CX-55, ED-2B, EX-31 — HEAD is truncated mid-sentence, the re-parse restores the tail; NOT applied).

Corpus guard over the staged deletion + strip: 1,155 changed files — 710 OK, 445 WARN (G-B prose
loss on deletion), 0 BLOCK. `docs/provenance/batch7-corpus-guard-*.json`.

## Derived sweeps (each through its producer)

- **search** `scripts/rebuild_search_index.py`: sections_meta 20,842 → 20,430 (-412), nz amendment
  rows 0, nz FTS 2,850. (412 < 445 because sections_meta is UNIQUE(act,section) and the amendment
  parts reused numeric ids.)
- **graph** `scripts/sweep_graph_stale_sections.py` (new; the ETL is upsert-only): 0 stale —
  `graph_etl.ACTS` has no nz-it-2007, verified 0 nz nodes.
- **embeddings** `scripts/openai_embed.py --prune` (new flag): 281,113 → 280,665 rows (-448), 445
  distinct file_paths, all under part-1/2/3/3B.

## Master verification (against the running service)

- scan: C18_nz_amendment_part 445 → **0**; C23_invisible_char 714 (1,947) → **0**.
- `/api/tree/nz-it-2007` → parts A–Z only; `/api/section/nz-it-2007/AA-1` 200;
  `/api/section/nz-it-2007/3` 404.
- service restarted, health 200, vector matrix auto-rebuilt 281,113 → 280,665.

## Unresolved / carried forward

- 3 review-list files (CX-55, ED-2B, EX-31): HEAD truncates mid-sentence; the re-parse's fuller
  text was NOT applied. Flag for a follow-up.
- similarity_index carries ~917k rows whose embedding_id does not resolve against embeddings (a
  pre-existing mismatch between that index and the OpenAI-embedding id space, unrelated to this
  batch's 448-row sweep). Its producer is `build_similarity_index.py`, out of scope here.
- The BOM-stripped files' embeddings still hold the pre-strip text (1,011 rows) — re-embedding was
  not in scope; the embeddings remain semantically valid (U+FEFF is invisible).
