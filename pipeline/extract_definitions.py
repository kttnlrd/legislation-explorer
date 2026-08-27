#!/usr/bin/env python3
"""
extract_definitions.py — canonical generator of the per-act definition catalogs
``data/{act}/definitions.json``.

These files are consumed by ``pipeline/extract_all_definitions.py`` (which merges
them into ``data/definitions_all.json``, the file the backend serves) and carry
the canonical *per-term* slug anchors (e.g. ``s995-1-4-build-to-rent-manner``)
used by ``backend/processors/markdown.py`` at serve time.

OUTPUT FORMAT (per act, flat dict keyed by the lowercased star-free term):

    {
      "<lowercase key>": {
        "term":    "<display term (original casing, '*' removed)>",
        "section": "<dictionary section id>",
        "anchor":  "s<section>-<slug>",
        "act":     "<act display name>"
      },
      ...
    }

SOURCES
-------
  itaa-1997  data/itaa-1997/sections/part-6-5/division-995/995-1.md  (regenerated
             in Phase 1; definitions start at line start). Subsection (1) block.
  itaa-1936  the ITAA-1936 s6 dictionary. The data/ file is manually curated, so
             the clean re-paragraphed render currently lives at
             /tmp/dictfix-new-itaa-1936/part-i/division-unknown/6.md — pass it
             with --source-itaa-1936. Subsection (1) block.
  gst-1999   the GST s195-1 Dictionary. The data/ file is manually curated, so the
             clean render currently lives at
             /tmp/dictfix-new-gst-1999/part-6-3/division-195/195-1.md — pass it
             with --source-gst-1999. The GST dictionary has no numbered subsection
             wrapper; extraction runs from the intro line to the first schedule
             heading (the uncurated "Schedule 1—Food" block must be excluded).

Once the curation is resolved for itaa-1936 / gst-1999, point --source-* at the
regenerated data/ files instead of the /tmp renders.

DEFENSIVE EXTRACTION: line-anchored matching is primary, but if a configured
source still contains run-on lines (legacy layout), overly long lines are also
split at mid-line definition boundaries — a ". " followed by text for which
``dictionary_utils.starts_new_definition`` returns True is treated as a new
definition start.

NOTE: this script NO LONGER writes the old data/definitions.json catalog. That
file fed only pipeline/link_definitions.py, which is being retired in Phase 4.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictionary_utils import starts_new_definition  # noqa: E402

BASE = Path.home() / "legislation-explorer"
DATA_DIR = BASE / "data"

# Per-act metadata: dictionary section id and display name.
ACTS = {
    "itaa-1997": {"section": "995-1", "display": "ITAA 1997"},
    "itaa-1936": {"section": "6", "display": "ITAA 1936"},
    "gst-1999": {"section": "195-1", "display": "GST Act 1999"},
}

DEFAULT_SOURCES = {
    "itaa-1997": DATA_DIR / "itaa-1997" / "sections" / "part-6-5" / "division-995" / "995-1.md",
    # itaa-1936 / gst-1999 default to the data/ files but currently need the
    # /tmp renders (curation detected) — pass them explicitly.
    "itaa-1936": DATA_DIR / "itaa-1936" / "sections" / "part-i" / "division-unknown" / "6.md",
    "gst-1999": DATA_DIR / "gst-1999" / "sections" / "part-6-3" / "division-195" / "195-1.md",
}

# ---------------------------------------------------------------------------
# Term capture patterns
# ---------------------------------------------------------------------------

# Predicate style: "<term> means/includes/has the meaning ...".
# Include Unicode curly quotes (U+2018/U+2019) commonly found in PDF-extracted text.
PREDICATE_RE = re.compile(
    r"^([A-Za-z0-9*][\w%*\u2018\u2019'() -]{0,80}?)\s+"
    r"(has (?:the|a) meaning given by|has (?:the|a) meaning affected by|"
    r"has the same meaning as(?: in)?|means|includes)\b"
)

# Colon style: "<term>: ...".
COLON_RE = re.compile(r"^([A-Za-z0-9*][\w%*\u2018\u2019'() -]{0,80}?):\s")

# Strip trailing predicate words accidentally captured in a colon-style term
# (kills the "payment means" junk class).
TRAILING_PREDICATE_RE = re.compile(
    r"\s+(?:means|includes|has(?:\s+the\s+meaning(?:\s+\w+)*)?)\s*$",
    re.IGNORECASE,
)

# Mid-line boundary used by the defensive run-on splitter: a sentence end
# followed by text that begins a new definition.
MIDLINE_SPLIT_RE = re.compile(r"\.\s+(?=\S)")

PREDICATE_WORD_RE = re.compile(r"\b(?:means|includes|has)$", re.IGNORECASE)

ANCHOR_SLUG_STRIP_RE = re.compile(r"[^a-z0-9\s-]")

# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

FALSE_STARTS = {
    "The ", "This ", "Note:", "Section ", "Division ", "Part ",
    "For ", "If ", "It ", "There ", "Subject ", "Without ",
}
FALSE_STARTS_EXACT = {"A ", "An "}

STOP_WORDS = {
    "a", "an", "and", "or", "the", "to", "of", "in", "for", "on", "at", "by",
    "with", "from", "as", "is", "it", "its", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "must", "shall", "can", "need", "dare", "ought", "used",
    "if", "then", "than", "that", "this", "these", "those", "such", "so",
    "not", "no", "nor", "but", "yet", "however", "therefore", "thus", "hence",
    "when", "where", "why", "how", "what", "which", "who", "whom", "whose",
    "all", "any", "both", "each", "every", "few", "more", "most", "other",
    "some", "only", "own", "same", "too", "very",
    "just", "also", "now", "here", "there", "up", "out", "down", "off",
    "over", "under", "again", "further", "once", "about", "into", "through",
    "during", "before", "after", "above", "below", "between", "among",
    "within", "without", "against",
    "note", "example", "item", "provision", "subject",
}


def _is_false_start(term: str) -> bool:
    for prefix in FALSE_STARTS:
        if term.startswith(prefix):
            return True
    for prefix in FALSE_STARTS_EXACT:
        if term.startswith(prefix) and term != prefix.strip():
            return True
    return False


def reject_key(key: str) -> bool:
    """True if the normalized key is junk and must not be emitted."""
    if not key:
        return True
    if key.startswith("("):
        return True
    if len(key) > 80:
        return True
    if PREDICATE_WORD_RE.search(key):  # ends in means/includes/has
        return True
    if ". " in key or "; " in key:
        return True
    if " " not in key and key in STOP_WORDS:
        return True
    # Unbalanced parentheses signal a PDF line-wrap fragment (e.g. an orphan
    # closing paren from a term that wrapped across a line), not a real term.
    if key.count("(") != key.count(")"):
        return True
    return False


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize(raw_term: str) -> tuple[str, str]:
    """Return (key, display) for a captured raw term.

    key     = stars removed, lowercased, whitespace-collapsed, stripped,
              Unicode quotes/apostrophes normalized to ASCII.
    display = stars removed, original casing, whitespace-collapsed, stripped,
              Unicode quotes/apostrophes normalized to ASCII.
    """
    stripped = raw_term.replace("*", "")
    # Normalize typographic quotes to ASCII
    stripped = stripped.replace("\u2018", "'").replace("\u2019", "'")
    stripped = stripped.replace("\u201c", '"').replace("\u201d", '"')
    display = re.sub(r"\s+", " ", stripped).strip()
    key = display.lower()
    return key, display


def make_anchor(section: str, key: str) -> str:
    slug = ANCHOR_SLUG_STRIP_RE.sub("", key).strip()
    slug = re.sub(r"\s+", "-", slug)
    return f"s{section}-{slug}"


# ---------------------------------------------------------------------------
# Definition-start scanning
# ---------------------------------------------------------------------------

def capture_term(text: str) -> str | None:
    """Capture the raw defined term from the start of a definition block."""
    term = None
    m = PREDICATE_RE.match(text)
    if m:
        term = m.group(1).strip()
    else:
        m = COLON_RE.match(text)
        if m:
            term = m.group(1).strip()
            term = TRAILING_PREDICATE_RE.sub("", term).strip()
    if not term:
        return None
    # Reject list-style continuation fragments (CDN-0172): dictionary items
    # are enumerated ("(a) X means ...; (b) Y ...") and a captured line ending
    # in "and"/"of"/"the"/"or" is the tail of a list item, not a term —
    # e.g. "film and", "arrangement in relation to property ends and".
    if re.search(r"\b(?:and|of|the|or)$", term, re.IGNORECASE):
        return None
    return term


def iter_definition_starts(block_text: str):
    """Yield raw term strings for every definition start found in ``block_text``.

    Primary: line-anchored matching (each definition on its own line, the Phase 1
    layout). Defensive: long single lines are additionally split at mid-line
    definition boundaries to recover terms from legacy run-on layouts.
    """
    for line in block_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip blockquote lines, note/example lines, and bare anchor lines.
        if stripped.startswith(">"):
            continue
        if stripped.startswith("<a id"):
            # Drop a leading "<a id=...></a>" prefix and keep scanning the rest.
            stripped = re.sub(r"^<a id=\"[^\"]*\">\s*</a>\s*", "", stripped)
            if not stripped:
                continue
        low = stripped.lower()
        if low.startswith("note:") or low.startswith("example") or low.startswith("**note"):
            continue
        # Strip a leading subsection marker "**(1)**" if present.
        stripped = re.sub(r"^\*\*\(\d+\)\*\*\s*", "", stripped)
        if not stripped:
            continue

        # Build the list of candidate sub-segments. The line itself is the first;
        # if the line is long and run-on, split it at mid-line boundaries where a
        # new definition demonstrably starts.
        segments = [stripped]
        for m in MIDLINE_SPLIT_RE.finditer(stripped):
            tail = stripped[m.end():]
            if starts_new_definition(tail):
                segments.append(tail)

        seen_in_line: set[str] = set()
        for seg in segments:
            if seg in seen_in_line:
                continue
            seen_in_line.add(seg)
            term = capture_term(seg)
            if term:
                yield term


# ---------------------------------------------------------------------------
# Source slicing
# ---------------------------------------------------------------------------

def subsection_1_block(content: str) -> str:
    """Return the subsection (1) block: from the first **(1)** to the next
    \\n**(N)** marker (where N >= 2) or EOF."""
    m = re.search(r'(?:<a id="[^"]+"></a>\s*\n)?\*\*\(1\)\*\*', content)
    if not m:
        raise ValueError("Could not find subsection (1) marker")
    start = m.end()
    nxt = re.search(r"\n\*\*\((?!1\*\*)\d+\)\*\*", content[start:])
    end = start + nxt.start() if nxt else len(content)
    return content[start:end]


# Schedule-heading markers used to truncate the GST dictionary before the
# uncurated schedule block. Matches the em-dash schedule title (e.g.
# "Schedule 1—Food") so it never trips on "Schedule 1 to the Taxation
# Administration Act 1953" inside a definition body.
GST_SCHEDULE_RE = re.compile(r"Schedule\s+\d+[–—]")


def gst_dictionary_block(content: str) -> str:
    """Return the GST dictionary body: from the intro line to the first schedule
    heading (or EOF)."""
    intro = re.search(
        r"In this Act, except so far as the contrary intention appears:",
        content,
    )
    start = intro.end() if intro else 0
    m = GST_SCHEDULE_RE.search(content, start)
    end = m.start() if m else len(content)
    return content[start:end]


# ---------------------------------------------------------------------------
# Per-act extraction
# ---------------------------------------------------------------------------

def extract_act(act: str, source: Path) -> tuple[dict, list[str]]:
    """Return (terms_dict, log_lines) for one act."""
    meta = ACTS[act]
    section = meta["section"]
    display_act = meta["display"]
    content = source.read_text(encoding="utf-8")

    if act == "gst-1999":
        block = gst_dictionary_block(content)
    else:
        block = subsection_1_block(content)

    terms: dict[str, dict] = {}
    anchors_used: dict[str, str] = {}  # anchor -> key that owns it
    log: list[str] = []

    for raw_term in iter_definition_starts(block):
        if _is_false_start(raw_term.strip()):
            continue
        key, display = normalize(raw_term)
        if reject_key(key):
            continue
        if key in terms:  # first occurrence wins
            continue
        anchor = make_anchor(section, key)
        if anchor in anchors_used:
            log.append(
                f"anchor collision: dropped {key!r} (anchor {anchor} owned by "
                f"{anchors_used[anchor]!r})"
            )
            continue
        anchors_used[anchor] = key
        terms[key] = {
            "term": display,
            "section": section,
            "anchor": anchor,
            "act": display_act,
        }

    return terms, log


def write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for act in ACTS:
        ap.add_argument(
            f"--source-{act}",
            dest=f"source_{act.replace('-', '_')}",
            default=None,
            help=f"override source markdown for {act}",
        )
    args = ap.parse_args()

    for act in ACTS:
        override = getattr(args, f"source_{act.replace('-', '_')}")
        source = Path(override) if override else DEFAULT_SOURCES[act]
        if not source.exists():
            print(f"  SKIP {act}: source not found: {source}")
            continue
        terms, log = extract_act(act, source)
        out_path = DATA_DIR / act / "definitions.json"
        write_atomic(out_path, terms)
        print(f"  {act}: {len(terms)} terms -> {out_path} (source {source})")
        for line in log:
            print(f"    {line}")


if __name__ == "__main__":
    main()
