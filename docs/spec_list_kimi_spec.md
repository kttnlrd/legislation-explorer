# Spec List Data Type — Implementation Spec

## Goal

Add a "Display Spec" data type to the Legislation Explorer: a browsable tree where each node is a data-type section from the display spec, rendered through the existing tree + markdown machinery. No new React components, no new backend routes.

## Master document

`/home/harrison/legislation-explorer/docs/DISPLAY_SPEC.md` — contains 14 `## N. <Title>` sections (0. Global conventions … 12. Known deviations). This is the SOURCE OF TRUTH.

## Approach (ponytail)

Backend `list_acts()` auto-discovers acts by scanning `data/*/tree.json` (backend/routes/acts.py line 26-29). The frontend renders any act's tree + sections through existing TreeNode / SectionContent. Therefore the spec data type is **data only**:

1. Create `data/spec/tree.json` — one Part per `## N.` heading in DISPLAY_SPEC.md. Each Part has a single Section with a markdown path. Title = the heading text (minus the number).
2. Create `data/spec/sections/` — one `.md` file per section, each with YAML frontmatter (`act: spec`, `section: <slug>`, `title: <heading>`), body = the section's content from DISPLAY_SPEC.md.
3. Add `spec` to the DOMAINS act picker in `frontend/src/App.tsx` (new group `{ label: 'System', ids: ['spec'] }` or append to an existing group — pick the least intrusive).

## File details

### tree.json shape (follow existing acts exactly)

```json
{
  "act": "Display Spec",
  "parts": [
    {
      "id": "0",
      "title": "Global conventions",
      "divisions": [],
      "sections": [
        { "id": "0", "title": "Global conventions", "path": "0-global-conventions.md" }
      ]
    },
    ...
  ]
}
```

- `id` = the section number (string)
- `path` = the markdown filename

### Section markdown shape

```markdown
---
act: spec
section: "0"
title: Global conventions
part: "0"
division: ""
---
<body content from DISPLAY_SPEC.md, unchanged>
```

Keep the body EXACTLY as in DISPLAY_SPEC.md (markdown tables, code blocks, everything). Do not paraphrase.

### Frontend

In `frontend/src/App.tsx` DOMAINS array, add a group. Check `shortActName` in `frontend/src/utils/display.ts` — add `spec` → `Display Spec` mapping if it falls back to ugly casing.

## Generation script (recommended)

Write `scripts/generate_spec_data.py` that:
- Reads `docs/DISPLAY_SPEC.md`
- Splits on `## ` headings (line starts with `## ` — careful: `###` headings inside sections must NOT split)
- Writes `data/spec/tree.json` and `data/spec/sections/*.md`
- Idempotent (safe to re-run after doc edits)

Run it once to produce the data files. The script stays in the repo for regeneration.

## Verification (must do before claiming done)

1. `python3 scripts/generate_spec_data.py` exits 0
2. `data/spec/tree.json` valid JSON, N parts == number of `## ` headings
3. `data/spec/sections/` has N files, each with frontmatter
4. Backend: `curl http://127.0.0.1:8765/api/acts | grep spec` shows the act
5. Backend: `curl http://127.0.0.1:8765/api/tree/spec` returns the tree
6. Backend: `curl http://127.0.0.1:8765/api/section/spec/0` returns frontmatter + body
7. Frontend: build passes (`cd frontend && npm run build`)
8. Optionally restart service and verify in browser

## Constraints

- Do NOT modify DISPLAY_SPEC.md content
- Do NOT create new React components or backend routes
- Do NOT touch other acts' data
- Follow existing file naming conventions in data/ (lowercase-hyphen slugs)
