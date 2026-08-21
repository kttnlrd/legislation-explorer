#!/usr/bin/env python3
"""
Comprehensive definitions scan — searches ALL section files in ALL acts for
any definition-like text pattern, not relying on the existing index.

Uses the production backend's text-matching logic to find:
  - "term means/includes/has the meaning given by"
  - "which ... is in this section called the term"
  - "In this section/Division/Part: term means ..."
  - Colon-style definitions: "term: definition text"

Output: data/definitions_comprehensive.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path.home() / "legislation-explorer"
DATA_DIR = BASE / "data"
OUT_PATH = DATA_DIR / "definitions_comprehensive.json"
REPORT_PATH = DATA_DIR / "definitions_scan_report.json"

ACTS = {
    "itaa-1997": "ITAA 1997",
    "itaa-1936": "ITAA 1936",
    "gst-1999": "GST Act 1999",
    "taa-1953": "TAA 1953",
    "fbt-1986": "FBTAA 1986",
    "sis-1993": "SIS Act 1993",
    "corporations-act-2001": "Corporations Act 2001",
    "aml-ctf-2006": "AML/CTF Act 2006",
    "nz-it-2007": "NZ IT Act 2007",
}

# ── Pattern 1: Standard "term means/includes/has meaning" ──────────────
STD_DEF_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9\s'/(),%-]{1,80}?)\s+"
    r"(has (?:the|a) meaning given by|has (?:the|a) meaning affected by|"
    r"has the same meaning as(?: in)?|means|includes)\b",
    re.IGNORECASE,
)

# ── Pattern 2: "which ... is in this section/Division/Part called the <term>" ──
CALLED_RE = re.compile(
    r"(?:which|that)\s"
    r"(?:\([^)]*\)\s)*"  # optional parenthetical like "(in this section)"
    r"(?:is|are|is to be)\s"
    r"(?:in\s+this\s+(?:section|Division|Part|Subdivision|Act)\s)?"
    r"called\s+"
    r"(?:the\s+)?"
    r"([A-Za-z0-9][A-Za-z0-9\s'(),/-]{1,60}?)"
    r"(?:[.])",
    re.IGNORECASE,
)

# ── Pattern 3: "In this section/Division/Part: term means ..." ─────────
IN_THIS_RE = re.compile(
    r"(?:In\s+this\s+(?:section|Division|Part|Subdivision|Act)\s*[:.]\s*)?"
    r"([A-Za-z0-9][A-Za-z0-9\s'(/,-]{1,80}?)\s+"
    r"(means|includes|has (?:the|a) meaning)",
    re.IGNORECASE,
)

# ── Pattern 4: "term: definition text" ────────────────────────────────
COLON_DEF_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9\s'{(\[(\/,)-]{1,60}?):\s",
    re.MULTILINE,
)

SECTION_HEADING_RE = re.compile(r"^#{1,4}\s", re.MULTILINE)

# ── Dictionary-section scanner (curated phase for acts with no pointers) ──
# These acts have a single Interpretation/Definitions section whose terms are
# listed alphabetically in run-on paragraphs (the itaa-1936 s 6 pattern).
DICTIONARY_SECTIONS = {
    "fbt-1986": ("136", "sections/part-xid/division-unknown/136.md"),
    "taa-1953": ("2", "sections/part-i/division-unknown/2.md"),
    "sis-1993": ("10", "sections/part-1/division-2/10.md"),
    "aml-ctf-2006": ("5", "sections/part-1/division-1/5.md"),
    "nz-it-2007": ("YA-1", "sections/part-Y/division-YA/YA-1.md"),
}

DEFS_ALL_PATH = DATA_DIR / "definitions_all.json"

# "term means / includes / has the meaning ...", with an optional
# ", in relation to X," qualifier and the NZ "term— (a) means" dash style.
DICT_VERB_RE = re.compile(
    r"(?:^|\.\s+|;\s+|:\s+|\n|\)\s+|\]\s+)\s*"
    r"([A-Za-z0-9][^.;:\n—()\[\]]{0,80}?(?:\([^)]{1,60}\))?[^.;:\n—()\[\]]{0,40}?)"
    r"(,\s(?:in relation to|in respect of|when used|in connection with|for|of|to)\s[^.;\n]{0,200}?,)?"
    r"\s*(?:—\s*)?(?:\((?:[a-z]|[ivx]+|\d+)\)\s*)?"
    r"(?:has\s+(?:the|a)\s+(?:same\s+)?meanings?\b|is defined in\b|means\b|includes\b)",
    re.MULTILINE,
)

# Colon-style: "term: definition text" (AML/CTF s 5 uses this heavily)
DICT_COLON_RE = re.compile(
    r"(?:^|\.\s+|\n)\s*([A-Za-z0-9][^.;:\n—]{1,60}?):\s",
    re.MULTILINE,
)


def _loose_alpha_key(term: str) -> str:
    return re.sub(r"[^a-z0-9]", "", term.lower())


def clean_dict_body(content: str) -> str:
    body = get_body(content)
    body = re.sub(r'<a id="[^"]*"></a>\s*', "", body)
    body = re.sub(r"^#+\s.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^>\s?", "", body, flags=re.MULTILINE)
    body = body.replace("‘", "'").replace("’", "'")
    body = body.replace("“", '"').replace("”", '"')
    return body.replace("*", "")


def scan_dictionary_section(act: str) -> list[str]:
    """Extract term names from an act's dictionary section, in file order."""
    section, rel_path = DICTIONARY_SECTIONS[act]
    md_path = DATA_DIR / act / rel_path
    body = clean_dict_body(md_path.read_text(encoding="utf-8", errors="replace"))

    candidates = []  # (position, term)
    verb_spans = []
    for m in DICT_VERB_RE.finditer(body):
        term = m.group(1).strip().rstrip(",")
        candidates.append((m.start(1), term))
        verb_spans.append((m.start(1), m.end()))
    for m in DICT_COLON_RE.finditer(body):
        # Skip colon matches inside a verb-style match ("term means:")
        if any(s <= m.start(1) < e for s, e in verb_spans):
            continue
        candidates.append((m.start(1), m.group(1).strip()))
    candidates.sort()

    # Terms appear alphabetically in dictionary sections, so the real terms
    # form the longest non-decreasing chain of sort keys through the file;
    # mid-definition false positives ("the recipient means...") fall off it.
    valid = [t for _, t in candidates if is_valid_def_term(t) and _loose_alpha_key(t)]
    keys = [_loose_alpha_key(t) for t in valid]
    n = len(keys)
    # ponytail: O(n^2) LIS, n is at most a few thousand in a one-off script
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if keys[j] <= keys[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    if not n:
        return []
    i = max(range(n), key=lambda k: best[k])
    chain = []
    while i != -1:
        chain.append(valid[i])
        i = prev[i]
    chain.reverse()

    kept, seen = [], set()
    for term in chain:
        key = _loose_alpha_key(term)
        if key not in seen:
            seen.add(key)
            kept.append(term)
    return kept


def run_dictionary_phase() -> int:
    import datetime
    import shutil

    data = json.loads(DEFS_ALL_PATH.read_text(encoding="utf-8"))
    backup = DEFS_ALL_PATH.with_name(
        f"definitions_all.json.bak-{datetime.date.today().isoformat()}")
    if not backup.exists():
        shutil.copy2(DEFS_ALL_PATH, backup)
        print(f"Backup: {backup}")

    for act, (section, rel_path) in DICTIONARY_SECTIONS.items():
        raw = (DATA_DIR / act / rel_path).read_text(encoding="utf-8", errors="replace")
        anchor_m = re.search(r'<a id="(s[^"]+)"', raw)
        anchor = anchor_m.group(1) if anchor_m else ""

        terms = scan_dictionary_section(act)
        existing = data.get(act, {}).get("terms", {})
        merged = {**existing}
        for term in terms:
            if term not in merged:
                merged[term] = {"anchor": anchor, "section": section}
        data[act] = {"section": section, "terms": merged}
        print(f"{act}: {len(existing)} -> {len(merged)} terms (s {section})")

    DEFS_ALL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {DEFS_ALL_PATH}")
    return 0


def get_body(content: str) -> str:
    if content.startswith("---"):
        m = re.search(r"\n---\s*\n", content)
        return content[m.end():] if m else content
    return content


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def is_valid_def_term(term: str) -> bool:
    t = normalize(term)
    if not t or len(t) < 2 or len(t) > 80:
        return False
    if t.startswith("(") or t.endswith("("):
        return False
    if re.match(r"^[\d\s]+$", t):  # numbers only
        return False
    # Subsection markers like "a)", "(b)", "ii)", "(ii)"
    if re.match(r"^\(?[a-z]\)?$", t) or re.match(r"^\(?[ivx]+\)?$", t):
        return False
    if re.match(r"^\d+\)", t):  # "2)", "3)"
        return False
    # False starts
    first_word = t.split()[0] if t.split() else ""
    if first_word in ("the", "a", "an", "this", "that", "these", "those", "if", "for", "to", "in", "of", "on", "or", "and", "but", "not", "by", "with", "from", "at", "as", "any", "all", "each", "every", "its", "his", "her", "their", "whether", "where", "when", "while", "after", "before", "during", "under", "over", "without", "no", "nor"):
        return False
    # Remove leading "In this section/Division" prefix that got captured
    if re.match(r"^(?:in this|for the purposes of this)", t):
        return False
    # Must contain at least one alphabetic character
    if not re.search(r"[a-z]", t):
        return False
    return True


def find_definition_end(body: str, start: int, term: str) -> int:
    """Find where this definition ends using multiple strategies."""
    after = body[start:]
    ends = []

    # Next definition anchor
    m = re.search(r'<a id="s\d', after)
    if m:
        ends.append(start + m.start())

    # Next section heading
    m = SECTION_HEADING_RE.search(after)
    if m:
        ends.append(start + m.start())

    # Next definition pattern (standard or called-style)
    m_std = STD_DEF_RE.search(after, 1)
    if m_std and m_std.start() > 10:  # avoid matching the same def again
        ends.append(start + m_std.start())

    m_called = CALLED_RE.search(after, 1)
    if m_called:
        ends.append(start + m_called.start())

    # Try to use the next sentence break after a reasonable length
    # Find the next ". \n" pattern that follows a definition-length segment
    long_enough = max(50, len(term) * 3)
    if len(after) > long_enough:
        # Find next double-newline or paragraph break
        m = re.search(r"\n\n(?=[A-Z\"(])", after[long_enough:])
        if m:
            ends.append(start + long_enough + m.start())

    return min(ends) if ends else len(body)


def scan_act(act: str, act_display: str) -> list[dict]:
    sections_dir = DATA_DIR / act / "sections"
    if not sections_dir.exists():
        return []

    results = []
    seen = set()

    for md_path in sorted(sections_dir.rglob("*.md")):
        section_id = md_path.stem
        content = md_path.read_text(encoding="utf-8", errors="replace")
        body = get_body(content)
        if not body.strip():
            continue

        # Normalize: remove asterisk markup (bold/italic markers)
        clean_body = body.replace("*", "")

        # 1. Standard definitions: "term means/includes"
        for m in STD_DEF_RE.finditer(clean_body):
            term = normalize(m.group(1))
            if not is_valid_def_term(term):
                continue
            sig = f"{term}|{act}"
            if sig in seen:
                continue

            # Check it doesn't start with a false start word
            first_word = term.split()[0] if term.split() else ""
            if first_word in ("the", "a", "an", "this", "that", "these", "those", "if", "for", "to", "in", "of", "on"):
                continue

            seen.add(sig)
            start = m.start()
            end = find_definition_end(clean_body, start, term)
            def_text = clean_body[start:end].strip()
            def_text = re.sub(r"\n{3,}", "\n\n", def_text)

            if len(def_text) >= 15:
                results.append({
                    "term": term,
                    "act": act, "act_display": act_display,
                    "section": section_id,
                    "definition": def_text,
                    "source": "std",
                })

        # 2. "which ... is called the <term>" pattern
        for m in CALLED_RE.finditer(clean_body):
            term = m.group(1).strip().lower()
            if not is_valid_def_term(term):
                continue
            sig = f"{term}|{act}"
            if sig in seen:
                continue
            seen.add(sig)

            start = m.start()
            end = find_definition_end(clean_body, start, term)
            def_text = clean_body[start:end].strip()
            def_text = re.sub(r"\n{3,}", "\n\n", def_text)

            if len(def_text) >= 15:
                results.append({
                    "term": term,
                    "act": act, "act_display": act_display,
                    "section": section_id,
                    "definition": def_text,
                    "source": "called",
                })

    return results


def main() -> int:
    all_defs = []
    for act, display in sorted(ACTS.items()):
        print(f"Scanning {act} ({display})...")
        defs = scan_act(act, display)
        all_defs.extend(defs)
        print(f"  -> {len(defs)} definitions found")

    # Dedup: first occurrence wins
    seen = set()
    unique = []
    for d in all_defs:
        sig = f"{d['term']}|{d['act']}"
        if sig not in seen:
            seen.add(sig)
            unique.append(d)

    print(f"\nTotal raw: {len(all_defs)}")
    print(f"Unique (term+act): {len(unique)}")

    # Per-act breakdown
    print("\nPer-act:")
    for act, display in sorted(ACTS.items()):
        n = sum(1 for d in unique if d['act'] == act)
        # Also show source breakdown
        std = sum(1 for d in unique if d['act'] == act and d['source'] == 'std')
        called = sum(1 for d in unique if d['act'] == act and d['source'] == 'called')
        print(f"  {display}: {n} ({std} std, {called} called)")

    # Write
    out = {"count": len(unique), "definitions": unique}
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nWritten: {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    if "--dictionaries" in sys.argv:
        sys.exit(run_dictionary_phase())
    sys.exit(main())