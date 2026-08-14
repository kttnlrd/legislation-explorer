---
act: spec
section: "2"
title: "Double Tax Agreements"
part: "2"
division: ""
---
**Scope:** 42 countries, each `data/treaties/{country}/`

### Sidebar tree
- Country → Article nodes
- Article node: `{title}`, slug path retained for routing
- Slug-like IDs hidden from display

### Content area
1. **Breadcrumb:** `{country} › Article {articleId}`
2. **Header:** h1 article title (only if present)
3. **Body:** markdown, frontmatter stripped (regex `/^---\n[\s\S]*?\n---\n?/`)
4. **No panels below body**

---
