#!/usr/bin/env python3
"""Repair the character/encoding defect classes C21 / C23 (plan Part B E-b / E-e / E-g residual).

Lossless, mechanical mappings — every change is a pure character decode/normalise:

  C23_nonstandard_hyphen  U+2010 / U+2011 (non-breaking hyphen) -> '-'
  C23_soft_hyphen         U+00AD -> '-' when it sits between two letters (it stands in
                          for a real hyphen), removed everywhere else (it was a list
                          bullet / stray)
  C21_html_entity         html.unescape on derived text (raw .html is never scanned and
                          never touched)

Scans exactly the file set scan_corpus_error_classes.character_corpus_files() plus the
derived case-summary corpus (CASE_SUMMARIES_DIR), so the detector and the repair cannot
drift.  Text-level transforms only — no JSON re-serialisation — so map/summary formatting
is byte-preserved apart from the mapped characters.

Usage:
  python3 scripts/repair_character_classes.py            # dry run: report what would change
  python3 scripts/repair_character_classes.py --apply    # write the changes
"""
import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scan_corpus_error_classes import character_corpus_files, DATA  # noqa: E402
import os  # noqa: E402

CASE_SUMMARIES_DIR = Path(
    os.environ.get(
        "CASE_SUMMARIES_DIR",
        str(ROOT / "scripts" / "cleaned" / "summaries"),
    )
)

# A soft hyphen between two letters stands in for a real hyphen.  The `(?<!\\)`
# guard stops the 'n' of a JSON `\n` escape (which immediately precedes the soft
# hyphen in the AID summaries' serialised "body") from being read as a word letter —
# those are list bullets and must be removed, not hyphenated.
SOFT_IN_WORD = re.compile(r"(?<!\\)([A-Za-z])\u00ad(?=[A-Za-z])")


def transform(text: str) -> tuple[str, list[str]]:
    """Return (new_text, list of change descriptions)."""
    changed: list[str] = []

    n2010 = text.count("\u2010")
    n2011 = text.count("\u2011")
    if n2010 or n2011:
        text = text.replace("\u2010", "-").replace("\u2011", "-")
        changed.append(f"U+2010/U+2011 -> '-' ({n2010 + n2011}x)")

    nshy = text.count("\u00ad")
    if nshy:
        # between two letters -> real hyphen
        text, n_hyphen = SOFT_IN_WORD.subn(r"\1-", text)
        # remaining -> remove (bullet / stray)
        text, n_remove = re.subn("\u00ad", "", text)
        changed.append(f"U+00AD -> '-' ({n_hyphen}x) / removed ({n_remove}x)")

    # html entities: only act when one is present, so a clean file is byte-identical
    if re.search(r"&(?:[a-zA-Z][a-zA-Z0-9]{1,31}|#\d{1,7}|#x[0-9a-fA-F]{1,6});", text):
        decoded = html.unescape(text)
        nent = text.count("&") - decoded.count("&")
        if decoded != text:
            text = decoded
            changed.append(f"html entities unescaped (~{nent} ampersand deltas)")

    return text, changed


def build_files() -> list[Path]:
    files = character_corpus_files(DATA)
    if CASE_SUMMARIES_DIR.is_dir():
        files += [p for p in CASE_SUMMARIES_DIR.glob("*.json") if p.is_file()]
    return sorted(set(files))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    touched = 0
    total_changes = 0
    for p in build_files():
        if p.suffix == ".html":
            continue
        try:
            original = p.read_text(encoding="utf-8")
        except OSError:
            continue
        new, desc = transform(original)
        if new == original:
            continue
        touched += 1
        total_changes += len(desc)
        rel = p.relative_to(ROOT) if p.is_relative_to(ROOT) else str(p)
        print(f"{rel}: {', '.join(desc)}")
        if args.apply:
            p.write_text(new, encoding="utf-8")

    print(f"\n{'APPLIED' if args.apply else 'DRY-RUN'}: {touched} file(s) changed, "
          f"{total_changes} transformation(s)")
    if not args.apply and touched:
        print("(re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
