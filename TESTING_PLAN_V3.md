# Legislation Explorer — V3 Data Integrity Testing Plan

## How to use this document

Each data type has a **test procedure** (MCP + visual), a **common bugs register** (expand as bugs are found), and **cleanup instructions** (scripts or AI subagent prompts).

**Test modes:**
- **MCP recall** — call the MCP tool directly via curl or the Claude MCP client. Verifies the tool returns correct, complete data.
- **Visual inspection** — open the frontend and verify rendered output matches expectations.
- **Data audit** — inspect the raw data files on disk for structural issues.

---

# 1. Primary Legislation Sections (ITAA 1997, ITAA 1936, TAA 1953, GST 1999, Corps Act, AML/CTF, NZ IT)

## Test procedure

### MCP recall
```bash
# 1. List all acts — verify count and names
curl -s $MCP_URL -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_acts","arguments":{}}}'

# 2. Get section tree — verify part → division → section hierarchy
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_act_tree","arguments":{"act":"itaa-1997"}}}'

# 3. Get specific section — verify body, title, commentary, rulings, cases
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_section","arguments":{"act":"itaa-1997","section":"8-1"}}}'

# 4. Search across all legislation
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_legislation","arguments":{"query":"residence"}}}'

# 5. Resolve alias
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"resolve_alias","arguments":{"reference":"s 100A"}}}'
```

**Checklist:**
- [ ] `list_acts` returns all 7 primary acts with correct names
- [ ] `get_act_tree` returns valid tree — all parts have ids, all sections have paths
- [ ] `get_section` returns frontmatter (act, section, title) + body + related content
- [ ] Sections with hyphens (8-1) resolve correctly
- [ ] Sections without hyphens (23AH) resolve correctly
- [ ] `resolve_alias` works for common aliases (Div 7A, Part IVA, s 100A)
- [ ] `search_legislation` returns results with snippets, ranked by BM25

### Visual inspection
- Open `https://<host>/itaa-1997` → sidebar loads tree
- Click a section → body renders with proper formatting
- Related panel shows commentary, cases, rulings, definitions
- Definition popover works on italicised terms
- Search panel returns results with act/section/title/snippet

## Common bugs register

| ID | Severity | Area | Status | Found in |
|----|----------|------|--------|----------|
| TRTY-001 | Medium | Treaty articles — `get_treaty_article` content includes raw YAML frontmatter (`---\ncountry:...`). All 42 countries affected. Section/insolvency/commentary tools strip frontmatter correctly; treaty tool does not. | **New** | V2.8 |
| CASES-001 | High | MCP `search_cases` — runtime error: `cannot access free variable 'words' where it is not associated with a value in enclosing scope`. Root cause: `words = query.split()` is inside an `if` block (line 1040); when FTS5 returns enough results (≥ limit*2), the `if` is skipped and `words` never gets assigned. Nested `_relevance_score` function at line 1077 references `words` unconditionally. Python 3.12 catches this at compile time. Fix: move `words = query.split()` above the `if` block. | **New** | V2.8 |
| CASES-002 | Low | 4 citations duplicated (2-4×) in `case_summaries_fts` — 11 extra rows from repeated indexing runs | Open | V2.8 |
| RLG-004 | Low | `list_rulings` returns results keyed by `by_year` not flat `rulings` array — not a bug per se but the response structure differs from what `len(r.get('rulings',[]))` would find. Use `by_year` key instead. | Open | V2.8 |
| CMTY-001 | Medium | `master-tax-guide` 1,404 index entries vs 1,393 files — **re-verified: index now 1,393 = files 1,393. No gap.** This was resolved. | Resolved | V2.8 |
| TAA-001 | Medium | TAA 1953: 1,047 orphan files on disk not referenced in tree.json (817 in `part-unknown/`, 229 in `part-v/`, 1 in `part-iii/`) | Open | V2.8 |
| TAA-002 | Low | TAA 1953: section 45B appears 3× in tree.json (duplicate entry) | Open | V2.8 |
| EG-001 | Medium | Master Tax Examples: 23 orphan .md files (7.4%) with valid content not in `section_index.json` | Open | V2.8 |
| CASE-005 | Medium | 327 citations in `case_catchwords.json` (8.3%) have no matching `.html` file — mostly pre-2000 HCA, FCA, AATA | Open | V2.8 |
| DEF-003 | Low | `definitions_all.json` has 187 duplicate anchors in itaa-1936, 2 in gst-1999, 113 terms missing 'anchor' field in corporations-act-2001 | Open | V2.5 |

## Cleanup instructions

### AI Subagent Prompt — Section Data Audit
```
Goal: Audit all section data for {act} in /home/harrison/legislation-explorer/data/{act}/

1. Read data/{act}/tree.json — note the tree structure (parts, divisions, sections)
2. For each section entry, verify the path/to/file.md exists on disk
3. Read 5 random section files and check:
   - YAML frontmatter has act, section, title fields
   - Body content is clean markdown (no HTML artifacts, no PDF noise)
   - No smart-quote issues in the body
4. Report: sections in tree vs files on disk (gaps), frontmatter issues found, body quality

Return: structured report with pass/fail per section, examples of any issues found
```

### Existing scripts
- `python3.12 scripts/validate_data.py` — checks tree paths exist, definitions integrity
- `python3.12 scripts/scan-formatting-bugs.py` — scans for formatting issues
- `python3.12 scripts/normalize_sections.py` — normalises section formatting
- `python3.12 scripts/clean_pdf_noise.py` — removes PDF artifacts
- `python3.12 scripts/fix-smart-quotes.py` — normalises smart quotes
- `python3.12 scripts/clean_footnotes.py` — cleans footnotes

---

# 2. Double Tax Agreements (42 countries)

## Test procedure

### MCP recall
```bash
# 1. List all articles for a country
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_treaty_articles","arguments":{"country":"usa"}}}'

# 2. Get a specific article
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_treaty_article","arguments":{"country":"usa","article":1}}}

# 3. Test error handling — unknown country
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_treaty_articles","arguments":{"country":"narnia"}}}'

# 4. Test error handling — unknown article
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_treaty_article","arguments":{"country":"usa","article":999}}}
```

**Checklist:**
- [ ] All 42 countries return article lists with correct counts (check 3+ countries)
- [ ] Each article returns title + content (no frontmatter leaked)
- [ ] `list_treaty_articles` returns correct treaty name, schedule number, total count
- [ ] Unknown country returns error + list of available countries
- [ ] Unknown article returns error + list of valid article numbers

### Visual inspection
- Open the act picker → "International Tax" → "Tax Treaties"
- Click a country in the sidebar tree
- Article renders with proper formatting
- Click different articles — all load correctly

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| TRTY-001 | Article content leaks YAML frontmatter to user — ALL 42 countries affected. Section/insolvency/commentary tools strip frontmatter correctly; treaty tool does not. | **New** | V2.8 |
| TRTY-002 | `get_treaty_article` article param is string, backend expects int — works as int in practice, doc only | Low | V2.8 |

## Cleanup instructions

### AI Subagent Prompt — Treaty Data Audit
```
Goal: Audit treaty data integrity for all 42 countries in /home/harrison/legislation-explorer/data/treaties/

1. For each country directory, read tree.json and verify:
   - All article file paths exist on disk
   - Article count matches declared `total`
   - Article numbers are sequential without gaps
2. For 5 random countries, read 3 article files each and check:
   - YAML frontmatter has: country, country_slug, treaty_schedule, article, title
   - No duplicate content across articles
   - Body has substantive content (not just "Reserved" or empty)
3. Report: tree.json integrity per country, frontmatter issues, content quality flags

Return: per-country pass/fail with specific issues found
```

### Existing scripts
- `python3.12 scripts/validate_data.py` — covers some treaty validation
- `pipeline/ingest_dta.py` — DTA ingestion pipeline (for re-processing)

---

# 3. ATO Rulings (11,930 files)

## Test procedure

### MCP recall
```bash
# 1. List rulings with filters
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_rulings","arguments":{"type":"TR","year":"2024"}}}'

# 2. Get specific ruling
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_ruling","arguments":{"citation":"TR 2024/1"}}}

# 3. Get counts
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_rulings","arguments":{"counts_only":true}}}
```

**Checklist:**
- [ ] `list_rulings` returns correct count, pagination works
- [ ] `get_ruling` returns frontmatter + body + metadata
- [ ] Ruling types (TR, TD, CR, PR, GSTR, IT, MT, TA, SGR, ATOID, AID) all resolve
- [ ] 2-digit year citations work (e.g. TD 94/82)
- [ ] Ruling body does not leak YAML frontmatter
- [ ] Citation format displayed correctly (TR_2012_1 → TR 2012/1)

### Visual inspection
- Click "Rulings" in sidebar → tree of ruling types/years loads
- Click a ruling → content panel shows descriptive_title, subject, question, background, ruling, decision
- Search "TR 2024" → rulings appear in results
- Section page shows "Related rulings" in Related panel

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| RLG-001 | Ruling FTS index shows citation as title when summary file missing | Fixed | V2.8 |
| RLG-002 | Some ruling bodies contain HTML artifacts from scraped source | Open | V2.7 |
| RLG-003 | `get_ruling` may return full 58KB body without truncation | Investigate | V2.5 |
| RLG-004 | `list_rulings` results keyed by `by_year` not flat `rulings` array — consumers must check `by_year` key, not `rulings` | Known | V2.8 |

## Cleanup instructions

### AI Subagent Prompt — Ruling Data Audit
```
Goal: Audit ATO ruling data integrity in /home/harrison/legislation-explorer/data/rulings/

1. Read ruling_manifest.json — note total count and ruling types present
2. Verify manifest entries match actual .txt files on disk (no orphans either way)
3. For 20 random rulings (spread across types), check:
   - .txt file exists and has content (not empty)
   - summary JSON has: citation, title, type, year (if applicable)
   - Body does not contain raw HTML tags or PDF artifacts
4. Report: manifest-file mismatch count, empty files, type distribution, sample issues

Return: structured report with pass/fail per check
```

### Existing scripts
- `python3.12 scripts/fix_bad_titles.py` — patches missing summary titles
- `python3.12 scripts/fix_errors.py` — general fixes
- `pipeline/extract_ato_ruling_pdfs.py` — PDF extraction pipeline
- `pipeline/fetch_ato_id_content.py` / `fetch_ato_id_content_v2.py` — ruling content fetching

---

# 4. Tax Cases (6,167 HTML files)

## Test procedure

### MCP recall
```bash
# 1. Search cases
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_cases","arguments":{"query":"residence","limit":20}}}

# 2. Get specific case
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_case","arguments":{"citation":"(2024) 300 FCR 1"}}}

# 3. Get legislation references from a case
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"case_legislation_refs","arguments":{"citation":"(2024) 300 FCR 1"}}}
```

**Checklist:**
- [ ] `search_cases` returns results with case name, court, citation, snippet
- [ ] `get_case` returns headnote + judgment with paragraph refs
- [ ] Case content renders with proper formatting, not raw HTML
- [ ] Bracketless citations normalised (2024 HCA 18 → [2024] HCA 18)
- [ ] `case_legislation_refs` returns sections cited
- [ ] Related cases appear in section pages

### Visual inspection
- Click "Tax Cases" in sidebar → list of cases by year/court loads
- Click a case → headnote, judgment, related provisions, related rulings
- Search panel returns case results with name/citation
- Section page → Related panel → "Related Cases" section

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| CASE-001 | Bracketless citations not normalised | Fixed | V2.8 |
| CASE-002 | Some HTML case files contain navigation markup | Open | V2.7 |
| CASE-003 | Case search returns sections from section FTS instead of case FTS | Fixed | V2.8 |
| CASE-004 | Case content may include raw HTML tags if strip_scraped_markup misses edge cases | Open | V2.8 |
| CASES-001 | **MCP `search_cases` runtime error** — `cannot access free variable 'words'` when FTS5 returns ≥limit*2 results. `words = query.split()` is inside an `if` block; nested `_relevance_score()` references it unconditionally. | **New** | V2.8 |
| CASES-002 | 4 citations duplicated (2-4×) in `case_summaries_fts` — 11 extra rows from repeated indexing | Open | V2.8 |
| CASE-005 | 327 citations in `case_catchwords.json` (8.3%) have no matching `.html` file | Open | V2.8 |

## Cleanup instructions

### AI Subagent Prompt — Case Data Audit
```
Goal: Audit tax case data integrity in /home/harrison/legislation-explorer/data/case_texts/

1. Walk the case_texts/ directory — count total .html files
2. Check case_catchwords.json — verify entries match existing .html files
3. Check section_case_index.json — verify referenced citations exist in case_texts/
4. For 15 random .html files, verify:
   - File is valid HTML (not empty, has structure)
   - Contains substantive content (not just "Judgment reserved" or similar)
   - No excessive markup or navigation artifacts
5. Report: file counts, index integrity, content quality flags

Return: structured report with gap analysis and sample issues
```

### Existing scripts
- `scripts/validate_data.py` — checks case references
- `scripts/check_indexes.py` / `check_indexes_v2.py` — checks citation_index + section_case_index
- `pipeline/scrape_ato_ids.py` — ATO ID content scraping

---

# 5. Regulatory Guides (ASIC RGs)

## Test procedure

### MCP recall
```bash
# 1. Get a regulatory guide
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_regulatory_guide","arguments":{"rg_number":1}}}

# 2. Get sections referenced by an RG
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_rg_sections","arguments":{"rg_number":1}}}
```

**Checklist:**
- [ ] `get_regulatory_guide` returns subject, background, ruling, cases/legislation referenced
- [ ] RG body is present and clean
- [ ] PDF download URL is valid
- [ ] `get_rg_sections` returns Corps Act sections with titles
- [ ] Corps Act section page shows "Related RGs" in Related panel

### Visual inspection
- Click "Corporate Law" → "ASIC RGs" → tree loads by RG number
- Click an RG → structured summary panel with status badge
- PDF download button works
- Corps Act section → Related panel → shows related RGs

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| RG-001 | RG body may miss sections if source docx parsing failed | Open | V2.8 |
| RG-002 | Some RG PDFs may not exist despite being listed | Open | V2.8 |
| RG-003 | Reverse section index (section→RGs) may be incomplete | Open | V2.8 |

## Cleanup instructions

### AI Subagent Prompt — Regulatory Guide Data Audit
```
Goal: Audit ASIC Regulatory Guide data in /home/harrison/legislation-explorer/data/regulatory-guides/

1. Read rg_manifest.json — check total count and fields
2. For each RG entry, verify:
   - Summary JSON exists in summaries/ (if applicable)
   - Text file exists in texts/
   - PDF exists in pdfs/ (if has_pdf=true)
3. For 10 random RGs, read the text file and check:
   - Body has substantive content
   - No excessive markup artifacts
4. Read section_rg_index.json — check structure and cross-references

Return: structured report with gaps and issues
```

---

# 6. Commentary (Master Tax Guide, Master Tax Examples, Master GST Guide)

## Test procedure

### MCP recall
- Commentary is accessed via `get_section` with `include_commentary=True`
```bash
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_section","arguments":{"act":"itaa-1997","section":"8-1","include_commentary":true}}}
```

**Checklist:**
- [ ] Commentary appears in `get_section` response when `include_commentary=true`
- [ ] Commentary snippet (500 chars) + locator returned when `include_commentary=false`
- [ ] Section_index.json entries match actual .md files on disk

### Visual inspection
- Navigate to a section → Related panel → "Commentary" section
- Click a commentary entry → expanded content renders

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| CMTY-001 | `master-tax-guide` index has 1,404 entries but only 1,393 files (11 missing) | Open | V2.8 |
| CMTY-002 | Commentary section_index entries for GST may cite wrong act | Open | V2.7 |

## Cleanup instructions

### AI Subagent Prompt — Commentary Data Audit
```
Goal: Audit Master Guide commentary data in /home/harrison/legislation-explorer/data/

1. For each of master-tax-guide, master-tax-examples, master-gst-guide:
   - Read section_index.json — note total entries
   - Count actual .md files in sections/
   - Report any index entries without matching files and vice versa
2. For 10 random .md files across all 3 guides, check:
   - File has substantive content (not empty or placeholder)
   - YAML frontmatter has required fields
3. Check that commentary links in section pages actually resolve

Return: gap analysis per guide, sample content issues
```

---

# 7. Insolvency (Keays Textbook)

## Test procedure

### MCP recall
```bash
# 1. Search insolvency text
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"insolvency_search","arguments":{"query":"winding up","limit":20}}}

# 2. Get a chapter
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"insolvency_get_chapter","arguments":{"chapter":1}}}
```

**Checklist:**
- [ ] `insolvency_search` returns results with chapter number, title, snippet
- [ ] `insolvency_get_chapter` returns full chapter text
- [ ] Chapter content is clean markdown (no scraped artifacts)

### Visual inspection
- Click "Corporate Insolvency" → "Keays Insolvency" → chapter tree loads
- Click a chapter → body renders

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| INSV-001 | Chapter count mismatch between tree and FTS index | Open | V2.7 |
| INSV-002 | Chapter content may include PDF artifacts | Open | V2.7 |

## Cleanup instructions

### AI Subagent Prompt — Insolvency Data Audit
```
Goal: Audit Keays Insolvency data in /home/harrison/legislation-explorer/data/insolvency-keays/

1. Read ch-tree.json — note total chapters and list
2. Verify each chapter's file path exists on disk
3. Read 5 random chapter files and check:
   - YAML frontmatter has chapter, title
   - Body has substantive content
   - No HTML artifacts or PDF noise
4. Report: tree integrity, file gaps, content quality

Return: structured report
```

---

# 8. Definitions Index

## Test procedure

### MCP recall
```bash
curl ... -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_definition","arguments":{"act":"itaa-1997","term":"resident"}}}
```

**Checklist:**
- [ ] `get_definition` searches across all acts, prefers requested act
- [ ] Results include `also_defined_in` for cross-act matches
- [ ] Terms with Unicode characters resolve (curly quotes normalised to ASCII apostrophes)
- [ ] Definition text is complete and not truncated

### Visual inspection
- Any section page → italicised terms are clickable
- Click a term → definition popover appears with text + source section

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| DEF-001 | Unicode keys not normalised (curly quotes in PDF-extracted text) | Fixed | V2.8 |
| DEF-002 | Definition boundary algorithm fails for non-alphabetical section ordering | Fixed | V2.8 |
| DEF-003 | `definitions_all.json` may be absent (falls back to `definitions.json`) | Fixed | V2.7 |

## Cleanup instructions

### AI Subagent Prompt — Definitions Data Audit
```
Goal: Audit definitions index in /home/harrison/legislation-explorer/data/

1. Check which definitions files exist: definitions.json, definitions_all.json, definitions_comprehensive.json
2. For the largest file, verify:
   - Total entry count is reasonable (not truncated)
   - Each entry has: term, act, section, text
   - No duplicate term+act+section combinations
3. Spot-check 20 random terms — verify the referenced section+act actually exists
4. Report: file presence, integrity, sample checks

Return: structured report
```

---

# 9. Smartlinks / Cross-References

## Test procedure

### MCP recall
- Smartlinks are embedded in `get_section` response
- Verify `related_sections`, `related_rulings`, `related_cases`, `related_commentary` arrays are populated

**Checklist:**
- [ ] Each section returns related content arrays
- [ ] Related section references resolve to valid sections
- [ ] No dead links in smartlink_index.json

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| SMART-001 | Smartlink may reference sections that don't exist | Open | V2.7 |
| SMART-002 | Citation index may have stale entries after data re-ingestion | Open | V2.8 |

---

# 10. Search Index Integrity

## Test procedure

### Direct SQLite inspection
```bash
# Check FTS table counts
sqlite3 search_index.db "SELECT 'sections_fts', COUNT(*) FROM sections_fts;"
sqlite3 search_index.db "SELECT 'rulings_fts', COUNT(*) FROM rulings_fts;"
sqlite3 search_index.db "SELECT 'treaties_fts', COUNT(*) FROM treaties_fts;"
sqlite3 search_index.db "SELECT 'insolvency_fts', COUNT(*) FROM insolvency_fts;"
sqlite3 search_index.db "SELECT 'case_summaries_fts', COUNT(*) FROM case_summaries_fts;"

# Check for duplicate entries
sqlite3 search_index.db "SELECT act, section, COUNT(*) FROM sections_fts GROUP BY act, section HAVING COUNT(*) > 1;"

# Check for empty content
sqlite3 search_index.db "SELECT act, section FROM sections_fts WHERE length(content) < 50 LIMIT 20;"

# Verify tokenization
sqlite3 search_index.db "SELECT rowid, snippet(sections_fts, 2, '<b>', '</b>', '...', 32) FROM sections_fts WHERE sections_fts MATCH 'residence' LIMIT 5;"
```

**Checklist:**
- [ ] All FTS tables have reasonable counts (sections: ~70K+, rulings: ~11K+, treaties: ~1K+)
- [ ] No duplicate act+section combinations
- [ ] No entries with empty/trivial content
- [ ] BM25 ranking returns relevant results first
- [ ] Prefix search works (partial word matching)

## Common bugs register

| Bug ID | Description | Status | Found in |
|--------|-------------|--------|----------|
| FTS-001 | Sections with blank content pollute search results | Open | V2.7 |
| FTS-002 | Case FTS index doesn't have dedicated meta table | Open | V2.8 |

## Cleanup instructions

### Rebuild search index
```bash
cd /home/harrison/legislation-explorer
python3.12 scripts/rebuild_search_index.py
```

---

# 11. Frontend Rendering Integrity

## Visual inspection checklist (browser)

For each act/dataset, open the frontend and verify:

### Navigation & Picker
- [ ] Act picker shows all domain groups
- [ ] Picking an act loads its tree in the sidebar
- [ ] URL updates correctly (`/<act>`)
- [ ] Back/forward browser navigation works
- [ ] Mobile sidebar drawer opens/closes

### Tree View
- [ ] Parts expand/collapse
- [ ] Divisions expand/collapse
- [ ] Sections are clickable
- [ ] Active section is highlighted
- [ ] Deeply nested structures render without overflow

### Section Content
- [ ] Title, act reference, section number displayed
- [ ] Body renders as formatted markdown
- [ ] Long sections scroll smoothly
- [ ] Definition popover works (click italicised terms)
- [ ] Links to other sections work (<a href="/itaa-1997/s8-1">)

### Related Panel
- [ ] Sections tab — shows cross-referenced sections
- [ ] Rulings tab — shows related rulings
- [ ] Cases tab — shows related cases with citations
- [ ] Commentary tab — shows CCH commentary entries
- [ ] Defined terms tab — shows terms defined in this section
- [ ] Tabs are collapsible

### Treaty Content
- [ ] Article renders without YAML frontmatter in body
- [ ] Country name and article number displayed
- [ ] Clicking different countries in tree loads correct articles

### Ruling Content
- [ ] Ruling type + year displayed
- [ ] Descriptive title shown
- [ ] Subject, question, background sections rendered
- [ ] Full body toggle-able
- [ ] Related legislation/cases links work

### Case Content
- [ ] Case headnote displayed
- [ ] Judgment body rendered
- [ ] Related provisions listed
- [ ] Related rulings listed
- [ ] AUSTLII / HCA / FedCourt links work

### Search
- [ ] Search input works
- [ ] Results show act, section, title, snippet
- [ ] Filter tabs (All, Sections, Rulings, Cases, Commentary) work
- [ ] Pagination works (if >20 results)
- [ ] Clicking a result navigates to that section

---

# 12. Cross-Cutting Tests

## Known bug search
For each known bug, verify it's fixed:
```bash
# Check HTML artifacts don't appear in section body
curl ... -d '{"name":"get_section","arguments":{"act":"itaa-1997","section":"995-1"}}' | grep -i 'html\|<div\|<span\|<p>'

# Check YAML frontmatter doesn't leak
curl ... -d '{"name":"get_treaty_article","arguments":{"country":"usa","article":1}}' | grep -i 'country_slug\|---'

# Check bracketless citations normalised
curl ... -d '{"name":"get_case","arguments":{"citation":"[2024] HCA 18"}}'
```

## Performance checks
- [ ] Tree loads in <2s for each act
- [ ] Section content loads in <1s
- [ ] Search returns in <3s
- [ ] Graph modal renders with <5s delay

## Regression checks
- [ ] All previously fixed bugs stay fixed (run full test suite)
- [ ] New features don't break existing functionality

---

# Quick Reference: Test Command by Data Type

| Data Type | MCP Tool(s) | Frontend Path |
|-----------|-------------|---------------|
| Section | `get_section`, `search_legislation` | `/<act>/<section>` |
| Act tree | `get_act_tree`, `list_acts` | `/<act>` |
| Treaty | `list_treaty_articles`, `get_treaty_article` | `/treaties/<country>/<article>` |
| Ruling | `get_ruling`, `list_rulings` | `/rulings/<citation>` |
| Case | `get_case`, `search_cases` | `/?act=tax-cases` |
| RG | `get_regulatory_guide`, `get_rg_sections` | `/?act=regulatory-guides` |
| Commentary | `get_section` with `include_commentary=true` | Section → Related → Commentary |
| Insolvency | `insolvency_get_chapter`, `insolvency_search` | `/?act=insolvency-keays` |
| Definition | `get_definition` | Section → click italicised term |
| Search | `search_all`, `search_legislation` | Search panel |

---

# Automated Audit Script

To run the full data integrity audit in one shot:
```bash
cd /home/harrison/legislation-explorer

# Tree structure validation
python3.12 scripts/validate_data.py

# Search index rebuild + stats
python3.12 scripts/rebuild_search_index.py --check-only

# Section-to-file mapping
python3.12 -c "
import json
from pathlib import Path

acts = ['itaa-1997', 'itaa-1936', 'gst-1999', 'taa-1953', 'corporations-act-2001',
        'nz-it-2007', 'aml-ctf-2006', 'aml-ctf-rules-2007']
for act in acts:
    tree_file = Path(f'data/{act}/tree.json')
    if not tree_file.exists():
        print(f'MISSING: {act}/tree.json')
        continue
    tree = json.loads(tree_file.read_text())
    sections_in_tree = 0
    for part in tree.get('parts', []):
        for div in part.get('divisions', []):
            for sub in div.get('subdivisions', []):
                sections_in_tree += len(sub.get('sections', []))
            sections_in_tree += len(div.get('sections', []))
        sections_in_tree += len(part.get('sections', []))
    print(f'{act}: {sections_in_tree} sections in tree')

# Treaty integrity
treaties_dir = Path('data/treaties')
for d in sorted(treaties_dir.iterdir()):
    if d.is_dir():
        tree = json.loads((d / 'tree.json').read_text())
        articles = len(tree.get('articles', []))
        files_ok = sum(1 for a in tree.get('articles', []) if (d / a['file']).exists())
        print(f'Treaty {d.name}: {articles} articles, {files_ok}/{articles} files exist')
"
```

---

# Cross-Cutting Findings (V3 Scan — 2026-08-14)

## YAML Frontmatter Leak Analysis

All raw data files checked for `---` at start. MCP tools tested to verify frontmatter is stripped.

| Data Type | Raw files have `---` | MCP strips it | Status |
|-----------|:---:|:---:|--------|
| Sections (all acts) | ✅ Yes | ✅ Yes | Clean |
| **Treaty articles (42 countries)** | ✅ Yes | **❌ No** | **TRTY-001** |
| Rulings | ❌ No (plain text) | N/A | Clean |
| Insolvency chapters | ✅ Yes | ✅ Yes | Clean |
| Commentary (Master Guides) | ✅ Yes | ✅ Yes | Clean |
| Regulatory Guides | ❌ No (plain text) | N/A | Clean |
| Cases | ❌ No (HTML) | N/A | Clean |

**Conclusion**: Treaty articles are the **only** data type with frontmatter leak. Fix: add YAML stripper to `get_treaty_article`, consistent with section/insolvency tools.

## MCP Tool Runtime Errors

All 22 tools stress-tested. **One failure:**

| Tool | Error | Root Cause |
|------|-------|------------|
| `search_cases` | `cannot access free variable 'words'` | `words = query.split()` inside an `if` block (line 1040). When FTS5 returns ≥limit×2 results, `if` skipped → `words` never assigned. Nested `_relevance_score()` uses it unconditionally (lines 1091, 1094). Python 3.12 catches at compile time. Fix: move `words = query.split()` above the `if`. |
| Other 21 tools | None | — |

## Data Coverage Gaps Found

| Gap | Size | Impact |
|-----|------|--------|
| TAA 1953: orphan files in `part-unknown/` | 817 files | Sections on disk but invisible to tree/UI |
| TAA 1953: orphan files in `part-v/` | 229 files | Same |
| TAA 1953: tree.json 45B duplication | 2 extra entries | Section shown 3× in tree |
| Master Tax Examples: orphan .md files | 23 files (7.4%) | Commentary invisible to UI |
| Case catchwords without .html files | 327 citations (8.3%) | Referenced cases don't exist on disk |
| FTS case_summaries duplicates | 11 extra rows | Same results appearing multiple times |
| Definitions: missing anchor fields | 113 terms (corps act) | Definitions can't link to section text |

---

# Appendix: Environment Variables for Tests

```bash
export MCP_URL="http://localhost:8765/mcp"
export TOKEN="$(grep LEGISLATION_BEARER_TOKEN /path/to/.env | cut -d= -f2)"
```