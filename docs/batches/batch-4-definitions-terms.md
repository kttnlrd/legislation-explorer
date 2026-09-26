# Batch 4 — CDN-0209 (terms with `&` / apostrophe), CDN-0210 (prose and list-fragment terms)

Executor log. Packet: batch 4 of `docs/bug-plan-2026-09-25.md`, both ids sharing one fix site (the
term-boundary logic in the definitions producer family). Branch `master` from `899e86afc`.
Python `/usr/bin/python3.12`. No push. `data/quotes.json` left alone (still dirty, mtime
2026-09-24 09:28).

## Fix sites and commits

| Commit | Fix site | Files |
|---|---|---|
| `b95d6fbe7` | CDN-0209/0210 — the definitions builder | `scripts/build_definitions_index.py` |
| `1a4147fe6` | CDN-0209 — the served catalogue and its producers | `pipeline/extract_definitions.py`, `pipeline/extract_all_definitions.py`, `pipeline/dictionary_utils.py`, `data/itaa-1997/definitions.json`, `data/itaa-1936/definitions.json`, `data/gst-1999/definitions.json` |
| `1181de8fe` | CDN-0209/0210 — fixture and checks | `tests/fixtures/austlii_995_1_terms.txt`, `tests/test_cdn_0209_0210_definitions.py` |
| (this file) | Batch log | `docs/batches/batch-4-definitions-terms.md` |

The dirty file this batch owns is committed in `b95d6fbe7`; the tree is clean apart from
`data/quotes.json`. `data/definitions_all.json` and `data/definitions_comprehensive.json` are
gitignored (see the provenance note below).

## What the fix site actually was

**CDN-0209.** The term classes had no `&`, so the capture restarted after the ampersand
(`R&D entity` → `d entity` — 5 R&D terms in itaa-1997 s 995-1 alone) and a curly `’` cut possessives
(`arm’s length profits` → `s length profits`). Fixed by putting `&`/U+2019 in the STD/CALLED/IN_THIS/
COLON classes, normalising curly quotes to straight, and adding
`scripts/build_definitions_index.py:starts_at_left_boundary()` so a capture can never begin
immediately after an ASCII letter or digit. Provenance (`generator`, `source_commit`) added to the
builder's output; the served catalogue's producers now carry a `_provenance` block.

**CDN-0210.** Three defects in the in-progress diff, all corrected:

* **a)** `"a"`/`"an"` removed from `_CONNECTOR_TAILS` — as written they dropped every term ending in
  an article (`Zone A`, itaa-1936 s 79A).
* **b)** `dedupe_sig()`: a record whose raw capture carried a `, <scope qualifier>` clause now keys
  on term+act+**section**, so scoped definitions in other sections survive instead of folding into
  whichever section was scanned first.
* **c)** `_SECTION_NUMBER_LEAD_RE` rejects captures that begin with a section number
  (`57a meaning of corporation (1)`, corps-act s 57A; 65 corps captures in the pre-batch index).

`scan_act()` was split into `scan_section_body()` + `dedupe_records()` so the checks exercise the
real code path rather than a copy of it.

## The checks that failed first (gate 3)

`tests/test_cdn_0209_0210_definitions.py` accepts `DEFS_INDEX_MODULE=<path>` so it can be pointed at
an unfixed copy; the fallback scan inside `_scan()` keeps it failing on the defect instead of on a
missing attribute.

Against the pre-fix script (`DEFS_INDEX_MODULE=/tmp/bdi_head.py`, i.e. `git show HEAD:`):

```
8 failed, 2 passed in 10.73s
  test_995_1_paragraph_terms_exact
    got {'d entity', 's length profits', 'rba surplus'}   (exactly the plan's failure)
  test_recall_against_austlii_fixture
    995-1 recall: 1453/1566 = 92.78% (113 missing)
  test_r_and_d_terms_present_in_995_1_scan
    missing: core r&d activities, r&d activities, r&d entity, r&d partnership,
             supporting r&d activities
  test_995_1_paragraph_no_curly_apostrophe_left, test_list_fragment_yields_no_term,
  test_no_terms_at_all_are_list_fragments, test_scoped_definition_keeps_its_own_section,
  test_built_index_records_provenance
```

Against the pre-batch **working copy** (the committed diff with the three 0210 defects still in it,
reconstructed at `/tmp/bdi_diffonly.py`):

```
4 failed, 6 passed in 48.53s
  test_zone_a_survives — ['census population', ..., 'zone b'] (no 'zone a')
  test_scoped_definition_keeps_its_own_section — sections ['6'] (s 90 folded away)
  test_no_term_begins_with_a_section_number — corps 57A '57a meaning of corporation (1) ...'
  test_built_index_records_provenance — no 'generator' field yet
  recall at this state: 1542/1566 = 98.47%
```

After the fixes: `10 passed`, recall `1,542/1,566 = 98.47%`.

**On the plan's "1,484" and its 97.7%/98.1%.** The fixture holds 1,927 distinct terms; 1,566 of them
occur in the served 995-1 body at a definition boundary (start of text or after a sentence,
paragraph or list break, with at most a `, <qualifier>,` before the verb). That is the reference
this log uses. The ticket's 1,484 count is not reproducible from the fixture — the plan already
records the same finding for its own 1,404 parse (`docs/bug-plan-2026-09-25.md:618`) — so the
percentage here is measured against 1,566, not 1,484. Recall measured against all 1,927 fixture
terms is 80.0% (1,542), the rest being terms whose definition starts sit in blockquotes or behind
run-on prose (see CDN-0214).

## Measured before/after (gates 3/4/5)

Rollback point: `data/definitions_comprehensive.json.bak-cdn0209-2026-09-26`
(md5 `379752633a8c31e6bbe71ae2b2ee6aa0`, byte-identical to the pre-batch file).
`python3.12 scripts/build_definitions_index.py`:

| Metric | Before | After |
|---|---|---|
| definitions | 5,609 | 4,950 |
| itaa-1997 s 995-1 entries | 1,771 | 1,721 |
| list-fragment terms (`^\(?[0-9a-z]{1,4}\)\s`) | 397 | 0 |
| mid-word heads (`^[a-z]\s`) | 93 | 0 |
| section-number heads (`^\d+[a-z]?\s`) | 90 | 0 |
| terms containing `&` | 0 | 13 |
| definition text, mean / max | 9,793 / 433,218 chars | 8,936 / 431,276 chars |

Terms added/dropped by the all-acts dedupe: 1,285 dropped, 626 added (keyed on act+term+section) —
the plan's CDN-0210 estimate was 1,162/539, the difference being the section-number gate and the
`a`/`an` correction. `Zone A` and `Zone B` survive; itaa-1936 "exempt income" now appears at
s 6, 90, 95 and 102AAB (was s 6 only). The `&` terms include `R&D entity`, `R&D activities`,
`R&D partnership`, `core R&D activities`, `supporting R&D activities`, `R&D expenditure`,
`refundable/non-refundable R&D tax offset`.

Served catalogue (`pipeline/extract_definitions.py --preserve-existing` then
`pipeline/extract_all_definitions.py`):

| File | Before | After |
|---|---|---|
| `data/itaa-1997/definitions.json` | 1,681 | 1,700 (803 re-derived, 897 preserved, 19 added, **0 lost**) |
| `data/itaa-1936/definitions.json` | 205 | 205 (provenance only) |
| `data/gst-1999/definitions.json` | 327 | 327 (provenance only) |
| `data/definitions_all.json` (served) | 1,955 terms | 1,974 terms, 0 lost |

Live evidence, no restart needed (the loader caches on `(path, mtime)`):

```
curl /api/definitions
  {"acts":[{"act":"gst-1999","count":327},{"act":"itaa-1936","count":205},
           {"act":"itaa-1997","count":1700}]}          # was 1681
curl --get --data-urlencode "q=r&d" /api/definitions/itaa-1997/search
  "R&D partnership" (s995-1-rd-partnership),
  "supporting R&D activities" (s995-1-supporting-rd-activities)
/usr/bin/python3.12 tests/integration_test.py
  exit 0 — "Results: 34 passed, 0 failed"
/usr/bin/python3.12 -m pytest tests/test_cdn_0204_tree_title.py tests/test_cdn_0205_related_cases.py \
    tests/test_cdn_0206_commentary_ranking.py tests/test_cdn_0209_0210_definitions.py
  24 passed in 67.67s
/usr/bin/python3.12 tests/test_vectors.py
  64 passed, 1 failed — "Cross-type edges exist — 0 (0.0%)" in embeddings.db, PRE-EXISTING
  (embeddings.db mtime 13:37, before this batch; nothing here touches it)
```

## New tickets

* **CDN-0213** (`bug`) — the `definition` text still runs past the end of each definition
  (`find_definition_end`, mean 8,936 chars / max 431,276 after this rebuild; 9,793 / 433,218 before).
  Logged as the plan requires (`docs/bug-plan-2026-09-25.md:287`) and **not** fixed here.
* **CDN-0214** (`bug`) — the served itaa-1997 catalogue does not re-derive from the current source:
  0 of 1,700 anchors resolve against `995-1.md` (34 `<a id="s995-1-*">` tags), and
  `extract_definitions.py` re-derives only **803** of the 1,700 terms, because the 2026-09-19/20
  re-ingest (`a014aefff`/`68120e313`/`db1e4cddf`) put the dictionary back into run-on paragraphs.
  897 rows were carried over with the new `--preserve-existing` flag rather than dropped. Three of
  the five 995-1 R&D terms (`R&D activities`, `R&D entity`, `core R&D activities`) sit on `>`
  blockquote lines, which `iter_definition_starts()` skips, so they are still not *terms* in the
  served catalogue (they only appear inside other definitions' text).

## Open items handed on

* **`data/definitions_all.json` is gitignored, not tracked** (`.gitignore:20`), contrary to the
  packet. Its pre-batch state is therefore not recoverable with `git checkout`; it is reproducible
  by checking out the tracked per-act files and re-running `pipeline/extract_all_definitions.py`.
  The regenerated file is a strict superset (1,955 → 1,974 displays, 0 lost), so nothing was
  destroyed, but the next batch that needs a rollback point for it should copy the file first.
* **The three CDN-0210 defects were in the uncommitted diff, not at HEAD** — `test_zone_a_survives`,
  `test_scoped_definition_keeps_its_own_section` and (on the corps sections)
  `test_no_term_begins_with_a_section_number` pass at HEAD and fail on the diff, which is why the
  fail-first evidence above is given for both states.
* **`pipeline/dictionary_utils.py` was changed** (`DEF_START_RE` gains `&`). It is shared with
  `parse_itaa97/parse_itaa36/parse_gst1999`, which were not run here; the effect on a future
  re-ingest is that run-on R&D definitions are recognised as definition starts, which is the same
  defect class.
* **Not run:** `scripts/randomised_api_mcp_test.py`, `final_data_audit.py`,
  `scripts/validate_data.py` (they write findings into the issues portal or expect a quiet tree).
  The regenerated `data/definitions_all.json` keeps its shape (`{act: {section, provenance, terms}}`)
  — `data_loader`, `graph_etl.load_definitions` and `validate_data.check_definitions_all` all read
  only `section`/`terms`, so the added `provenance` key is inert for them.
