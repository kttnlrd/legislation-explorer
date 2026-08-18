#!/usr/bin/env python3
"""
repair_rulings_chrome.py — Strip ATO page chrome from ruling text files.

Defects (from verify_data_integrity.py):
  - HTML entities: &#169; etc.
  - JS analytics: GoogleAnalytics, dataLayer, gtag, bazadebezolkohpepadr
  - page chrome: "| Legal database //", "Please note that the PDF version...",
    trailing nav junk

Structure of a contaminated file (often ONE line):
    "PR 2014/6 | Legal database // (function...analytics... ) Class Ruling
     PR 2014/6 Income tax: ... real text ... Print Email Share"

Strategy:
  1. Replace the leading "<CITATION> | Legal database // <JS>" prefix with the
     bare citation "PR 2014/6 ".
  2. Strip the JS/GA block if it appears after the first citation.
  3. Decode HTML entities.
  4. Remove known chrome phrases and trailing nav junk.

Usage:
  python3 scripts/repair_rulings_chrome.py            # dry run
  python3 scripts/repair_rulings_chrome.py --apply    # write
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RULINGS = BASE / "data" / "rulings"

# First citation at start of file, optionally followed by page chrome
CITE_AT_START = re.compile(
    r"^([A-Z]+ \d{4}/\d+[A-Za-z]*)\s*\|\s*Legal database\s*//\s*.*?(?=\s(?:Class Ruling|Product Ruling|Public Ruling|Determination|Addendum|Income Tax|GST|FBT|Superannuation|A New Tax System|Taxation Ruling|Miscellaneous|Self Managed|Deceased|Capital Gains|Goods and Services|Fringe Benefits|Fringe benefits))",
    re.S,
)
# JS analytics block (optional after the first citation)
JS_BLOCK = re.compile(
    r"\s*(?:\(function\s*\(\s*i\s*,\s*s\s*,\s*o\s*,\s*g[^)]*\)\s*\{.*?ga'\s*\);\s*)?"
    r"(?:window\.dataLayer\s*=.*?;\s*)?"
    r"(?:function\s*gtag\s*\([^)]*\)\s*\{.*?\}\s*)?"
    r"(?:gtag\([^;]*;\s*)+"
    r"(?:bazadebezolkohpepadr\s*=\s*\"[^\"]*\"\s*)?"
    r"\s*",
    re.S,
)
HTML_ENTITY = re.compile(r"&#\d+;|&[a-zA-Z]+;")
CHROME_PHRASES = [
    r"Please note that the PDF version is the authorised version of this[^.]*\.?",
    r"To make an enquiry about this publication, please phone[^.]*\.?",
    r"Persons with queries or concerns about the contents of this publication[^.]*\.?",
    r"Email: [^\s]+@ato\.gov\.au\s*",
    r"Phone: [^\s]+(?:\.|,|\s)",
    r"© Australian Taxation Office for the Commonwealth of Australia\s*$",
    r"\|\s*Legal database\s*//\s*$",
]
NAV_JUNK_TAIL = re.compile(
    r"\s*(?:Print\s+Email\s+Share\s*|\s*Share\s*|\s*Print\s*|\s*Email\s*|\s*Back to top\s*|\s*Back\s*|\s*Next\s*|\s*Previous\s*)+$",
    re.I,
)
DOUBLE_SPACE = re.compile(r" {2,}")


def strip_chrome(text: str) -> str:
    orig = text
    # 1. If file starts with "CITE | Legal database // ...", keep bare citation
    m = CITE_AT_START.match(text)
    if m:
        text = m.group(1) + " " + text[m.end():]
    # 2. Remove JS analytics block(s)
    text = JS_BLOCK.sub(" ", text)
    # 3. Decode HTML entities
    def dec(m: re.Match) -> str:
        try:
            return html.unescape(m.group(0))
        except Exception:
            return " "
    text = HTML_ENTITY.sub(dec, text)
    # 4. Remove known chrome phrases
    for ph in CHROME_PHRASES:
        text = re.sub(ph, " ", text, flags=re.S)
    # 5. Remove trailing nav junk
    text = NAV_JUNK_TAIL.sub("", text)
    # 6. Collapse multiple spaces
    text = DOUBLE_SPACE.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files = sorted(RULINGS.glob("*.txt"))
    changed = 0
    examples = []
    for p in files:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        new = strip_chrome(t)
        if new != t:
            changed += 1
            if len(examples) < 5:
                examples.append((p.name, len(t), len(new)))
            if args.apply:
                p.write_text(new, encoding="utf-8")

    print(f"{'APPLYING' if args.apply else 'DRY RUN'} — files changed: {changed}/{len(files)}")
    for name, before, after in examples:
        print(f"  {name}: {before} -> {after} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
