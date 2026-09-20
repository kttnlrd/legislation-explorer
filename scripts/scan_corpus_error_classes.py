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
import unicodedata
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
EXTRACT_GLYPH = re.compile(r"[ç÷´êëûüàáâãäåæôöòóõøèéíìîïñšžÿý]")

# A flagged char is NOT corruption when it is a normal diacritic inside an
# alphabetic word in natural-language text (e.g. "Fédération Internationale").
# Formula-font junk always shows up as a lone symbol, or as a prefix glued to
# the following word ("êTotal", "ç1", "´ fringe benefits") — never with letters
# on BOTH sides whose accent-folded form is a real word.
_ASCII_FOLD = lambda w: "".join(
    c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c)
)


def _is_natural_word_accent(line: str, m: re.Match) -> bool:
    i = m.start()
    if i == 0 or not line[i - 1].isalpha() or i + 1 >= len(line) or not line[i + 1].isalpha():
        return False
    s = i
    while s > 0 and (line[s - 1].isalpha() or line[s - 1] in "'’"):
        s -= 1
    e = i + 1
    while e < len(line) and line[e].isalpha():
        e += 1
    word = line[s:e]
    if len(word) < 4:
        return False
    if _WORDS is None:
        return False
    return _ASCII_FOLD(word).lower() in _WORDS

# CDN-0193 Phase 1: the connector must TRAIL other text in the same cell.
# A cell whose entire content is one of these words is a complete value
# (gst-1999 s3-5 item 14 is the defined term "you"), not a truncation.
DANGLE_CELL_END = re.compile(r"[^|\s]\s+(the|and|a|an|or|of|to|for|in|on|was|is|you|if|that|which|with|by|as|at|when)\s*\|\s*$", re.I)

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


def _continuation_after(lines: list[str], ln_no: int, max_look: int = 4) -> tuple[str, str]:
    """Classify what follows a row that ends on a connector: 'wrap', 'header', or 'none'.

    A wrapped row ends on a connector by nature ("... to the" / "extent that ...") and the next row
    holds the rest. A column heading in a comparative table is also a split phrase - it is completed
    by the DATA rows below the '| --- |' rule, not by the line immediately after it, so the separator
    has to be looked through:

        | Item | Topic | These supplies are GST-free (except to the extent that |
        | --- | --- | --- |          <- the phrase continues in the cells below the rule

    What remains - a connector with no row, no heading rule, and no prose carrying it on - is the
    defect DANGLE_CELL_END was written for. Returns (kind, why), and the kind decides the class.
    """
    saw_separator = False
    for off in range(1, max_look + 1):
        j = ln_no - 1 + off
        if j >= len(lines):
            return "none", "end of file"
        nxt = lines[j]
        if not nxt.strip():
            continue
        if re.match(r"^\|\s*---", nxt.strip()):
            saw_separator = True
            continue
        if not nxt.startswith("|"):
            return "none", f"next non-empty line is not a table row ({nxt.strip()[:28]!r})"
        first = nxt.strip().strip("|").split("|")[0].strip()
        if saw_separator:
            return "header", "a heading rule follows, so the phrase continues in the rows below it"
        if not first:
            return "wrap", "next row opens with an empty first cell"
        if first[:1].islower():
            return "wrap", f"next row continues in lower case ({first[:24]!r})"
        return "none", f"next row starts a new item ({first[:24]!r})"
    return "none", "no following row"


def table_coherence_findings(lines: list[str], relpath: str) -> list[dict]:
    """The C11 detectors for ONE file. scan_table_coherence() walks the corpus
    and calls this; other tools (corpus_change_guard) reuse it per-file."""
    out: list[dict] = []

    def add(cls, _path, detail):
        out.append({"class": cls, "path": relpath, "detail": detail})

    for ln_no, ln in enumerate(lines, 1):
        if not ln.startswith("|") or re.match(r"^\|\s*---", ln):
            continue
        # (b) glyph junk (ignore natural-language accents, e.g. "Fédération")
        gm = next((m for m in EXTRACT_GLYPH.finditer(ln)
                   if not _is_natural_word_accent(ln, m)), None)
        if gm:
            add("C11_table_glyph", relpath,
                f"line {ln_no}: extraction glyph {gm.group(0)!r}: {ln.strip()[:90]}")
            continue
        # (c) dangling connector end - a defect ONLY when nothing continues the sentence.
        # A row that wraps ends on a connector by nature, so the old rule counted the wrap as damage
        # and named the class 'truncated'. Every one of the 138 findings was that shape, in corpora
        # the re-ingest never touched (the audit's own examples were gst-1999), which is how a class
        # can be 138 findings strong and still never have found the thing it was named for.
        if DANGLE_CELL_END.search(ln):
            kind, why = _continuation_after(lines, ln_no)
            if kind == "wrap":
                add("C11_table_rowwrap", relpath,
                    f"line {ln_no}: row ends on bare connector, continued by the next row "
                    f"({why}): {ln.strip()[:80]}")
            elif kind == "header":
                add("C11_table_header_split", relpath,
                    f"line {ln_no}: split column heading ({why}): {ln.strip()[:80]}")
            else:
                add("C11_table_truncated", relpath,
                    f"line {ln_no}: row ends on bare connector and nothing continues it "
                    f"({why}): {ln.strip()[:80]}")
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
            # A boundary is only legitimate when BOTH sides are whole
            # words ('asset | when'). If either half is a fragment, the
            # word was cut across cells ('d | efinitions' too — a
            # single-letter half is still a fragment, not a cell).
            if joined in _WORDS and not (tw in _WORDS and hw in _WORDS):
                add("C11_table_midword", relpath,
                    f"line {ln_no}: '{tw}|{hw}' = '{joined}' cut across cells {ci+1}|{ci+2}: {ln.strip()[:100]}")
                break
    return out


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
            findings.extend(table_coherence_findings(lines, str(p.relative_to(DATA))))


# ── C6 (CDN-0081): stray trailing token at cut point (e.g. "payments") ──────
# A cut remnant duplicates the END of a heading: the title was severed at the cut point and the
# trailing token was stranded on the next line as its own two-word-at-most heading. It does NOT
# duplicate the START of the heading.
#
# Every finding this class produced (15, all in nz-master-tax-guide) was one legitimate shape: H1 is
# the heading as printed carrying its paragraph number ("Fishing gear and quotas ¶27-371") and H2 is
# the short topic heading the guide prints beneath it ("Fishing gear"). The H2 repeats the START of
# H1 - the topic - which is the act's own convention, so the check was reporting the guide's layout
# as damage while never seeing the shape it was written for.
#
# Fixed on 2026-09-19: a finding requires the repeated token to be the TRAILING token of H1. Acts
# whose headings carry paragraph references are reported by name and skipped, so the correction
# cannot silently become a check that cannot fire - the pinned self-test in
# scripts/test_c6_cut_token.py fails if the CDN-0081 shape stops being caught.
PARA_REF = re.compile(r"\s*¶\s*\d{1,3}-\d{1,4}\s*$")
_WORD_EDGE = "*_.,;:()[]'\""


def cut_token_shape(h1: str, h2: str) -> str:
    """Classify an H1/H2 pair: 'cut' (CDN-0081), 'convention' (legitimate), or 'none'.

    Split out from the scanner so the pinned self-test exercises the same code path the corpus
    scan uses, rather than a copy of it that can drift.
    """
    core = PARA_REF.sub("", h1)
    t1 = [w.lower().strip(_WORD_EDGE) for w in core.split() if w.strip()]
    t2 = [w.lower().strip(_WORD_EDGE) for w in h2.split() if w.strip()]
    if not t1 or not t2 or len(t2) > 2:
        return "none"
    shares = any(
        len(w1) >= 3 and len(w2) >= 3 and (w1.startswith(w2[:5]) or w2.startswith(w1[:5]))
        for w1 in t1 for w2 in t2
    )
    # The paragraph reference is what distinguishes the two conventions, not where the shared word
    # sits. A guide heading carries "¶NN-NNN" and is followed by a short topic heading restating
    # part of it - at the front ("Fishing gear and quotas" / "Fishing gear"), at the back
    # ("Introduction to tax credits" / "Credits"), or as a shared stem ("Tax rates for trusts" /
    # "Trustee income"). A cut remnant of the same shape is indistinguishable from it, so an act
    # using this convention is skipped by name rather than guessed either way.
    if PARA_REF.search(h1):
        return "convention" if shares else "none"
    trailing = len(t1[-1]) >= 3 and t1[-1].startswith(t2[0][:5]) and t2[0][:5] in t1[-1]
    leading = len(t1[0]) >= 3 and t1[0].startswith(t2[0][:5]) and t2[0][:5] in t1[0]
    if trailing and not leading:
        return "cut"                      # heading severed, trailing token stranded
    if leading and trailing and len(t1) == 1:
        return "cut"                      # the same single token repeated
    return "none"


def scan_stray_cut_tokens():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        convention = 0
        for p in sorted(sec_dir.rglob("*.md")):
            text = p.read_text(errors="replace")
            # H1 then immediately a short H2 - the shape a cut point leaves behind
            m = re.search(r"^# (.+)\n\n## (.+)$", text, re.M)
            if not m:
                continue
            h1, h2 = m.group(1).strip(), m.group(2).strip()
            shape = cut_token_shape(h1, h2)
            if shape == "cut":
                add("C6_cut_token", str(p.relative_to(DATA)),
                    f"H1={h1!r} H2={h2!r} trailing token repeated - cut remnant")
            elif shape == "convention":
                convention += 1
        if convention:
            add("C6_cut_token:CONVENTION", f"data/{act_dir.name}/sections",
                f"{convention} H1+H2 pairs are the act's own heading/topic-heading convention "
                f"(H1 carries a ¶ reference, H2 repeats its opening words) - skipped, not a pass")


# ── C13 (CDN-0193 follow-up): duplicate anchors introduced by a re-ingest ──
# The gate verifies tokens, not markup, so a re-ingest can emit the same <a id="..."> hook twice for
# one printed subparagraph and pass every check. Duplicate anchors break deep links: a fragment URL
# resolves to the first match, so the second copy is unreachable. Found on 2026-09-19 by the
# structural integrity gate AFTER a 4,629-section apply that every per-block check had passed -
# byte-equality against the gate-verified output and the corruption counts are both blind to it.
def scan_duplicate_anchors():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            ids = re.findall(r'<a id="([^"]+)"', p.read_text(errors="replace"))
            dupes = sorted(k for k, v in Counter(ids).items() if v > 1)
            if dupes:
                add("C13_duplicate_anchor", str(p.relative_to(DATA)),
                    f"{len(dupes)} duplicated anchor id(s): {','.join(dupes[:6])}")


# ── C14 (CDN-0193): formula structure lost - every term present, nothing relating them ──
# Drawn operators (x, -, +, division) are set in subsetted Symbol fonts whose ToUnicode maps them to
# a plain space, so a re-ingested formula keeps the terms and loses the structure between them:
#
#     ```ingest-formula source=vol08.pdf page=160
#     Owned deductions + Acquired deductions        *Corporate tax rate     <- the x is gone
#     ```
#
# A fence whose lines carry a fraction rule is NOT a finding: the rule IS the structure (numerator
# over denominator) and it survives extraction. What is reported is a fence with no operator and no
# rule anywhere - the formula a reader cannot reconstruct. The fence marker names its own source page,
# so every finding is locatable, unlike the gate-derived operator worklist.
#
# Measured 2026-09-19: 963 suspect lines across 173 ITAA sections and 201 distinct source pages. This
# is the real size of the drawn-operator problem; the 67 positions in /tmp/operator-worklist.json were
# a small gate-derived subset whose characters the gate had wrong.
FORMULA_FENCE = re.compile(r"```ingest-formula source=(\S+) page=(\d+)")
_FORMULA_OPS = "+\u2212\u00d7\u00f7="
_FRACTION_RULE = re.compile(r"_{4,}")


def scan_lost_formula_structure():
    for act_dir in DATA.iterdir():
        sec_dir = act_dir / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            lines = p.read_text(errors="replace").splitlines()
            i = 0
            while i < len(lines):
                m = FORMULA_FENCE.match(lines[i])
                if not m:
                    i += 1
                    continue
                body, j = [], i + 1
                while j < len(lines) and not lines[j].startswith("```"):
                    body.append(lines[j])
                    j += 1
                text = " ".join(body)
                has_op = any(o in text for o in _FORMULA_OPS)
                has_rule = bool(_FRACTION_RULE.search(text))
                meaningful = [b for b in body if b.strip() and not b.strip().startswith("---")]
                if meaningful and not has_op and not has_rule:
                    add("C14_formula_structure", str(p.relative_to(DATA)),
                        f"line {i + 1}: {m.group(1)} p{m.group(2)} - {len(meaningful)} term line(s), "
                        f"no operator and no fraction rule: {meaningful[0].strip()[:70]}")
                elif meaningful and has_rule and not has_op:
                    add("C14_fraction_rule", str(p.relative_to(DATA)),
                        f"line {i + 1}: {m.group(1)} p{m.group(2)} - fraction rule present "
                        f"({len(meaningful)} line(s))")
                i = j


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


def scan_missing_heading(check_root: str | None = None):
    """C12 (from the nightly mutation test, 2026-09-18): a section can lose its H1 and no class trips.

    The nightly investigator planted four defects in a copy of 30-315.md. Three were caught exactly
    (glyph, mid-word split, truncated row); deleting the '# ' H1 line was NOT caught by any class in
    this set, nor by the integrity gate's tail checks. A clean audit therefore said nothing about
    every section's title surviving.

    The rule is derived from the corpus's own convention rather than asserted: an act whose section
    files overwhelmingly carry an H1 is an act where a file without one is a defect. Acts that do not
    follow the convention are reported by name and skipped, so the check cannot become a
    false-positive factory.
    """
    root = Path(check_root) if check_root else DATA
    acts = sorted(p for p in root.glob("*/sections") if p.is_dir())
    for act_sections in acts:
        files = sorted(act_sections.rglob("*.md"))
        if not files:
            continue
        with_h1 = 0
        missing = []
        for p in files:
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            # an H1 is a '# ' line, ignoring YAML frontmatter
            body = text.split("---", 2)[-1] if text.startswith("---") else text
            if re.search(r"^#\s+\S", body, re.M):
                with_h1 += 1
            else:
                missing.append(p)
        share = with_h1 / len(files)
        act = act_sections.parent.name
        if share < 0.8:
            add("C12_missing_heading:CONVENTION", f"data/{act}/sections",
                f"only {with_h1}/{len(files)} files ({share:.0%}) carry an H1 - convention not "
                f"established for this act, check skipped (not a pass)")
            continue
        for p in missing:
            try:
                shown = p.relative_to(DATA.parent)
            except ValueError:
                shown = p          # scanning a sandbox outside the repo (how this is tested)
            add("C12_missing_heading", str(shown),
                f"no '# ' heading in a file of an act where {with_h1}/{len(files)} "
                f"({share:.0%}) have one - title lost or never written")


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
    scan_missing_heading()
    scan_duplicate_anchors()
    scan_lost_formula_structure()

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
