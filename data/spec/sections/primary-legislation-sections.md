---
act: spec
section: "1"
title: "Primary Legislation Sections"
part: "1"
division: ""
---
**Acts:** itaa-1997, itaa-1936, taa-1953, gst-1999, corporations-act-2001, aml-ctf-2006, aml-ctf-rules-2007, nz-it-2007

### Sidebar tree
- Hierarchy: Part → Division → Subdivision → Section
- Normal legislation ordering: **id first** → `— {title}`
- Part nodes: uppercase label `Part {id} — {title}` (signpost style)
- Active section: `rgba(39,158,136,0.12)` background highlight

### Content area
1. **Breadcrumb:** `{act} › Part {part} › Division {division}` + Pin/Unpin button (accent when pinned)
2. **Body:** markdown per global conventions
3. **Comments** — collapsible `▲/▼`, count in heading, add form (author + textarea + Post), comment cards with author/date/text/Resolve
4. **SmartLinkPanel "Related"** — 5 collapsible groups, all default-closed, max 10 items each:
   - Sections (Same Act / Cross-Act, `s{id} — {title}`)
   - Rulings (`{title || citation}`)
   - Defined Terms (`{term} — defined in {section}`)
   - Cases (grouped by court: HCA → FCAFC → FCA → AATA → ARTA → others, `**{citation}** — {title}`)
   - Commentary (`{heading_title}`, `{publication} ¶{paragraph_number} — {chapter_title}`)

### Section 995-1 / 6(1) / 195-1 (dictionary sections)
- Currently: full 310KB markdown body rendered inline (ITAA 1997 s 995-1)
- **Target (per bug #4):** expandable definition tree — term list, per-term fetch, no inline 310KB dump

---
