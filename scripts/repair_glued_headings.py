#!/usr/bin/env python3
"""Repair C24 glued headings (CDN-0221): split a bold heading that the ingester
glued to the end of the preceding paragraph in aml-ctf-2006.

The detector's own shape is reused verbatim so this fixes exactly what is flagged:
a sentence-ending punctuation + space + a bold run that ends the line, where the bold
run is the act's sub-heading and belongs on its own line.
"""
import re
from pathlib import Path

DATA = Path("/home/harrison/legislation-explorer/data/aml-ctf-2006/sections")

# Identical to scan_corpus_error_classes.GLUED_HEADING, but with capturing groups.
GLUED = re.compile(r"([.;:)] )(\*\*[A-Z][^*\n]{0,100}\*\*)[ \t]*$", re.M)

changed = 0
files_changed = 0
for p in sorted(DATA.rglob("*.md")):
    text = p.read_text(encoding="utf-8")
    new, n = GLUED.subn(r"\1\n\n\2", text)
    if n:
        p.write_text(new, encoding="utf-8")
        changed += n
        files_changed += 1
        print(f"{p.relative_to(DATA)}: {n} heading(s) split")

print(f"\n{changed} headings across {files_changed} files")
