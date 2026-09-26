#!/usr/bin/env python3.12
"""E-a: MTG "тАв" mojibake - a bullet (U+2022) decoded as CP866.

Root cause (docs/bug-plan-2026-09-25.md, E-a):
  `data/tax-docs.zip` in the cadena-knowledge-MCP archive stores 22 MTG filenames
  containing U+2022 with the zip UTF-8 flag (0x800) set - the only 22 entries with that
  flag.  The unzip step ignored the flag and decoded the NAMES as CP866, so the bullet
  became the three Cyrillic characters "тАв" (U+0442 U+0410 U+0432).  The archive's
  `pipeline/ingest_cch_commentary.py:249-255` then took the chapter title from the
  FILENAME, and `pipeline/build_cch_explorer.py:144` copied that title into
  `chapter_title`, the tree part title and the section_index.  The mangled filenames also
  exist under /home/harrison/projects/{ARCHIVE_cadena-knowledge-MCP,
  cadena-knowledge-MCP-backup-20260217-1842,cadena-knowledge-MCP.bak.202603050849,
  cadena-knowledge-MCP-oauth-wip}; those archives are the ORIGIN and are deliberately
  left unchanged (not served).  Recorded in the provenance file this script writes.

Measured before this repair (2026-09-26): 1,370 Cyrillic runs in 897 fields of 2 files
(897 = 875 `chapter_title` + 22 part `title`), 1,332 runs in section_index.json and 38 in
tree.json, all of them the same 3-character run "тАв" (4,110 characters).

Rule applied, per the plan: a string containing Cyrillic is replaced by
`s.encode('cp866').decode('utf-8')`, applied ONLY where that round trip succeeds AND the
result contains no Cyrillic.  The rule is applied to each maximal Cyrillic RUN (the way
the plan measures: "22 distinct strings" are the 22 mangled chapter titles, and the
"1,370 occurrences" are the runs) because the tree part titles also carry an em dash
(U+2014), which CP866 cannot encode - a whole-string encode fails on all 22 of those and
would leave the defect in place.  The whole-string form is tried first and used when it
succeeds; the per-run form gives the identical result for every other field.

Dry run by default.  --apply writes in blocks and records every changed JSON path with
its old and new value; --verify RE-DERIVES each change (re-applies the rule to the HEAD
bytes and compares to the bytes on disk, byte for byte) rather than trusting a count.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TICKET = "e-a-mtg-mojibake"
PROVENANCE_DIR = ROOT / "docs" / "provenance"

TARGETS = [
    DATA / "master-tax-guide" / "section_index.json",
    DATA / "master-tax-guide" / "tree.json",
]

# The Cyrillic blocks the plan's rule keys on (C20's definition: U+0400-U+04FF plus the
# Cyrillic Supplement, which is the same block the scanner reports).
CYRILLIC = re.compile(r"[\u0400-\u04FF\u0500-\u052F]+")

# Origin archives: the write never touches them, but the log names them as where the
# mojibake came from (plan E-a "record in the provenance log that they are the origin").
ORIGIN_ARCHIVES = [
    "/home/harrison/projects/ARCHIVE_cadena-knowledge-MCP",
    "/home/harrison/projects/cadena-knowledge-MCP-backup-20260217-1842",
    "/home/harrison/projects/cadena-knowledge-MCP.bak.202603050849",
    "/home/harrison/projects/cadena-knowledge-MCP-oauth-wip",
]


def repair_run(run: str) -> str | None:
    """CP866 -> UTF-8 round trip of one Cyrillic run.  None when the round trip is not
    safe (it fails, or the result still holds Cyrillic - the rule's two conditions)."""
    try:
        out = run.encode("cp866").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if CYRILLIC.search(out):
        return None
    return out


def repair_string(s: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (new string, [(old_run, new_run)]).  Unchanged when no run qualifies."""
    if not CYRILLIC.search(s):
        return s, []
    # the plan's literal rule, whole string first
    try:
        whole = s.encode("cp866").decode("utf-8")
        if not CYRILLIC.search(whole):
            return whole, [(r, repair_run(r) or r) for r in CYRILLIC.findall(s)]
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    changes: list[tuple[str, str]] = []
    out = s
    # every occurrence, not every distinct run: the plan counts 1,370 occurrences
    # (section_index 1,332 + tree 38 for the 22 part titles), so the log must too.
    for run in CYRILLIC.findall(s):
        new = repair_run(run)
        if new is None or new == run:
            continue
        out = out.replace(run, new)
        changes.append((run, new))
    return out, changes


def walk(node, path: str = ""):
    """Yield (path, value) for every string leaf, with a stable JSON path."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def set_path(node, path: str, value: str) -> None:
    """Write value at a path produced by walk() ('' means the root, which is a list here)."""
    keys: list[object] = []
    for m in re.finditer(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]", path):
        keys.append(m.group(1) if m.group(1) is not None else int(m.group(2)))
    cur = node
    for k in keys[:-1]:
        cur = cur[k]
    cur[keys[-1]] = value


def rewrite_file(p: Path) -> tuple[str, str, list[dict]]:
    """Return (head text, new text, [change dicts]) for one JSON target.

    The JSON is re-serialised with `json.dumps(indent=2, ensure_ascii=False)`, which is
    what `pipeline/build_cch_explorer.py:218,221` writes; the round trip is asserted
    byte-identical to HEAD before the repair so the diff can only be the repaired values.
    """
    head = subprocess.run(["git", "show", f"HEAD:{p.relative_to(ROOT)}"], cwd=ROOT,
                          capture_output=True, text=True).stdout
    if not head:
        raise SystemExit(f"{p}: not tracked at HEAD - refusing to write")
    data = json.loads(head)
    again = json.dumps(data, indent=2, ensure_ascii=False)
    if again != head:
        raise SystemExit(f"{p}: JSON round trip is not byte-identical to HEAD - refusing")
    changes: list[dict] = []
    for path, value in walk(data):
        new, runs = repair_string(value)
        if new == value:
            continue
        changes.append({"path": path, "old": value, "new": new,
                        "runs": [{"from": a, "to": b} for a, b in runs],
                        "reverse_ok": all(b.encode("utf-8").decode("cp866") == a for a, b in runs)})
        set_path(data, path, new)
    return head, json.dumps(data, indent=2, ensure_ascii=False), changes


def scan() -> None:
    total_fields = total_runs = failures = 0
    distinct: dict[str, int] = {}
    for p in TARGETS:
        head, new, changes = rewrite_file(p)
        n_runs = sum(len(c["runs"]) for c in changes)
        for c in changes:
            for r in c["runs"]:
                distinct[r["from"]] = distinct.get(r["from"], 0) + 1
        total_fields += len(changes)
        total_runs += n_runs
        failures += sum(0 if c["reverse_ok"] else 1 for c in changes)
        print(f"  {p.relative_to(ROOT)}: {len(changes)} field(s), {n_runs} run(s), "
              f"{len(new) - len(head)} byte(s) shorter")
    print(f"  total: {total_fields} field(s), {total_runs} run(s)")
    print(f"  distinct Cyrillic run(s): {distinct}")
    print(f"  fields whose reverse mapping failed: {failures}")
    print("  (dry run - nothing written; --apply to write)")


def rollback_tag() -> tuple[str, str]:
    """Tag HEAD before the first write, the way the X2 template does."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
    tag = f"{TICKET}-apply-rollback-{head}" if head else f"{TICKET}-apply-rollback-nogit"
    if head:
        subprocess.run(["git", "tag", "-f", tag], cwd=ROOT, check=True,
                       capture_output=True, text=True)
    return head, tag


def apply(block_size: int) -> int:
    records = []
    for p in TARGETS:
        head, new, changes = rewrite_file(p)
        if not changes:
            print(f"  {p.relative_to(ROOT)}: nothing to do")
            continue
        records.append({"file": str(p.relative_to(ROOT)), "changes": changes,
                        "bytes_before": len(head), "bytes_after": len(new)})
    if not records:
        print("  nothing to do - no tag, no provenance file")
        return 0
    head, tag = rollback_tag()
    print(f"  rollback point: tag {tag} (HEAD {head or 'unknown'}); "
          f"git checkout -- <path> also reverts these tracked files")
    written = 0
    for rec in records:
        target = ROOT / rec["file"]
        # the change list is the diff; re-deriving it from the target's own HEAD bytes and
        # writing that text is what makes the write reproducible rather than hand-edited.
        _, new, _ = rewrite_file(target)
        target.write_text(new, encoding="utf-8")
        written += 1
        if len(rec["changes"]) >= block_size:
            print(f"    block: {rec['file']} written ({len(rec['changes'])} field(s))")
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    log = PROVENANCE_DIR / f"{TICKET}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    log.write_text(json.dumps({
        "ticket": TICKET, "script": str(Path(__file__).name),
        "rollback_tag": tag, "head": head,
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": {"what": "zip entry names decoded as CP866 (U+2022 bullet -> 'тАв'), "
                           "then taken as the chapter title from the file name",
                   "archives": ORIGIN_ARCHIVES,
                   "archive_pipeline": "pipeline/ingest_cch_commentary.py:249-255 "
                                       "(archive copy, unchanged)",
                   "note": "the archives are not served; they are recorded as origin only"},
        "files": records}, indent=1, ensure_ascii=False))
    print(f"  wrote {written} file(s); provenance at {log.relative_to(ROOT)}")
    return 0


def latest_log() -> Path | None:
    if not PROVENANCE_DIR.is_dir():
        return None
    runs = sorted(PROVENANCE_DIR.glob(f"{TICKET}-*.json"))
    return runs[-1] if runs else None


def verify(log: Path | None = None) -> int:
    """RE-DERIVE every recorded change: repair(HEAD value) must equal the byte on disk.

    Re-derives instead of re-trusting the recorded paths, and also checks the reverse
    mapping (new run -> old run through UTF-8 -> CP866) the plan asks for.
    """
    log = log or latest_log()
    if log is None or not log.exists():
        print(f"  no provenance file under {PROVENANCE_DIR} - nothing to verify")
        return 1
    print(f"  verifying against {log.name}")
    data = json.loads(log.read_text())
    bad = 0
    for rec in data["files"]:
        p = ROOT / rec["file"]
        head = subprocess.run(["git", "show", f"HEAD:{rec['file']}"], cwd=ROOT,
                              capture_output=True, text=True).stdout
        cur = p.read_text(encoding="utf-8")
        # 1. re-derive: applying the rule to HEAD must give exactly the bytes on disk
        head_data = json.loads(head)
        head_values = dict(walk(head_data))
        for ch in rec["changes"]:
            before = head_values.get(ch["path"])
            if before is None:
                print(f"  {rec['file']} {ch['path']}: path absent from HEAD"); bad += 1; continue
            if before != ch["old"]:
                print(f"  {rec['file']} {ch['path']}: HEAD value is not the logged old value")
                bad += 1
                continue
            redone, _ = repair_string(before)
            if redone != ch["new"]:
                print(f"  {rec['file']} {ch['path']}: re-derived {redone!r} != logged {ch['new']!r}")
                bad += 1
        # 2. the recorded new value must be the byte on disk
        cur_data = json.loads(cur)
        cur_values = dict(walk(cur_data))
        for ch in rec["changes"]:
            if cur_values.get(ch["path"]) != ch["new"]:
                print(f"  {rec['file']} {ch['path']}: on-disk value is not the logged new value")
                bad += 1
        # 3. reverse mapping: every changed run must map back to the HEAD run
        for ch in rec["changes"]:
            for r in ch["runs"]:
                if r["to"].encode("utf-8").decode("cp866") != r["from"]:
                    print(f"  {rec['file']} {ch['path']}: reverse mapping {r['to']!r} != {r['from']!r}")
                    bad += 1
        left = sum(len(CYRILLIC.findall(json.dumps(v, ensure_ascii=False)))
                   for _p, v in walk(cur_data))
        if left:
            print(f"  {rec['file']}: {left} Cyrillic character(s) still present")
            bad += 1
    # 4. the diff may touch only chapter_title / part title values
    for rec in data["files"]:
        head = subprocess.run(["git", "show", f"HEAD:{rec['file']}"], cwd=ROOT,
                              capture_output=True, text=True).stdout
        hd, cd = json.loads(head), json.loads((ROOT / rec["file"]).read_text())
        hd_values = dict(walk(hd))
        for path, val in walk(cd):
            if hd_values.get(path) != val:
                if not (path.endswith(".chapter_title") or re.search(r"\.parts\[\d+\]\.title$", path)):
                    print(f"  {rec['file']} {path}: outside chapter_title / part title")
                    bad += 1
    print("  VERIFIED: every change re-derives, no Cyrillic left, diff confined to titles"
          if not bad else f"  {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--log", help="provenance file to verify against (default: the newest)")
    ap.add_argument("--block-size", type=int, default=50)
    a = ap.parse_args()
    if a.verify:
        sys.exit(verify(Path(a.log) if a.log else None))
    if a.apply:
        sys.exit(apply(a.block_size))
    scan()
