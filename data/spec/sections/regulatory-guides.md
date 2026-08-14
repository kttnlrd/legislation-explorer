---
act: spec
section: "5"
title: "Regulatory Guides (ASIC RGs)"
part: "5"
division: ""
---

### Content area
1. **Breadcrumb:** `ASIC Regulatory Guide › {citation}`
2. **Header:** h1 `{citation} — {title}` + status badge
   - Active: green (`#059669` / `#ecfdf5`)
   - Withdrawn/unavailable/no_pdf: amber (`#b45309` / `#fffbeb`)
3. **Metadata panel:** Status → Last updated → Download PDF button (if `hasPdf && downloadUrl`) → View on ASIC website + direct PDF link
4. **Body:** plain pre-wrap text (NO markdown), toggle "Show full text" / "Hide full text", only if non-empty
5. **Structured summary panel** (if `hasSummary`): Subject → Background → ASIC position → Cases referenced → Legislation referenced
   - If `!hasSummary`: dashed-border placeholder (withdrawn message or "Structured summary not yet...")

---
