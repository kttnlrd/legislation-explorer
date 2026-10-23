#!/usr/bin/env python3
"""CDN-0304 + CDN-0305 fix.

CDN-0304: fbt-1986 section filenames are lowercase while frontmatter `section`
(and tree id / citation) is uppercase (135m.md vs s 135M). 172 files. Canonical
is the frontmatter section (statute case). Rename file + rewrite tree.json path.

CDN-0305: duplicated `<a id="x">` anchors in 23 section files. Keep the first
occurrence of each id, drop the redundant repeats.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

DATA = Path("data")
DRY = "--apply" not in sys.argv

# ── CDN-0304 ────────────────────────────────────────────────────────────────
renames: list[tuple[Path, Path]] = []
for f in sorted((DATA / "fbt-1986" / "sections").rglob("*.md")):
    text = f.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^section:\s*[\"']?([^\"'\n]+)", text, re.M)
    if not m:
        continue
    fm = m.group(1).strip()
    if f.stem != fm and f.stem.lower() == fm.lower():
        renames.append((f, f.with_name(fm + ".md")))

# collisions would mean two files claim the same canonical name
targets = [str(t).lower() for _, t in renames]
assert len(targets) == len(set(targets)), "rename collision"

tree_path = DATA / "fbt-1986" / "tree.json"
tree_raw = tree_path.read_text(encoding="utf-8")
tree = json.loads(tree_raw)
path_map = {str(src.relative_to(DATA / "fbt-1986" / "sections")): dst.name
            for src, dst in renames}
changed_paths = 0


def walk(node):
    global changed_paths
    if isinstance(node, dict):
        p = node.get("path")
        if isinstance(p, str) and Path(p).name in {Path(k).name for k in path_map}:
            new = path_map.get(p) or path_map.get(str(Path(p)))
            if new and Path(p).name != new:
                node["path"] = str(Path(p).with_name(new))
                changed_paths += 1
        for v in node.values():
            walk(v)
    elif isinstance(node, list):
        for v in node:
            walk(v)


walk(tree)

print(f"CDN-0304: {len(renames)} files to rename, {changed_paths} tree paths to rewrite")
for src, dst in renames[:3]:
    print(f"  {src.name} -> {dst.name}")

if not DRY:
    for src, dst in renames:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
    tree_path.write_text(json.dumps(tree, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

# ── CDN-0305 ────────────────────────────────────────────────────────────────
anchor_re = re.compile(r'<a\s+id="([^"]+)"\s*></a>\s*')
files_fixed = anchors_removed = 0
for p in sorted((DATA).rglob("*.md")):
    text = p.read_text(encoding="utf-8", errors="replace")
    ids = anchor_re.findall(text)
    dupes = {k for k, v in Counter(ids).items() if v > 1}
    if not dupes:
        continue
    seen: set[str] = set()

    def repl(m):
        aid = m.group(1)
        if aid in seen:
            return ""
        seen.add(aid)
        return m.group(0)

    new_text = anchor_re.sub(repl, text)
    removed = len(ids) - len(anchor_re.findall(new_text))
    files_fixed += 1
    anchors_removed += removed
    if not DRY:
        p.write_text(new_text, encoding="utf-8")

print(f"CDN-0305: {files_fixed} files, {anchors_removed} redundant anchors removed")
print("DRY RUN" if DRY else "APPLIED")
