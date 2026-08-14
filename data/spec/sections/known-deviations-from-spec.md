---
act: spec
section: "12"
title: "Known deviations from spec (open bugs)"
part: "12"
division: ""
---

| ID | Type | Deviation | Severity |
|----|------|-----------|----------|
| TRTY-001 | Treaty | MCP `get_treaty_article` includes raw YAML frontmatter in content (42 countries) — frontend strips it, MCP does not | Medium |
| ROUTE-001 | All | `s`-prefixed section URLs (`/itaa-1997/s8-1`, definition links `/itaa-1997/s995-1#...`) 404 — URL→state parser passes `s8-1` verbatim to `/api/section`; backend doesn't strip. Tree clicks work (bare ids); direct/copied links break | **High** |
| ROUTE-002 | Treaty | Direct article URLs (`/usa/article-03-general-definitions`) render blank — backend `/api/treaties/{country}/article/{article}` expects integer; URL parser sends slug. Tree clicks work | **High** |
| DEF-001 | Definitions | "Defined Terms" group in Related panel never renders — `get_section_references` reads raw markdown without running `link_definitions()` (acts.py:104), so its `*term*` regex only finds subsection markers, 0 definitions | **High** |
| RUL-001 | Rulings | Normal rulings (CR/TR/TD) return no body — summary-only by design (backend comment); full text via Download. Spec section 3 updated to match | By design |
| #4 | Definitions | s 995-1 / s 6(1) / s 195-1 render 310KB inline dump instead of expandable tree | Medium |
| DEF-002 | Definitions | `truncated` flag inconsistent — 52-char cross-ref "deduct" flagged truncated=True | Low |
| SEARCH-001 | Search | treaty/RG/insolvency types missing from filter tabs (only section/ruling/case/commentary) | Low |
| UI-001 | Spec act | Spec breadcrumb shows empty `DIVISION` segment (`SPEC › PART 0 › DIVISION`) | Cosmetic |
| UI-002 | Treaty | Tree shows slug `usa` as node id ("usa — United States of America") — spec says slug-like ids hidden | Cosmetic |
| UI-003 | Treaty | Article heading duplicated — TreatyContent renders h1 from article title AND the markdown body contains its own `# Article N — Title` heading | Cosmetic |

*Spec generated 2026-08-14. Audit 2026-08-14: 11 types assessed — 2 high-sev route bugs, 1 high-sev definitions bug, rest per spec.*
