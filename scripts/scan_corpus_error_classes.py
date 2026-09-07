#!/usr/bin/env python3
"""Corpus-wide scan against previously-identified error classes (bug register).

Each check maps to a CDN ticket class and scans the FULL corpus, not just the
reported instance. Emits machine-readable findings: class, act/path, detail.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path("/home/harrison/legislation-explorer/data")
findings: list[dict] = []


def add(cls: str, path: str, detail: str):
    findings.append({"class": cls, "path": path, "detail": detail})


# ── C1 (CDN-0053/0070): compilation_no type consistency ─────────────────────
def scan_compilation_no():
    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
        try:
            t = json.loads((DATA / act / "tree.json").read_text())
        except Exception as e:
            add("C1_compilation_no", f"data/{act}/tree.json", f"unreadable: {e}")
            continue
        cn = t.get("compilation_no")
        if isinstance(cn, str):
            add("C1_compilation_no", f"data/{act}/tree.json",
                f"compilation_no is str ({cn!r}), others are int")
        if not t.get("compilation_date"):
            add("C1_compilation_no", f"data/{act}/tree.json", "missing compilation_date")


# ── C2 (CDN-0069): empty parts/divisions/leaves in trees ────────────────────
def scan_empty_tree_nodes():
    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
        try:
            t = json.loads((DATA / act / "tree.json").read_text())
        except Exception:
            continue
        for pi, p in enumerate(t.get("parts", [])):
            if not p.get("sections") and not p.get("divisions"):
                add("C2_empty_node", f"data/{act}/tree.json", f"empty part: {p.get('id')}")
            for di, d in enumerate(p.get("divisions", [])):
                if not d.get("sections") and not d.get("subdivisions"):
                    add("C2_empty_node", f"data/{act}/tree.json",
                        f"empty division: {p.get('id')}/{d.get('id')}")
                for si, s in enumerate(d.get("subdivisions", [])):
                    if not s.get("sections"):
                        add("C2_empty_node", f"data/{act}/tree.json",
                            f"empty subdivision: {p.get('id')}/{d.get('id')}/{s.get('id')}")


# ── C3 (CDN-0054): title truncation heuristics ──────────────────────────────
# A truncated title typically: ends mid-word with a hyphen, or ends '…'/'..',
# or ends with a standalone trailing word that indicates a cut (and/the/of/to
# as the LAST word, e.g. 'Rules applying to particular gifts of'). Words that
# merely CONTAIN those letters as suffixes ('demand', 'land') are NOT cuts.
def scan_tree_titles():
    suspicious_end = re.compile(r"[\w]-\s*$|\.\.\s*$|…\s*$|\b(?:and|the|of|to)\s*$")
    for act in sorted(p.name for p in DATA.iterdir() if (p / "tree.json").exists()):
        try:
            t = json.loads((DATA / act / "tree.json").read_text())
        except Exception:
            continue
        stack = []
        for p in t.get("parts", []):
            stack.append(p)
            for d in p.get("divisions", []):
                stack.append(d)
                for s in d.get("subdivisions", []):
                    stack.append(s)
        for node in stack:
            title = node.get("title", "")
            if not title:
                continue
            if suspicious_end.search(title.strip()) and len(title.strip()) > 3:
                add("C3_title_truncation", f"data/{act}/tree.json",
                    f"node {node.get('id')}: title ends suspiciously: {title!r}")


# ── C4 (CDN-0006/0049): asterisk footnote lines in section bodies ───────────
ASTERISK_LINE = re.compile(r"^\s*\*{2,}\s*$|^\s*\*[^*].*footnote|^\s*\*+ *[A-Za-z]+\s*\*+", re.M)
def scan_body_fragments():
    """Body text split into one-line fragments (treaties & any markdown).
    Fragment lines: bare (N), (a), a quote char, or a lone dash/em-dash.
    A file with more than 5 such lines is corrupted display-level text."""
    frag_re = re.compile(r"^\((?:\d+|[a-z])\)$|^\"$|^[-—]$")
    for base in [DATA / "treaties", DATA]:
        if base == DATA:
            dirs = [d for d in DATA.iterdir() if (d / "sections").is_dir()]
        else:
            dirs = [base]
        for d in dirs:
            for p in sorted((d / "sections").rglob("*.md")) if base == DATA else sorted(d.rglob("*.md")):
                if p.name.startswith("."):
                    continue
                try:
                    body = open(p, encoding="utf-8").read().split("---", 2)[-1]
                except Exception:
                    continue
                frags = [ln.strip() for ln in body.splitlines() if frag_re.match(ln.strip())]
                kinds = set()
                for f in frags:
                    if f == '"':
                        kinds.add("quote")
                    elif re.match(r"^[-—]$", f):
                        kinds.add("dash")
                    else:
                        kinds.add("mark")
                # Mono-pattern fragments are legitimate table cells (grid tables
                # use bare dashes; ATO guides use bare table-category codes).
                # Real fragmentation mixes quote/dash/marker kinds per file.
                if len(frags) > 5 and len(kinds) >= 2:
                    findings.append({"class": "C5_body_fragments", "path": str(p),
                                     "detail": f"{len(frags)} fragment lines ({', '.join(sorted(kinds))}) e.g. {frags[0]!r} {frags[1]!r}"})


# ── C4 (CDN-0006/0049): asterisk footnote lines in section bodies ───────────
def scan_asterisk_noise():
    for p in sorted((DATA / "itaa-1997" / "sections").rglob("*.md")):
        text = p.read_text(errors="replace")
        for m in ASTERISK_LINE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            add("C4_asterisk_noise", str(p.relative_to(DATA)), f"line {line}: {m.group(0).strip()[:60]}")


# ── C5 (CDN-0045/0167): sentence fragments / mid-sentence cut at end of section ─
# Fragment signal: section body ends with a lowercase word right after content,
# or a lone short word on the final line (no period), i.e. truncated at cut point.
STRAY_TAIL = re.compile(r"^\s*[a-z]{2,10}\s*$")
def scan_section_fragments():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            text = p.read_text(errors="replace")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if not lines:
                continue
            last = lines[-1]
            # section bodies normally end with a period/heading/anchor
            if STRAY_TAIL.match(last) and not last.endswith((".", ":", ")", "#")):
                add("C5_fragment_tail", str(p.relative_to(DATA)), f"ends with lone word: {last!r}")
            # fragment markers inside: '… of the' / 'the the' / double-space orphan
            for m in re.finditer(r"\b(the the|of the of|and the and)\b", text, re.I):
                ln = text.count("\n", 0, m.start()) + 1
                add("C5_fragment_inline", str(p.relative_to(DATA)), f"line {ln}: {m.group(0)}")


# ── C11 (CDN-0186/0187): table cell coherence — mid-word splits, glyph junk ─
# Tables are the audit's blind spot: C5 skips anything inside '|' pipe rows,
# so words cut across cells, PDF formula glyphs, and truncated rows all pass.
# This class parses pipe-table cells:
#   (a) mid-word split: a cell ends with a short lowercase fragment (<=4 chars,
#       not itself a whole word preceded by a space) and the next cell starts
#       lowercase — e.g. '| ... ast | erisked terms ... |' (whole word cut)
#   (b) extraction glyphs: ç ÷ ´ ê ú æ û etc. inside any cell (formula junk)
#   (c) dangling end: a table row's final cell ends with a bare connector
#       ('the |', 'and |') — content truncated at the old page boundary
EXTRACT_GLYPH = re.compile(r"[ç÷´êëûüàáâãäåæôöòóõøèéíìîïñšžÿýñ]")
DANGLE_CELL_END = re.compile(r"\s(the|and|a|an|or|of|to|for|in|on|was|is|you|if|that|which|with|by|as|at|when)\s*\|\s*$", re.I)

# /usr/share/dict/words (lowercase, ~104k) for the mid-word split test:
# flag cell boundary only if NEITHER side is a word but their concatenation is
# ('ast | erisked' -> 'asterisked'). Whole words on either side ('asset | when')
# are legitimate cell boundaries and are skipped.
try:
    _WORDS = set(open("/usr/share/dict/words", encoding="utf-8").read().split())
except Exception:
    _WORDS = None


def _tail_word(cell: str):
    """Last whitespace-separated token of a cell, stripped of leading markers."""
    t = cell.strip().split()[-1] if cell.strip().split() else ""
    return t.strip(",*'\"()") if t else ""


def _head_word(cell: str):
    """First whitespace token of a cell, stripped of leading markers."""
    parts = cell.strip().split()
    if not parts:
        return ""
    t = parts[0]
    return t.strip(",*'\"()") if t else ""


def scan_table_coherence():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for ln_no, ln in enumerate(lines, 1):
                if not ln.startswith("|") or re.match(r"^\|\s*---", ln):
                    continue
                # (b) glyph junk
                gm = EXTRACT_GLYPH.search(ln)
                if gm:
                    add("C11_table_glyph", str(p.relative_to(DATA)),
                        f"line {ln_no}: extraction glyph {gm.group(0)!r}: {ln.strip()[:90]}")
                    continue
                # (c) dangling connector end
                if DANGLE_CELL_END.search(ln):
                    add("C11_table_truncated", str(p.relative_to(DATA)),
                        f"line {ln_no}: row ends on bare connector: {ln.strip()[:90]}")
                    continue
                # (a) mid-word split across adjacent cells — wordlist test
                if _WORDS is None:
                    continue
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                for ci in range(len(cells) - 1):
                    left, right = cells[ci], cells[ci + 1]
                    tw = _tail_word(left).lower()
                    hw = _head_word(right).lower()
                    if len(tw) < 1 or len(hw) < 1:
                        continue
                    joined = tw + hw
                    if joined in _WORDS and tw not in _WORDS and hw not in _WORDS:
                        add("C11_table_midword", str(p.relative_to(DATA)),
                            f"line {ln_no}: '{tw}|{hw}' = '{joined}' cut across cells {ci+1}|{ci+2}: {ln.strip()[:100]}")
                        break


# ── C6 (CDN-0081): stray trailing token at cut point (e.g. "payments") ──────
# In tree titles or section H1: title that is a single fragment word repeated.
def scan_stray_cut_tokens():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            text = p.read_text(errors="replace")
            # H1 then immediately a very short H2 identical-ish (cut artifact)
            m = re.search(r"^# (.+)\n\n## (.+)$", text, re.M)
            if m:
                h1, h2 = m.group(1).strip(), m.group(2).strip()
                if h2.lower().startswith(h1.lower().split()[0][:5]) and len(h2.split()) <= 2:
                    add("C6_cut_token", str(p.relative_to(DATA)),
                        f"H1={h1!r} H2={h2!r} looks like cut remnant")


# ── C7 (CDN-0124): chapeau dropped — section body missing opening paragraph ──
# If the first body paragraph after frontmatter starts with a subsection marker
# or is empty → chapeau likely dropped.
def scan_chapeau():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            text = p.read_text(errors="replace")
            m = re.search(r"^---\n.*?\n---\n(.*)$", text, re.S)
            if not m:
                continue
            body = m.group(1).strip()
            if not body:
                add("C7_chapeau", str(p.relative_to(DATA)), "empty body")
                continue
            first_par = body.split("\n\n", 1)[0].strip()
            if re.match(r"^\(\d+\)", first_par) and len(first_par) < 80:
                add("C7_chapeau", str(p.relative_to(DATA)),
                    f"body starts with subsection ({first_par[:60]!r}) — chapeau may be missing")


# ── C8 (CDN-0095/0096/0097): formatting artifacts in bodies ─────────────────
ARTIFACT_PATS = {
    "header_slash": re.compile(r"/header/|/footer/|/content/"),
    "md_link_junk": re.compile(r"\]\(\s*\)|!\[\]\(\)"),
    "double_heading": re.compile(r"^##\s*$", re.M),
    "stray_bullet": re.compile(r"^\s*[-*]\s*$", re.M),
}
def scan_formatting_artifacts():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            text = p.read_text(errors="replace")
            for name, pat in ARTIFACT_PATS.items():
                m = pat.search(text)
                if m:
                    ln = text.count("\n", 0, m.start()) + 1
                    add(f"C8_{name}", str(p.relative_to(DATA)), f"line {ln}: {m.group(0)[:40]!r}")
                    break


# ── C9 (CDN-0007/0048/0071): definitions index quality ──────────────────────
def scan_definitions():
    try:
        store = json.loads((DATA / "definitions_all.json").read_text())
    except Exception as e:
        add("C9_definitions", "data/definitions_all.json", f"unreadable: {e}")
        return
    for act, act_data in store.items():
        terms = act_data.get("terms", {})
        # term keys that look truncated (end with 'the'/'of'/hyphen)
        for term in terms:
            if re.search(r"\b(the|of|and|to)\s*$", term, re.I) and len(term) > 8:
                add("C9_definitions", "data/definitions_all.json",
                    f"{act}: term looks truncated: {term!r}")
        # terms without anchor (index entry that can't resolve)
        for term, info in terms.items():
            if not info.get("anchor") and not info.get("section"):
                add("C9_definitions", "data/definitions_all.json",
                    f"{act}: term {term!r} missing anchor+section")


# ── C10 (CDN-0051/0073/0120): case citations year-collision / name issues ───
def scan_case_citations():
    # NOTE: FCAFC case numbers restart every year, so "[2018] FCAFC 122" and
    # "[2024] FCAFC 122" are DIFFERENT cases — normalizing the year away and
    # counting repeats is a false-positive factory. Only flag:
    #   (a) the exact same citation appearing more than once (true duplicate),
    #   (b) the same court+number with NO year at all (year-less citation —
    #       the CDN-0120 class that year-blind enrichment produced).
    for f in ["fcafc_tax_cases.json", "case_section_refs.json"]:
        p = DATA / f
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else list(data.values())
        seen_exact = Counter()
        seen_courtnum = Counter()
        for it in items:
            if isinstance(it, dict):
                c = it.get("citation", "")
                if not c:
                    continue
                # (a) exact duplicates
                seen_exact[c] += 1
                # (b) year-less court+number (only when the citation has a
                # court prefix like 'FCAFC 122' but no [year])
                if re.match(r"^FCAFC\s+\d+", c):
                    seen_courtnum[c] += 1
        for cit, cnt in seen_exact.items():
            if cnt > 1:
                add("C10_citation_collision", f"data/{f}",
                    f"{cit!r} appears {cnt} times — exact duplicate")
        for cit, cnt in seen_courtnum.items():
            if cnt > 1:
                add("C10_citation_collision", f"data/{f}",
                    f"{cit!r} appears {cnt} times — year-less citation (CDN-0120 class)")


def main():
    scan_compilation_no()
    scan_empty_tree_nodes()
    scan_tree_titles()
    scan_asterisk_noise()
    scan_section_fragments()
    scan_stray_cut_tokens()
    scan_chapeau()
    scan_formatting_artifacts()
    scan_definitions()
    scan_case_citations()
    scan_table_coherence()

    # summarize
    by_class = Counter(f["class"] for f in findings)
    print(f"TOTAL FINDINGS: {len(findings)}")
    for cls, cnt in sorted(by_class.items()):
        print(f"  {cls}: {cnt}")
    print()
    # print first 3 per class for context
    seen = set()
    for f in findings:
        if f["class"] not in seen:
            print(f"--- {f['class']} ---")
            seen.add(f["class"])
        print(f"  {f['path']}: {f['detail'][:100]}")

    out = Path("/tmp/corpus_scan_20260826.json")
    out.write_text(json.dumps(findings, indent=2))
    print(f"\nfull JSON: {out}")


if __name__ == "__main__":
    main()
