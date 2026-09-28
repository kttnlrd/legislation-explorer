# Table Reconstruction Log — CDN-0226

Root cause: the PDF table renderer (`_render_table` in `parse_gst1999.py` and siblings
`parse_fbt_sis.py`, `parse_itaa36.py`, `parse_taa53.py`) breaks its row loop on paragraph /
subparagraph markers (`RE_PARAGRAPH` / `RE_SUBPARAGRAPH`) and at page boundaries, so a table cell
holding `(a)/(b)/(c)` subclauses is cut at the first marker and the remainder is dropped or leaked
out as stray anchored paragraphs. Reconstructed surgically per file from the raw pdftotext source
(`data/<act>/raw/*.txt`), the source of truth. 40 files fixed; 3 candidates verified already-correct
and left untouched. Frontmatter, `# heading` and all non-table subsections preserved byte-identical.

Each of the 40 fixed sections now carries a `change_log` frontmatter field recording the date and a
one-line summary of what was changed (visible per-file and via the API).

## gst-1999 (9 fixed)
- **38-355** — table split into 6 fragments, items 1–7 truncated mid-clause and cells leaked out as
  stray `**(b)**/**(c)**` paragraphs. Rebuilt the full 8-item table (1,2,3,4,5,5A,6,7).
- **9-26** — table split into 3 fragments; rows 1–4 cut at first subclause marker. Rebuilt one 4-item
  table with all (a)/(b)/(c)/(i)/(ii) inline.
- **38-185** — 3 fragments; 7 items truncated + leaked anchored fragments. Rebuilt one 9-item table
  (1,2,2A,3,4,4A,5,6,7).
- **38-190** — 2 fragments; items 2–5 cut + leaked paragraphs. Rebuilt one 5-item table.
- **84-5** — 3 fragments; items 2–5 cut, item 5(c) glued onto (1A). Rebuilt one 5-item table, lifted
  item 5(c) back into its cell, restored (1A) as its own paragraph.
- **162-5** — 2 fragments; header cells truncated. Merged into one 4-row table.
- **162-70** — 2 fragments + page-footer row inside table. Merged into one 4-row table.
- **31-8** — header row truncated. Restored full header.
- **195-1** (dictionary) — 16 duplicate `| Item |` headers for 5 logical tables, interleaved with
  running headers/footer rows. Rebuilt 5 clean tables (Decreasing adjustments 13 rows, Increasing
  adjustments 19 rows, Food not GST-free 32 rows, Beverages GST-free 14 rows, Medical aids 158 rows).
- **11-99** — already correct, untouched.

## taa-1953 (21 fixed)
- **355-65** — worst case: 7 tables fragmented, 76 leaked anchored fragments. Rebuilt 7 clean tables
  (T1 15 rows … T7 19 rows), all subclauses inline. 553→181 lines.
- **355-50** — single table split into 4 fragments. Rebuilt one 11-row table.
- **355-70** — 2 fragments, items 1–6 cut, item 6 list leaked. Rebuilt one 6-row table.
- **396-55** — 5 fragments, 17 leaked anchors. Rebuilt one 16-row table.
- **45-232** — 4 tables ((3)/(3A)/(3B)/(3C)) split + 16 leaked anchors. Rebuilt 4 clean tables.
- **45-610** — main table split + 7 leaked anchors; Example table had no body rows. Rebuilt both.
- **45-400** — table split, title glued to header. Rebuilt one 4-row table.
- **45-402** — (4) table split across page break. Merged into one 2-row table (3 tables total).
- **268-90** — (3) table in 3 stubs, 4 leaked anchors. Rebuilt one 7-row table.
- **269-30** — (2) table in 4 stubs, interleaved garbage rows. Rebuilt one 6-row 4-column table.
- **359-50** — table split into 2 fragments. Merged into one 4-row table.
- **362-50** — header cut mid-clause. Header completed (rows already faithful).
- **446-5** — (6) table in 3 fragments. Rebuilt one 10-row table.
- **128-15** — (2) table in 3 fragments, 8 leaked anchors. Rebuilt one 3-row table.
- **128-25** — (5) table in 3 fragments. Rebuilt one 5-row table.
- **16-75** — two tables' headers cut mid-clause. Headers completed.
- **112-50** — header + item 2 sliced into fake cells. Rebuilt one table.
- **111-50** — total loss: table rendered as empty 4-column header, no rows. Restored all 5 rows.
- **135-10** — header truncated, item 4 split off. Rebuilt one 4-column table.
- **284-160** — item 1 cells cut + 3 leaked anchors. Rebuilt one table.
- **389-5** — 3 fragments, 6 leaked anchors. Rebuilt one 3-row table.

## itaa-1936 (6 fixed)
- **94** — both nested formula tables destroyed, prose glued in. Rebuilt both tables + restored prose.
- **121AS** — 12-row table unpiped, 38 leaked anchors. Rebuilt one 12-item table.
- **121AT** — many fragments, 26 leaked anchors. Rebuilt one 13-item table.
- **170B** — (3) + (8) tables split, 13 leaked anchors. Rebuilt both tables.
- **171A** — table in 4 fragments, 9 leaked anchors. Rebuilt one 4-row table.
- **419** — (1) table split, 2 leaked anchors. Rebuilt one 3-row table.

## fbt-1986 (4 fixed)
- **58Q** — formula chopped into pseudo-table. Restored (1)(c) + formula + prose.
- **65J** — 6 fragments, ~50 leaked anchors, 2 formulas as pseudo-tables. Rebuilt 12-item table + formulas.
- **110** — table split, 2 leaked anchors. Rebuilt one 4-row table.
- **135W** — sentence truncated, formula chopped into pseudo-table. Restored sentence + formula + definitions.
- **167** — already correct (amendment history), untouched.

## sis-1993
- **381** — already correct, untouched.

## Follow-ups (out of scope, separate defects — not fixed here)
- Truncated `section_title`/`# heading` in **355-70** and **45-232** (remaining heading words on their
  own lines).
- Page-header noise fused into subsection *prose* in 268-90 (2B)(d), 269-30 (2), 128-15 (5), 128-25 (1),
  362-50 (2) — a separate cleanup class present in ~423 other TAA files.
- **195-1** 4AA Provision cell: source PDF itself lost "Subdivision 79-A or" at a page break (verified
  via `pdftotext -bbox`); kept faithful to raw rather than silently completed.
