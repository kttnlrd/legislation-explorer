# Batch 2 — CDN-0204 residual, CDN-0205 REST, CDN-0206 ranking, CDN-0099 autocomplete

Executor log. Packet: batch 2 of `docs/bug-plan-2026-09-25.md`, four ids sharing one fix-site
family (the related-blocks pipeline plus the search box). Branch `master` from `f520ddf17`.
Python `/usr/bin/python3.12`. No writes under `data/**`.

## Fix sites and commits

| Commit | Fix site | Files |
|---|---|---|
| `fa2f7b9d9` | CDN-0204 residual — `_tree_title` compares the description against the citation/stem | `backend/routes/rulings.py`, `tests/conftest.py`, `tests/test_cdn_0204_tree_title.py` |
| `a5956edd4` | CDN-0205 — REST related-cases routing + `short_case_name` | `backend/services/data_loader.py`, `tests/test_cdn_0205_related_cases.py` |
| `e23be7561` | CDN-0206 — commentary selection ranked by per-chapter link count | `backend/fastmcp_server.py`, `tests/test_cdn_0206_commentary_ranking.py` |
| `b0e202d0b` | CDN-0099 — debounced live autocomplete + changelog line | `frontend/src/components/SearchPanel.tsx`, `frontend/src/components/__tests__/SearchPanel.suggest.test.tsx`, `frontend/src/test/setup.ts`, `frontend/vitest.config.ts`, `frontend/package.json`, `frontend/package-lock.json`, `backend/routes/api.py` |

The uncommitted `backend/fastmcp_server.py` commentary hunks (part of this batch) are inside
`e23be7561`. `data/quotes.json` and `scripts/build_definitions_index.py` are untouched and still
dirty, as the packet requires. `frontend/node_modules/.package-lock.json` (tracked, rewritten by
the `npm install` that added vitest) was restored to HEAD so the tree is clean apart from the two
owned files.

## The checks that failed first (gate 3)

Written before the fixes and run against the pre-fix state:

```
/usr/bin/python3.12 -m pytest tests/test_cdn_0204_tree_title.py \
    tests/test_cdn_0205_related_cases.py tests/test_cdn_0206_commentary_ranking.py
8 failed, 5 passed in 8.11s
  CDN-0204: test_gstr_2000_17_tree_title_carries_the_description,
            test_every_ruling_with_a_description_renders_it (365 offenders),
            test_bare_citation_titles_stay_at_the_pre_regression_level
  CDN-0205: test_rest_related_cases_carry_party_names (REST returns citations),
            test_short_case_name_names_the_taxpayer_not_the_jurisdiction,
            test_no_case_in_the_index_is_short_named_taxation
  CDN-0206: test_master_tax_guide_chapter_16_is_ranked_in,
            test_chapter_16_outranks_lower_link_chapters
cd frontend && npx vitest run          # HEAD component
3 failed | 1 passed in 2.31s
```

After the fixes:

```
/usr/bin/python3.12 -m pytest tests/test_cdn_0204_tree_title.py \
    tests/test_cdn_0205_related_cases.py tests/test_cdn_0206_commentary_ranking.py
14 passed in 8.65s
cd frontend && npx vitest run
4 passed in 2.37s
```

## Measured before/after (gate 3/5)

**CDN-0204** — bare (citation-only) tree titles over `load_rulings()` (11,952 rulings), counted with
the same rule in three checkouts:

| State | Bare tree titles |
|---|---|
| pre-extractor `3b715b745^` | 333 (plan says 332) |
| `f520ddf17` (HEAD, extractor in) | 365 (plan says 364) |
| after `fa2f7b9d9` | **118** |

The 118 that remain bare are the rulings whose description *is* the citation/stem
(`full_title == title == 'IT_1'`, 113 IT_* and 5 LCG_*); appending it would print the citation
twice. GSTR 2000/17 goes from `GSTR 2000/17  [WITHDRAWN]` to
`GSTR 2000/17 — Goods and services tax: tax invoices  [WITHDRAWN]`.

The fix therefore does more than restore the pre-regression level: comparing against the
citation/stem also recovers the descriptions of ~215 rulings that were already bare before the
extractor landed (the CR 2026/xx, GSTR, TA and MT series among them). That is the same defect the
ticket names, and it is a strict reduction in bare titles (333 → 118), so it is kept.

**CDN-0205** — `/api/cases/itaa-1997/8-1`:

```
before: {"type":"case","title":"[2020] FCAFC 25","citation":"[2020] FCAFC 25"}   (x3)
after:  {"title":"Greig v Commissioner of Taxation","citation":"[2020] FCAFC 25","short_name":"Greig","court":"FCAFC"}
        {"title":"Commissioner of Taxation v Day","citation":"[2008] HCA 53","short_name":"Day","court":"HCA"}
        {"title":"Lean and Commissioner of Taxation","citation":"[2008] AATA 519","short_name":"Lean","court":"AATA"}
```

`short_name == 'Taxation'` over the 8,460-entry name index: **2,043 → 79**. Of the 2,647 names
matching `... and <government party>`, 1,961 → 2. The 2 residue names are gov-vs-gov (both sides a
government body, or a party name truncated upstream, e.g. `s Joint Administrators of Cooper & Oxley
... and Commissioner of Taxation (Taxation)`); they are pinned by name in the test, not hidden. The
other 77 are the single-party `Re X; Ex parte Deputy Commissioner of Taxation` shape, which has no
taxpayer party to name at all and is outside this ticket.

**CDN-0206** — `get_section` for itaa-1997 8-1, 10 entries:

```
before (working-tree diff, live): MTG ch-01, 02, 03, 03, 08 + MTE ch-1, 1, 1, 1, 10 — no ch-16
after:                            5x MTG ch-16 (Deductions) + 5x MTE ch-4 (Deductions)
                                  every `source` non-empty, every `chapter_title` non-empty
```

Chapter ranking for 8-1 (all 112 `explained_in` edges weigh 1.0): MTG ch-16 = 47, MTE ch-4 = 18,
MTG ch-09 = 5, then singles. Weighted `LIMIT` cannot separate them, which is why the head
behaviour and the key-tie-break behaviour both failed.

**CDN-0099** — the frontend build and the effect: `npm run build` in `frontend/` → `BUILD_EXIT=0`,
`dist/assets/index-hbV7zID1.js` (911.43 kB) served by the restarted service.

## Live evidence after the restart (gate 5)

```
systemctl --user restart legislation-explorer.service   → active, /health 200
curl /api/rulings-list
  "id":"GSTR_2000_17","title":"GSTR 2000/17 — Goods and services tax: tax invoices  [WITHDRAWN]"
curl /api/cases/itaa-1997/8-1
  count 3, titles: "Greig v Commissioner of Taxation", "Commissioner of Taxation v Day",
  "Lean and Commissioner of Taxation" (all title != citation)
MCP get_section itaa-1997 8-1 (streamable HTTP, 10 commentary entries)
  entry 1: Master Tax Guide ch-16 "Business, Employment and Investment Deductions тАв Gifts",
           source "Australian Master Tax Guide"
  entry 2: Master Tax Examples ch-4 "Deductions", source "Australian Master Tax Examples"
  every entry: source and chapter_title non-empty
curl /api/search/suggest?q=gene&limit=8 → HTTP 200, suggestions non-empty (endpoint the
  restored effect calls)
/usr/bin/python3.12 tests/integration_test.py → exit 0, "Results: 34 passed, 0 failed"
```

## Open items handed on

* **CDN-0099 needs Harry's product sign-off** — it reverses the deliberate removal in 7066299a5. The
  code is complete, tested and live; a "no" means reverting `b0e202d0b` alone.
* **The Cyrillic assertion in CDN-0206 is E-a.** `chapter_title` for MTG ch-16 still reads
  `... Deductions тАв Gifts`: 875 master-tax-guide `section_index.json` chapter titles plus 22
  `tree.json` part titles carry the `тАв` U+0442/U+0410/U+0432 mojibake. The test measures and
  reports the count (`test_report_cyrillic_chapter_titles_e_a_pending`) and deliberately does not
  assert it — the repair is a data change for batch 3.
* **CDN-0206 slice diversity.** MTG contributes 5 rows from ch-16 and MTE 5 from ch-4; MTG ch-09
  (5 links, the second-most relevant MTG chapter) does not appear at limit 10. That is the plan's
  prescribed ranking (chapter link count first, then interleave). A within-publication
  chapter round-robin would widen the slice if Harry prefers it.
* **Graph node labels still carry citations** for 3,006 of 5,053 cases (CDN-0205's durable fix, out
  of scope here); the REST/MCP paths now name rows from the summaries corpus instead.
* Not run: `scripts/randomised_api_mcp_test.py` and `final_data_audit.py` — they write findings into
  the issues portal (side effects outside this batch).
