#!/usr/bin/env python3
"""CDN-0171: rebuild mangled markdown tables in ITAA 1997 section files.

Uses PyMuPDF word positions to reconstruct table cells column-by-column,
eliminating the interleaving artifacts of pdftotext -layout.

Method:
  1. Locate the section's pages (find "Section X" body headers, fall back to
     running headers).
  2. On each page, find table header lines ("Item ...").
  3. Derive column boundaries from the header words' x positions.
  4. Assign every word to a column by x, group into rows by item number.
"""

import argparse
import re
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


HEADER_WORD_RE = re.compile(r"^(Item|Items)$")  # capitalised; lower-case
# 'item 6 of the table' in a body cell must NOT split a block


def words_for_page(page) -> list[dict]:
    """All words on a page sorted by (baseline y1, x0).

    Different fonts (asterisked terms) have different ascents, so y0 differs
    for the same visual line; baselines (y1) align across fonts.
    """
    out = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, t = w[0], w[1], w[2], w[3], w[4]
        out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "t": t})
    out.sort(key=lambda w: (round(w["y1"], 2), w["x0"]))
    return out


def find_section_pages(doc, section: str) -> list[int]:
    """Pages containing a body header 'Section X', a running header, or the
    section's own heading line (e.g. '40-190 Second element of cost').
    TOC entries (leader dots + page numbers) are excluded.
    """
    pages = []
    pat_body = re.compile(rf"^Section\s+{re.escape(section)}\s*$", re.MULTILINE)
    pat_run = re.compile(rf"Section\s+{re.escape(section)}\s*$", re.MULTILINE)
    pat_own = re.compile(rf"^\s*{re.escape(section)}\s+\S", re.MULTILINE)
    for pno in range(doc.page_count):
        page = doc[pno]
        txt = page.get_text("text")
        # skip pages whose only mention is a TOC entry (leader dots)
        if pat_body.search(txt) or pat_run.search(txt):
            pages.append(pno)
            continue
        for ln in txt.splitlines():
            if ".." in ln:
                continue  # TOC leader line
            if re.match(rf"^\s*{re.escape(section)}\s+\S", ln):
                pages.append(pno)
                break
    # A table may start on the page BEFORE the first section marker (the
    # section body continues from the previous page) and may flow onto the
    # page after the last marker. Include both neighbours.
    if pages:
        first = pages[0]
        if first - 1 >= 0 and first - 1 not in pages:
            pages.insert(0, first - 1)
        last = pages[-1]
        nxt = last + 1
        if nxt < doc.page_count and nxt not in pages:
            pages.append(nxt)
    return pages


def table_blocks(page) -> list[list[dict]]:
    """Split the page's words into table blocks: consecutive lines sharing
    a common 'Item' header. Returns list of blocks; each block is a list of
    word dicts (header words + body words)."""
    words = words_for_page(page)
    # Build lines: group words by rounded baseline y1 (aligns across fonts)
    lines: dict[float, list[dict]] = {}
    for w in words:
        key = round(w["y1"], 2)
        lines.setdefault(key, []).append(w)
    ordered = sorted(lines.items())
    blocks = []
    cur = None
    for y, ws in ordered:
        # header line: first word is capitalised 'Item' IN THE ITEM COLUMN
        # (lower-case 'item N of the table...' refs inside body cells must
        # not split a block)
        is_header = bool(ws) and HEADER_WORD_RE.match(ws[0]["t"])
        if is_header:
            if cur is not None and len(cur) > 1:
                blocks.append(cur)
            cur = []
        if cur is not None:
            cur.extend(ws)
    if cur is not None and len(cur) > 1:
        blocks.append(cur)
    return blocks


def col_boundaries(block: list[dict]) -> list[float]:
    """Column x boundaries.

    Prefer the header line's word clusters (accurate for standard tables);
    fall back to line-start clustering when the header line has fewer than
    3 words (covers wrapped two-line headers like 118-300's).
    """
    ys = sorted({round(w["y1"], 2) for w in block})
    header_y = ys[0]
    hdr = [w for w in block if round(w["y1"], 2) == header_y]
    hdr.sort(key=lambda w: w["x0"])
    if len(hdr) >= 3 and hdr[0]["t"] == "Item":
        # cluster header words by gap > 8
        clusters = []
        cur = [hdr[0]]
        for w in hdr[1:]:
            gap = w["x0"] - cur[-1]["x1"]
            if gap > 8:
                clusters.append(cur)
                cur = [w]
            else:
                cur.append(w)
        clusters.append(cur)
        if len(clusters) >= 2:
            return [c[0]["x0"] for c in clusters[1:]]
    return _col_boundaries_line_start(block)


def _col_boundaries_line_start(block: list[dict]) -> list[float]:
    """Fallback: cluster line-start x0s (leftmost word per baseline) across
    the whole block. Handles wrapped two-line headers."""
    line_starts = {}
    for w in block:
        key = round(w["y1"], 2)
        if key not in line_starts or w["x0"] < line_starts[key]:
            line_starts[key] = w["x0"]
    xs = sorted(set(round(v, 1) for v in line_starts.values()))
    if not xs:
        return []
    clusters = []
    cur = [xs[0]]
    for x in xs[1:]:
        if x - cur[-1] > 20:
            clusters.append(cur)
            cur = [x]
        else:
            cur.append(x)
    clusters.append(cur)
    return [c[0] for c in clusters[1:]]


FOOTER_Y_MIN = 600  # footer boilerplate starts ~y600 on the 842pt pages


def is_footer_word(w: dict) -> bool:
    """Footer boilerplate (the 'To find definitions...' line, the Compilation
    header line, and the page number) sits in the bottom band of every page
    (y1 >= ~600). Table cells never extend there."""
    return w["y1"] >= FOOTER_Y_MIN


def build_rows(block: list[dict], boundaries: list[float]) -> list[dict]:
    """Assign words to columns, group into rows by item-number y positions.

    The PDF's columns have different y-offsets for the same visual line
    (font metrics), so line-grouping by y is unreliable. Instead:
      1. Assign every word to a column by x.
      2. The item column has one word per row (the item number). Sort those
         by y; each marks the start of a row.
      3. Every non-item word belongs to the row whose item-y it follows
         (up to the next item-y).
      4. Words in the footer band (y1 >= FOOTER_Y_MIN) are dropped.
    """
    # assign columns
    for w in block:
        col = 0
        for i, bx in enumerate(boundaries):
            if w["x0"] >= bx:
                col = i + 1
        w["col"] = col

    # separate header line (the line containing 'Item' as first word)
    ys = sorted({round(w["y1"], 2) for w in block})
    header_y = None
    for y in ys:
        ws = [w for w in block if round(w["y1"], 2) == y]
        if ws and ws[0]["t"] == "Item":
            header_y = y
            break
    if header_y is None:
        return []

    # Item candidates must be above the footer band (page numbers live in
    # the footer band and land in the item column).
    items = []
    for w in block:
        if (w["col"] == 0 and re.match(r"^\d+([A-Za-z]|\.\d+)*$", w["t"])
                and round(w["y1"], 2) > header_y and w["y1"] < FOOTER_Y_MIN):
            items.append(w)
    items.sort(key=lambda w: w["y1"])
    if not items:
        return []

    rows = []
    for idx, it in enumerate(items):
        y_lo = it["y1"]
        if idx + 1 < len(items):
            y_hi = items[idx + 1]["y1"]
        else:
            # Cap the last row: table rows are at most ~55pt tall (4-5 text
            # lines). Without a cap, the block's tail (notes, next section)
            # gets swept into the last row.
            y_hi = min(
                max(w["y1"] for w in block if not is_footer_word(w)) + 1,
                it["y1"] + 55,
            )
        row = {"item": it["t"], "cols": {i + 1: [] for i in range(len(boundaries))}}
        for w in block:
            if w["col"] > 0 and not is_footer_word(w) and y_lo <= w["y1"] < y_hi:
                row["cols"][w["col"]].append(w["t"])
        rows.append(row)
    return rows


def header_text(block: list[dict], boundaries: list[float]) -> list[str]:
    """Real column labels from the table header line(s).

    Primary: the 'Item' line itself. If a column has no words on that line
    (wrapped header, e.g. 118-300's two-line header), add the next line.
    """
    item_line_y = None
    for w in block:
        if w["t"] == "Item" and w["col"] == 0:
            item_line_y = round(w["y1"], 2)
            break
    if item_line_y is None:
        return []

    def labels_for(hdr_words: list[dict]) -> list[str]:
        hdr_words.sort(key=lambda w: w["x0"])
        labels = []
        for i, bx in enumerate(boundaries):
            if i + 1 < len(boundaries):
                nxt = boundaries[i + 1]
                words = [w["t"] for w in hdr_words if bx <= w["x0"] < nxt]
            else:
                words = [w["t"] for w in hdr_words if w["x0"] >= bx]
            labels.append(" ".join(words))
        return labels

    ys = sorted({round(w["y1"], 2) for w in block})
    idx = ys.index(item_line_y)
    hdr = [w for w in block if round(w["y1"], 2) == item_line_y]
    labels = labels_for(list(hdr))
    # if any column is empty, add the next line (wrapped header)
    if any(not lab.strip() for lab in labels) and idx + 1 < len(ys) and ys[idx + 1] - item_line_y < 16:
        nxt_y = ys[idx + 1]
        hdr2 = [w for w in block if round(w["y1"], 2) == nxt_y]
        labels = labels_for(list(hdr) + hdr2)
    return labels


def render_rows(rows: list[dict], boundaries: list[float], header: list[str] | None = None) -> str:
    """Render rows as a markdown table with real column headers."""
    ncols = len(boundaries) + 1
    if header and len(header) == len(boundaries):
        header_cells = ["Item"] + header
    else:
        header_cells = ["Item"] + [f"Column {i + 1}" for i in range(len(boundaries))]
    out = ["| " + " | ".join(header_cells) + " |", "| " + " | ".join(["---"] * ncols) + " |"]
    for r in rows:
        cells = [r["item"]]
        for i in range(len(boundaries)):
            cells.append(" ".join(r["cols"].get(i + 1, [])))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def collect_tables(doc, section: str) -> list[dict]:
    """All table blocks for a section as dicts: {header, rows} where rows is
    [{item, cols: {col: text}}]. Blocks that are continuations of the same
    logical table (same header, adjacent pages) are merged into one table.
    """
    pages = find_section_pages(doc, section)
    out = []
    for pno in pages:
        page = doc[pno]
        for block in table_blocks(page):
            bd = col_boundaries(block)
            if len(bd) < 2:
                continue
            rows = build_rows(block, bd)
            if not rows:
                continue
            hdr = header_text(block, bd)
            out.append({
                "page": pno + 1,
                "cols": len(bd) + 1,
                "header": hdr,
                "rows": [{"item": r["item"], "cols": {k: " ".join(v) for k, v in r["cols"].items()}} for r in rows],
            })

    # Merge blocks with the same header text (multi-page tables).
    merged: list[dict] = []
    for t in out:
        if merged and merged[-1]["header"] == t["header"]:
            # continuation: append rows (keep item numbering order)
            merged[-1]["rows"].extend(t["rows"])
            merged[-1]["page"] = f"{merged[-1]['page']}-{t['page']}"
        else:
            merged.append(dict(t))
    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("section")
    ap.add_argument("--json", action="store_true", help="emit JSON for the repair driver")
    args = ap.parse_args()

    if fitz is None:
        print("PyMuPDF not available", file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    tables = collect_tables(doc, args.section)
    if not tables:
        print(f"section {args.section}: no tables found", file=sys.stderr)
        return 1

    if args.json:
        import json
        print(json.dumps(tables, ensure_ascii=False))
        return 0

    print(f"section {args.section}: {len(tables)} tables")
    for t in tables:
        print(f"\n=== page {t['page']} cols={t['cols']} rows={len(t['rows'])} ===")
        print(render_rows(
            [{"item": r["item"], "cols": {int(k): v for k, v in r["cols"].items()}} for r in t["rows"]],
            [0] * (t["cols"] - 1),
            t["header"],
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
