---
act: spec
section: "0"
title: "Global conventions (apply to all types)"
part: "0"
division: ""
---

### Typography
- Headings: Montserrat, `COLORS.heading`
- Body text: Lora, 15px, line-height 1.7, `COLORS.text`
- Metadata/labels: Montserrat 12px, uppercase, letter-spacing 0.3, `COLORS.textMuted`
- All colours via `COLORS` tokens (theme-driven; no hardcoded hex in components)

### Breadcrumb (all types)
`{Type label} › {identifier}` — 12px uppercase muted, margin-bottom 20.

### Markdown rendering (all markdown-bodied types)
- `remark-gfm` + `rehype-raw` (tables, strikethrough, raw HTML)
- h1: mobile 20 / desktop 22, bottom border
- h2: mobile 17 / desktop 18; h3: mobile 15 / desktop 16
- `p` margin-bottom 12; `blockquote` 3px left border, muted
- `ul/ol` margin-left 20, `li` margin-bottom 4
- `table`: full-width, bordered, `thead` surfaceHover background
- Internal links intercepted: `/itaa-1997/sX#Y` → `onNavigate`, `/rulings/X` → `onNavigateRuling`
- Defined-term links: dashed underline → DefinitionPopover

### Mobile (<768px)
- h1 20px (vs 22), body 15px
- Tree: min-height 40px (vs 28px), reduced indent, word-wrap on
- Content padding `16px 12px 24px`
- Sidebar bottom buttons stack vertically

---
