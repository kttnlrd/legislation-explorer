# Fix Batch: 3 High-Severity Routing/Rendering Bugs

## Scope

Fix 3 bugs found in the 2026-08-14 display audit. All are small, targeted changes. Do NOT touch anything outside the listed files. Run verification after each fix.

---

## Bug ROUTE-001: `s`-prefixed section URLs 404 (HIGH)

**Symptom:** `/itaa-1997/s8-1` and definition links like `/itaa-1997/s995-1#s995-1-deduct` render blank when opened directly or via copy-link. Tree clicks work.

**Root cause:** Frontend URL→state sync (`frontend/src/App.tsx`, useEffect at ~line 336-360) captures the section path verbatim via `window.location.pathname.match(/\/([a-z0-9-]+)\/(.+)/)` → `setActiveSection(sectionMatch[2])` gives `s8-1` (with `s` prefix). Then `api.section(act, 's8-1')` calls `/api/section/itaa-1997/s8-1` → backend route `/api/section/{act}/{section:path}` (backend/routes/acts.py line 83) does NOT strip the `s` → 404 → catch block sets `setActiveSection('')` → blank.

Meanwhile the click-handler in `frontend/src/components/MarkdownRenderers.tsx` line 46 uses regex `/\/(itaa-\d{4})\/s([^#]+)(?:#(.+))?/` which DOES strip the `s` — so in-app clicks work but direct URLs don't.

**Fix (choose the minimal correct one — prefer backend strip so ALL entry points work):**
- Option A (recommended): In `backend/routes/acts.py` `get_section()` (and wherever sections are looked up from URL params), strip a leading `s` from the section param when the remainder matches a valid section id shape: `if section.startswith('s') and len(section) > 1: section = section[1:]`. Apply to the section lookup before `get_act_section_content`. Be careful: `section` may be `s8-1`, `s995-1`, `s6`, `s160ZZU` — the prefix is always a single `s` directly attached. Also handle the treaty path and any other route that receives section ids from URLs. Do NOT strip when the id genuinely starts with `s` as part of the id (check data: sections are stored WITHOUT the s prefix, e.g. `8-1`, `995-1`, `6`, `23AH`).
- Option B: strip in the frontend URL→state sync — `setActiveSection(sectionMatch[2].replace(/^s(?=\d)/, ''))`. Less robust (only fixes one entry point; MarkdownRenderers + RulingContent links still emit `s`-prefixed hrefs that would break copy-paste).

Apply BOTH if trivial (defense in depth), but Option A is mandatory.

**Verify:**
1. `curl -s http://127.0.0.1:8765/api/section/itaa-1997/s8-1` returns 200 JSON (frontmatter.section == "8-1"), NOT SPA HTML / 404
2. `curl -s http://127.0.0.1:8765/api/section/itaa-1997/8-1` still returns 200
3. Browser: `http://127.0.0.1:8765/itaa-1997/s8-1` renders "8-1 General deductions" body
4. Browser: open `http://127.0.0.1:8765/itaa-1997/s995-1` — renders the dictionary section (may be large)
5. Regression: tree-click navigation still works

---

## Bug ROUTE-002: Treaty article direct URLs blank (HIGH)

**Symptom:** `/usa/article-03-general-definitions` renders blank content area. Tree clicks work.

**Root cause:** Frontend tree mapping (App.tsx ~line 276) builds section ids as `String(a.article)` (the article NUMBER) with `path: a.slug`. Direct URL `/usa/article-03-general-definitions` → URL parser sets `activeSection = 'article-03-general-definitions'` → `api.treatyArticle(act, 'article-03-general-definitions')` → `/api/treaties/usa/article/article-03-general-definitions` → backend route (backend/routes/treaties.py line 55-56) declares `article: int` → FastAPI returns 422 int_parsing → frontend catch treats as 404 → blank.

**Fix (minimal):**
- Backend: in `backend/routes/treaties.py`, change the article path param to accept the slug OR make the route tolerant. Two clean options:
  - Option A: keep `article: int` but add a slug→number lookup: when the article param fails int parsing, resolve the slug against the country's tree (`data/treaties/{country}/tree.json` articles array, match by slug or by title) to find the article number.
  - Option B (simpler, recommended): make the route accept a string and look up by EITHER number or slug: `@router.get("/api/treaties/{country}/article/{article}")` with `article: str`, then `try: n = int(article) except: n = resolve_slug(...)`. Look at the existing `get_treaty_article` body (treaties.py lines 56-92) to see how it currently resolves — likely already loads tree.json, so extend the lookup to match slug.
- ALSO check: does the frontend emit slug-based URLs anywhere (TreatyContent links, copy-link)? If the tree node id is the NUMBER and path is the slug, check what `TreeNode` uses for navigation — if it navigates by id (number), direct slug URLs only come from manual entry; the fix above still covers them. If it navigates by slug, the API must accept slugs regardless.

**Verify:**
1. `curl -s http://127.0.0.1:8765/api/treaties/usa/article/3` returns 200 JSON (article content)
2. `curl -s http://127.0.0.1:8765/api/treaties/usa/article/article-03-general-definitions` returns the SAME 200 JSON
3. Browser: `http://127.0.0.1:8765/usa/article-03-general-definitions` renders article content (breadcrumb `USA › Article 3`, body markdown)
4. Browser: tree-click on an article still renders

---

## Bug DEF-001: "Defined Terms" group never renders in Related panel (HIGH)

**Symptom:** SectionContent's SmartLinkPanel shows Sections/Rulings/Cases/Commentary but NEVER "Defined Terms" — even for s 8-1 which has 12 definition links.

**Root cause:** `get_section_references()` in `backend/routes/commentary.py` (line 76, `@router.get("/api/section-refs/{act}/{section}")`) loads raw markdown via `get_act_section_content()` and scans it for `\*([^*\n]+?)\*` patterns (definition-term markers). BUT the `*term*` markers are NOT in the raw markdown — they're injected at render time by `link_definitions()` which `get_section()` runs (backend/routes/acts.py line 104) but `get_section_references()` does NOT. So the regex only matches subsection markers like `(1)`, `(a)` → 0 definitions → group hidden.

**Fix (minimal, consistent with render path):**
In `backend/routes/commentary.py` `get_section_references()`, after loading `fm, body`, run the SAME definition-linking pass the render path uses so the `*term*` markers exist before the regex scan:
- `from backend.processors.markdown import link_definitions` (already imported in acts.py — check commentary.py imports)
- `body = link_definitions(body, act)` BEFORE the `_clean_markdown_for_analysis` / definition regex step
- Keep the rest unchanged.

**Verify:**
1. `curl -s http://127.0.0.1:8765/api/section-refs/itaa-1997/8-1` → `definitions` array has items (should include 'deduct' etc., 12+ terms)
2. `curl -s http://127.0.0.1:8765/api/section-refs/itaa-1997/995-1` → definitions present
3. Browser: open `http://127.0.0.1:8765/itaa-1997/8-1`, expand Related panel → "Defined Terms (N)" group visible with term list
4. Regression: `curl -s http://127.0.0.1:8765/api/section-refs/gst-1999/9-5` still returns valid JSON (no crash)

---

## General constraints

- Files in scope: `backend/routes/acts.py`, `backend/routes/treaties.py`, `backend/routes/commentary.py`, `frontend/src/App.tsx` (only if Option B for ROUTE-001), `frontend/src/api.ts` (only if needed for treaty path).
- Do NOT modify data files, the spec doc, or other acts' data.
- Do NOT create new components/routes unless unavoidable (prefer extending existing lookup logic).
- After changes, run the verification steps for ALL three bugs (they share the section-lookup path — make sure fixes don't conflict).
- Report what you changed per bug + verification output.
