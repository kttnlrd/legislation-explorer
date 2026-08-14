---
act: spec
section: "8"
title: "Definitions Index"
part: "8"
division: ""
---

### API
- `data/definitions.json` maps term → section/anchor
- `/api/definitions/{act}` serves full index

### Frontend
- Inline popover (DefinitionPopover): dashed-underline term → click → term name (Montserrat 14 bold) + definition text (Lora 13, max-height 240px scroll) + "Go to definition →"
- Definition section links: bold+italic defined terms in non-dictionary sections link to the dictionary section
- **Target (bug #4):** s 995-1 / s 6(1) / s 195-1 render as expandable tree, not 310KB dump

---
