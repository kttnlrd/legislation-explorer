#!/usr/bin/env python3
"""Normalise PDF-extraction character artifacts across the served corpus.

One pass, stdlib only. Clears the character classes the scanner reports:

  C26_pua_glyph         Symbol/Wingdings Private-Use-Area passed through literally
                        (U+F0xx is the Latin-1 range at a fixed -0xF000 offset;
                        a few bullet glyphs need an explicit target)
  C21_html_entity       raw HTML entities in DERIVED text (source was escaped)
  C23_nonstandard_hyphen  U+2010/U+2011 -> '-'  (FTS5 treats them as separators,
                          so a quoted search for "sub-fund" matches nothing)
  C23_soft_hyphen       U+00AD removed
  C23_invisible_char    U+FEFF / zero-width removed

Not touched here: C11_table_* / C14_formula_* / C15_drawing_char. Those are table
and formula GEOMETRY (a word or operator split across cell boundaries), not a
character substitution — a character map cannot invent the missing half. They
belong to the extractor fix.

Usage:
    python scripts/normalize_extraction_chars.py            # dry-run (default)
    python scripts/normalize_extraction_chars.py --apply
    python scripts/normalize_extraction_chars.py --selfcheck
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

DATA = REPO / "data"

# Symbol-font PUA -> the Latin-1 codepoint it stands for (MS Symbol/Wingdings
# offset). U+F02D -> '-', U+F0B7 -> '·', U+F0EA -> 'ê', U+F0E9 -> 'é'.
PUA_MAP = {chr(0xF000 + i): chr(i) for i in range(0x100)}
# Glyphs whose offset target is a control codepoint or outside Latin-1: these are
# list bullets in the source PDFs, verified in-context (e.g. gst-1999 s182-5
# "These do not form part of this Act: <glyph> footnotes and endnotes; <glyph> ...").
PUA_MAP.update({"\uf09f": "\u2022", "\uf8e7": "\u2022", "\uf0b7": "\u2022"})

# Applied after the PUA map, so U+F0AD -> U+00AD -> removed falls out naturally.
CLEAN_MAP = {
    "\u2010": "-", "\u2011": "-",              # non-standard hyphens -> ASCII
    "\u00ad": "",                               # soft hyphen
    "\ufeff": "", "\u200b": "", "\u200c": "", "\u200d": "",   # invisible
}

PUA_TABLE = str.maketrans(PUA_MAP)
CLEAN_TABLE = str.maketrans(CLEAN_MAP)

# &nbsp; unescapes to U+00A0, which is not a normal space and breaks FTS
# tokenising. Fold it at the entity, not corpus-wide: existing U+00A0 in the
# corpus is left alone (that's a separate 7k-file change, not this fix).
_NBSP_ENTITIES = re.compile(r"&nbsp;|&#160;|&#xa0;", re.I)


def normalise(s: str) -> str:
    # str.translate() looks up ORDINALS, so the str-keyed maps must go through
    # maketrans (a raw str-keyed dict silently no-ops).
    s = _NBSP_ENTITIES.sub(" ", s)
    return html.unescape(s).translate(PUA_TABLE).translate(CLEAN_TABLE)


def corpus_files() -> list[Path]:
    """The exact file set the scanner's character classes run over.

    Imported from the scanner so the two can never disagree about scope.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scan_corpus_error_classes", REPO / "scripts" / "scan_corpus_error_classes.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    return sc.character_corpus_files(DATA)


def selfcheck() -> int:
    cases = [
        ("\uf0b7 footnotes", "\u2022 footnotes"),
        ("$10 + $1 \uf02d $6", "$10 + $1 - $6"),
        ("F\uf0e9d\uf0e9ral", "F\u00e9d\u00e9ral"),
        ("sub\u2011fund", "sub-fund"),
        ("soft\u00adhyphen", "softhyphen"),
        ("&bull; item &#150; x", "\u2022 item \u2013 x"),
        ("pre\ufefffix", "prefix"),
    ]
    bad = [(a, normalise(a), b) for a, b in cases if normalise(a) != b]
    for a, got, want in bad:
        print(f"  FAIL {a!r} -> {got!r} (want {want!r})")
    print(f"selfcheck: {len(cases) - len(bad)}/{len(cases)} pass")
    return 0 if not bad else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        return selfcheck()

    files = corpus_files()
    changed = 0
    for p in files:
        if p.suffix == ".html":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out = normalise(text)
        if out == text:
            continue
        changed += 1
        if args.apply:
            p.write_text(out, encoding="utf-8")
        else:
            for a, b in zip(text.splitlines(), out.splitlines()):
                if a != b:
                    print(f"  {p.relative_to(REPO)}")
                    print(f"    - {a.strip()[:100]}")
                    print(f"    + {b.strip()[:100]}")
                    break
    verb = "rewrote" if args.apply else "would change"
    print(f"\n{verb} {changed} of {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
