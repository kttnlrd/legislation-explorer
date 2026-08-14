---
act: spec
section: "4"
title: "Tax Cases"
part: "4"
division: ""
---
**Scope:** 6,167 HTML files (HCA, FCA, FCAFC, AATA)

### Sidebar tree
- Court → Year → Case hierarchy (mapped through TreeNode: court=Part, year=Division, case=Section)
- Case ordering: title first → citation

### Content area
1. **Breadcrumb:** `Tax Case › {title || citation}`
2. **Header:** h1 `{title} — {citation}` (or citation only)
3. **Metadata rows** (dark `rgba(0,0,0,0.15)` rows, label:value, conditional per field) in order:
   Citation → Court → Decision Date → Judges → Outcome → Catchwords → Paragraphs → Content Length (`N.N KB`) → Cited By
4. **External links row:**
   - View on AustLII (accent-filled)
   - View on HCA (outlined) — when URL exists
   - View on FedCourt (outlined) — when URL exists
   - Download HTML (outlined)
5. **Case Summary** (from `/static/cleaned/summaries/{safe}.json`): Facts → Issues → Held → Reasoning → Outcome → Cases Cited (clickable) → Legislation Cited (clickable)
6. **Related Provisions** — parsed legislation links
7. **Section References** — `{act} s {section}` links
8. **Related Rulings** — clickable ul

---
