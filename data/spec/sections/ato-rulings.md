---
act: spec
section: "3"
title: "ATO Rulings (incl. ATO IDs)"
part: "3"
division: ""
---
**Scope:** 11,930 files — TD/TR/PCG/PS LA rulings + AID_ files

### Sidebar tree
- Ruling-style ordering: **title first** → id (smaller, opaque)
- Citations resolve under `rulings` act

### Content area
1. **Breadcrumb:** `Ruling › {citation}`
2. **Header:** h1 `{fm.title || citation}` + descriptive title if different + **Download** button (accent, `/api/ruling/{citation}/download`)
3. **Metadata panel (AI Summary)** — bordered box, ONLY when `type !== 'ATO ID'` and any field exists. Order:
   - Status
   - Subject
   - Question
   - Decision
   - Background
   - Ruling
   - Notice (yellow `#fff8e1` box)
   - Legislation (ul)
   - Cases (ul)
   - ATO URL (`View on ATO website ↗`)
4. **TOC ("Contents")** — only when `##`/`###` headers exist; h2/h3 get slug anchor IDs; nested indent for h3
5. **Body:** markdown
6. **Referenced Sections** — `{shortActName} s{section} — {title}` links
7. **Related Cases** — deduplicated by citation, `{title || citation} ({year})`

### ATO ID conditional
- Metadata panel **hidden** for ATO IDs — full body renders instead

---
