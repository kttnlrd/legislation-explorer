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
