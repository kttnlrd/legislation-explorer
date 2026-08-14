# Bug: Stray "s" prefix in search results + broken ruling navigation

## Bug 1 — Stray "s" in section display

**File:** `frontend/src/components/SearchPanel.tsx`, line 329

```tsx
: `${shortActName(r.act)} s${r.section}`
```

**Problem:** Prepends literal `s` before every section number in search results.
- `ITAA97 s832-530` — "s" looks like part of the section ID
- `NZ IT07 sDE-2` — "sDE-2" looks like a single identifier
- `ITAA97 s8-5` — redundant with the green "Sec" badge
- No space between `s` and section number

**Impact:** Every search result showing a legislation section has a confusing "s" prefix. Badge already says "Sec", making this redundant.

**Fix:** Remove the literal `s` prefix. Change to `${shortActName(r.act)} ${r.section}`.

---

## Bug 2 — Ruling links in markdown content cause full page reload

**File:** `frontend/src/components/MarkdownRenderers.tsx`, line 47

```tsx
const rulingMatch = href.match(/\/rulings\/s(.+)/)
```

**Problem:** Regex expects `/rulings/sCITATION` but actual URLs are `/rulings/CITATION` (no `s`).
- A link like `/rulings/IT%201` never matches `rulingMatch`
- Falls through to default `<a>` tag → full page reload (breaks SPA)

**Impact:** All cross-reference links to rulings in section content, case content, and ruling body trigger full page navigations.

**Fix:** Remove the literal `s` from the regex: `href.match(/\/rulings\/(.+)/)`

---

## Bug 3 — URL→state sync checks section before ruling (wrong match wins)

**File:** `frontend/src/App.tsx`, lines 286-298

```tsx
const sectionMatch = window.location.pathname.match(/\/([a-z0-9-]+)\/(.+)/)
const rulingMatch = window.location.pathname.match(/\/rulings\/(.+)/)

if (rulingMatch) { ... }
else if (sectionMatch) { ... }  // sectionMatch ALSO matches /rulings/IT 1
```

**Problem:** Regex `\/([a-z0-9-]+)\/(.+)` matches `/rulings/IT%201` with `[a-z0-9-]` matching `rulings`. Since `sectionMatch` is declared first, both regexes match but ruling is checked first with `if/else if`. Actually the current order is: `if (rulingMatch)` THEN `else if (sectionMatch)` — this order IS correct.

**Wait** — the order is right, but `sectionMatch` is a broader pattern that also captures `/rulings/...` as `{act: rulings, section: ...}`. The `if/else if` chain checks rulingMatch first (correct), so this isn't actually a bug if rulingMatch is checked first.

**Reality:** Bug 3 is NOT a real bug — the `if (rulingMatch)` fires first and `sectionMatch` is never reached for `/rulings/X` URLs.

---

## Bug 4 — Navbar SearchPanel doesn't handle rulings (potential)

**File:** `frontend/src/App.tsx`, lines 597-614 vs 802-820

Both SearchPanel instances have the same inline handler. Bug 4 is already fixed.

---

## Verified issues to fix

1. **SearchPanel.tsx:329** — Remove literal `s` from `${shortActName(r.act)} s${r.section}` 
2. **MarkdownRenderers.tsx:47** — Remove literal `s` from `\/rulings\/s` regex

---

## Reproduction

For Bug 1:
1. Open https://legislation.scriptkitty.yachts
2. Search for "deduction"
3. Observe "sDE-2", "s832-530", "sEH-7" in result titles

For Bug 2:
1. Open a ruling with cross-referenced sections
2. Click a link to another ruling
3. Page fully reloads instead of SPA navigation

---

## Severity

Bug 1: **Medium** — cosmetic but confusing (especially for NZ section IDs)
Bug 2: **Low** — only affects markdown content links (rulings/cases)
