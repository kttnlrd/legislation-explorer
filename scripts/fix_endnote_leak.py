#!/usr/bin/env python3.12
"""CDN-0222 — remove the OPC endnote appendix leaked into the last section of an act.

The compilation endnotes ("Endnote 1—About the endnotes" through "Endnote 4—Amendment
history") are not law text: they belong to the compilation, not to a section. The ingester
never cut them off, so the whole appendix was appended to the last section file of four
acts. The appendix begins at its own page header, so the boundary is unambiguous: cut at the
first occurrence of the marker and drop everything after it.

Targets (corpus-wide; only these four files carry the marker):

  gst-1999  sections/part-6-3/division-195/195-1.md     (also a C25_dot_leader_endnote find)
  sis-1993  sections/part-32/division-unknown/381.md    (also a C25_dot_leader_endnote find)
  fbt-1986  sections/part-xii/division-unknown/167.md   (also a C25_dot_leader_endnote find)
  aml-ctf-2006 sections/part-schedule-1/division-1/1.md (same shape, no dot leaders)

sis 381 and aml 1 carry law text and the marker on the SAME line; the cut keeps the law text
up to the marker. gst 195-1 and fbt 167 start the block on its own line.

Dry-run by default. `--apply` writes and logs provenance to
docs/provenance/cdn-0222-<stamp>.json. `--verify` re-derives each target from HEAD and
asserts the on-disk file is exactly that: HEAD truncated at the marker, trailing whitespace
stripped, newline-terminated. A rollback tag is created by the caller (git tag) before
`--apply`.

Usage:
  /usr/bin/python3.12 scripts/fix_endnote_leak.py                 # dry run
  /usr/bin/python3.12 scripts/fix_endnote_leak.py --apply
  /usr/bin/python3.12 scripts/fix_endnote_leak.py --verify
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "Endnotes Endnote 1—About the endnotes"

TARGETS = [
    "data/gst-1999/sections/part-6-3/division-195/195-1.md",
    "data/sis-1993/sections/part-32/division-unknown/381.md",
    "data/fbt-1986/sections/part-xii/division-unknown/167.md",
    "data/aml-ctf-2006/sections/part-schedule-1/division-1/1.md",
]


def truncate(text: str) -> str:
    """Return `text` up to the endnote appendix, or unchanged if the marker is absent."""
    idx = text.find(MARKER)
    if idx == -1:
        return text
    return text[:idx].rstrip() + "\n"


def head_text(relpath: str) -> str:
    out = subprocess.run(
        ["git", "show", f"HEAD:{relpath}"], cwd=ROOT, capture_output=True, text=True
    )
    if out.returncode != 0:
        raise SystemExit(f"git show HEAD:{relpath} failed: {out.stderr.strip()}")
    return out.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    report = []
    problems = 0
    for rel in TARGETS:
        path = ROOT / rel
        cur = path.read_text(encoding="utf-8")
        new = truncate(cur)
        n_marker = cur.count(MARKER)
        removed = len(cur) - len(new)
        rec = {
            "path": rel,
            "marker_occurrences": n_marker,
            "chars_removed": removed,
            "bytes_before": len(cur),
            "bytes_after": len(new),
            "changed": cur != new,
        }
        report.append(rec)
        if args.verify:
            expected = truncate(head_text(rel))
            ok = cur == expected
            problems += 0 if ok else 1
            print(f"  {'ok  ' if ok else 'FAIL'} {rel} ({len(cur)} bytes)")
            if not ok:
                print(f"       expected {len(expected)} bytes from HEAD truncation")
            continue
        print(
            f"  {rel}: marker x{n_marker}, removes {removed:,} of {len(cur):,} bytes -> "
            f"{len(new):,}"
        )
        if args.apply and cur != new:
            path.write_text(new, encoding="utf-8")

    if args.verify:
        print("PASS" if not problems else f"{problems} FAILURE(S)")
        return 1 if problems else 0

    if args.apply:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        out = ROOT / "docs" / "provenance" / f"cdn-0222-{stamp}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "ticket": "CDN-0222",
                    "marker": MARKER,
                    "applied_at": dt.datetime.now().isoformat(timespec="seconds"),
                    "files": report,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"provenance -> {out.relative_to(ROOT)}")
    else:
        print("dry run (pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
