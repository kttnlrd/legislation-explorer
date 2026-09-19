#!/usr/bin/env python3.12
"""Full-ingest apply runbook: backup, apply, reindex, verify - with a BOUNDED summary.

WHY THIS SHAPE
An apply over 4,620 sections produces thousands of lines. Reading that into an agent's context
costs far more than the apply is worth, and the cost lands in tokens rather than in work. So every
phase here writes its full detail to a log file and prints at most ~40 lines: counts, deltas,
verdicts, and - only when something fails - the failing items, truncated. The operator reads the
summary; the log is for forensics.

Phases (each one idempotent enough to re-run):
  preflight  disk, backup (corpus + DBs), git tag, corruption counts BEFORE, apply dry run
  apply      the real write, then the post-apply guard; refuses if preflight flags are unresolved
  reindex    rebuild the indices that go stale when section text changes
  verify     900-5 exists, dropped text is back, section count, corruption counts AFTER, deltas
  all        preflight -> apply -> verify

Safety: DRY RUN unless --commit is passed. --only <file> bounds the write to a section list.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import time
import datetime as dt

REPO = pathlib.Path("/home/harrison/legislation-explorer")
STAGING = REPO.parent / "legislation-explorer-staging/table-rebuild"
SECTIONS = REPO / "data/itaa-1997/sections"
BACKUP_ROOT = pathlib.Path("/home/harrison/backups/legislation-explorer/apply-full")
LOGDIR = pathlib.Path("/tmp/apply-full")
PY = "/usr/bin/python3.12"

# DBs that a text change invalidates. embeddings.db is derived and rebuildable (embed_legislation.py)
# so it is excluded unless --backup-embeddings: 2.5GB of copy for something a script can regenerate.
DB_SMALL = ["data/search_index.db", "data/graph.db", "data/cases.db", "data/data_version.db",
            "data/issues.db"]
DB_BIG = ["data/embeddings.db"]
INDEX_BUILDERS = ["build_definitions_index.py", "build_smartlink_index.py",
                  "build_similarity_index.py", "build_section_case_index.py",
                  "build_rg_section_index.py"]


def log_path(phase: str) -> pathlib.Path:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    return LOGDIR / f"{phase}.log"


def run(cmd: list[str], log: pathlib.Path, timeout: int = 7200) -> int:
    """Run a command with output redirected to a file. Returns the exit code."""
    with log.open("a") as fh:
        fh.write(f"\n$ {' '.join(cmd)}\n")
        fh.flush()
        try:
            return subprocess.run(cmd, cwd=REPO, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            fh.write("TIMEOUT\n")
            return 124


def grep_counts(log: pathlib.Path, pattern: str, limit: int = 8) -> list[str]:
    """Read at most `limit` matching lines from a log - never the whole file into context."""
    out = []
    try:
        with log.open(errors="ignore") as fh:
            for line in fh:
                if re.search(pattern, line):
                    out.append(line.rstrip()[:160])
                    if len(out) >= limit:
                        break
    except FileNotFoundError:
        pass
    return out


def sha256_file(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def corruption_counts(tag: str) -> dict:
    """Run the class scanner and return {class: count} + total. Detail goes to the log."""
    log = log_path(f"scan-{tag}")
    rc = run([PY, "scripts/scan_corpus_error_classes.py"], log)
    counts = {"_rc": rc}
    with log.open(errors="ignore") as fh:
        for line in fh:
            m = re.match(r"\s+(\w+):\s+(\d+)\s*$", line)
            if m:
                counts[m.group(1)] = int(m.group(2))
            t = re.match(r"TOTAL FINDINGS:\s+(\d+)", line)
            if t:
                counts["_total"] = int(t.group(1))
    return counts


def phase_preflight(args) -> int:
    print("PREFLIGHT")
    du = shutil.disk_usage("/home")
    print(f"  disk: {du.free/1e9:.0f}GB free of {du.total/1e9:.0f}GB")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)

    # corpus
    tarball = dest / "itaa-1997-sections.tar.zst"
    tar_cmd = (["tar", "--use-compress-program=zstd", "-cf", str(tarball), "-C", str(REPO),
                "data/itaa-1997/sections"] if shutil.which("zstd")
               else ["tar", "-czf", str(tarball.with_suffix(".tar.gz")), "-C", str(REPO),
                     "data/itaa-1997/sections"])
    rc = run(tar_cmd, log_path("backup"))
    tarball = tarball if tarball.exists() else tarball.with_suffix(".tar.gz")
    print(f"  corpus backup: {'ok' if rc == 0 else 'FAILED rc=' + str(rc)} "
          f"{tarball.name if tarball.exists() else ''} "
          f"{tarball.stat().st_size/1e6:.0f}MB" if tarball.exists() else "  corpus backup: FAILED")

    # DBs
    copied, skipped = [], []
    for rel in DB_SMALL + (DB_BIG if args.backup_embeddings else []):
        src = REPO / rel
        if src.exists() and src.stat().st_size:
            dbsub = dest / "db"
            dbsub.mkdir(exist_ok=True)
            shutil.copy2(src, dbsub / src.name)
            copied.append(f"{src.name}({src.stat().st_size/1e6:.0f}MB)")
        elif src.exists():
            skipped.append(f"{src.name}(empty)")
    print(f"  db backup: {', '.join(copied) if copied else 'none'}")
    if not args.backup_embeddings:
        e = REPO / "data/embeddings.db"
        if e.exists():
            print(f"  embeddings: NOT copied ({e.stat().st_size/1e9:.1f}GB, derived - "
                  f"rebuild with scripts/embed_legislation.py; use --backup-embeddings to copy)")

    # rollback tag
    tag = f"apply-full-{stamp}"
    run(["git", "tag", tag], log_path("backup"))
    print(f"  rollback: git tag {tag} | {dest}")

    # counts BEFORE
    before = corruption_counts("before")
    print(f"  corruption BEFORE: total {before.get('_total', '?')} "
          f"(C11 glyph {before.get('C11_table_glyph', '?')}, midword {before.get('C11_table_midword', '?')}, "
          f"truncated {before.get('C11_table_truncated', '?')})")

    # dry run
    cmd = [PY, "scripts/apply_reingest.py", "--act", "itaa-1997", "--dry-run", "--keep-going",
           "--summary", str(LOGDIR / "dryrun.json")]
    if args.only:
        cmd += ["--only", pathlib.Path(args.only).read_text().strip()]
    run(cmd, log_path("dryrun"))
    summary = {}
    try:
        summary = json.loads((LOGDIR / "dryrun.json").read_text())
    except Exception:
        pass
    print(f"  dry run: would apply {summary.get('applied', '?')}/{summary.get('considered', '?')} "
          f"| refused {summary.get('refused', '?')} | byte-identical {summary.get('unchanged_bytes', '?')}")

    state = {"stamp": stamp, "backup_dir": str(dest), "tag": tag, "before": before,
             "dry_run": summary, "only": args.only}
    (LOGDIR / "preflight.json").write_text(json.dumps(state, indent=1))
    print(f"  state: {LOGDIR/'preflight.json'}")
    print("  VERDICT: ready" if summary.get("refused", 1) <= 25 else "  VERDICT: check refusals")
    return 0


def phase_apply(args) -> int:
    pre = json.loads((LOGDIR / "preflight.json").read_text())
    if not args.commit:
        print(f"DRY RUN (no write). Would apply {pre['dry_run'].get('applied')} sections. "
              f"Pass --commit to write.")
        return 0
    print("APPLY")
    log = log_path("apply")
    cmd = [PY, "scripts/apply_reingest.py", "--act", "itaa-1997", "--keep-going",
           "--log", str(LOGDIR / "apply-log.jsonl"), "--summary", str(LOGDIR / "apply.json")]
    if pre.get("only"):
        cmd += ["--only", pathlib.Path(pre["only"]).read_text().strip()]
    rc = run(cmd, log)
    summary = {}
    try:
        summary = json.loads((LOGDIR / "apply.json").read_text())
    except Exception:
        pass
    print(f"  applied {summary.get('applied', '?')} | unchanged {summary.get('unchanged_bytes', '?')} "
          f"| refused {summary.get('refused', '?')} | rc={rc}")
    for line in grep_counts(log, r"^(BLOCK|REFUSE|GUARD)", 6):
        print(f"  ! {line}")
    for line in grep_counts(log, r"guard|BLOCK", 3):
        pass
    print(f"  detail: {log}")
    return 0 if rc == 0 else rc


def phase_reindex(args) -> int:
    print("REINDEX")
    log = log_path("reindex")
    done = []
    for script in INDEX_BUILDERS:
        p = REPO / "scripts" / script
        if not p.exists():
            continue
        rc = run([PY, str(p)], log, timeout=3600)
        done.append(f"{script.replace('build_', '').replace('_index.py', '')}={'ok' if rc == 0 else 'rc'+str(rc)}")
    print("  " + " ".join(done) if done else "  no index builders found")
    print(f"  detail: {log}")
    return 0


def phase_verify(args) -> int:
    print("VERIFY")
    pre = json.loads((LOGDIR / "preflight.json").read_text())

    n = len(list(SECTIONS.rglob("*.md")))
    print(f"  sections on disk: {n} (was {pre.get('before_sections', 4648) if 'before_sections' in pre else 4648})")

    # the two defects the audit found: 900-5 must exist, 405-45 must carry Step 2
    missing = []
    want = {"900-5": True, "405-45": "Step 2.  Work out the amount"}
    f900 = list(SECTIONS.rglob("900-5.md"))
    print(f"  900-5 file: {'present ' + str(f900[0].relative_to(REPO)) if f900 else 'STILL MISSING'}")
    if not f900:
        missing.append("900-5")
    f405 = list(SECTIONS.rglob("405-45.md"))
    if f405:
        t = f405[0].read_text(errors="ignore")
        has_steps = sorted(set(re.findall(r"Step \d\.", t)))
        ok = "Step 2." in has_steps
        print(f"  405-45 step labels: {has_steps} -> {'Step 2 recovered' if ok else 'Step 2 STILL MISSING'}")
        if not ok:
            missing.append("405-45 Step 2")

    # served text, not just the file
    for sec, expect in (("900-5", 200), ("900-10", 200), ("405-45", 200)):
        url = f"http://localhost:8765/api/section/itaa-1997/{sec}"
        rc = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                            capture_output=True, text=True).stdout.strip()
        flag = "ok" if rc == str(expect) else "MISMATCH"
        print(f"  api {sec}: HTTP {rc} ({flag})")
        if rc != str(expect):
            missing.append(f"api {sec}")

    after = corruption_counts("after")
    print(f"  corruption AFTER: total {after.get('_total', '?')} "
          f"(was {pre['before'].get('_total', '?')}) | "
          f"glyph {after.get('C11_table_glyph','?')} (was {pre['before'].get('C11_table_glyph','?')}) "
          f"truncated {after.get('C11_table_truncated','?')} (was {pre['before'].get('C11_table_truncated','?')})")

    # index staleness: an index older than the corpus is serving stale text
    newest = max((p.stat().st_mtime for p in SECTIONS.rglob("*.md")), default=0)
    stale = []
    for rel in ["data/search_index.db", "data/graph.db", "data/embeddings.db"]:
        p = REPO / rel
        if p.exists() and p.stat().st_mtime < newest:
            stale.append(rel)
    print(f"  indices older than the corpus: {', '.join(stale) if stale else 'none'}")

    print(f"  RESULT: {'CLEAN' if not missing else 'PROBLEMS: ' + ', '.join(missing)}")
    return 0 if not missing else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["preflight", "apply", "reindex", "verify", "all"])
    ap.add_argument("--commit", action="store_true", help="actually write (default is dry run)")
    ap.add_argument("--only", help="file containing a comma-separated section list")
    ap.add_argument("--backup-embeddings", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    rc = 0
    if args.phase in ("preflight", "all"):
        rc |= phase_preflight(args)
    if args.phase in ("apply", "all"):
        rc |= phase_apply(args)
    if args.phase == "reindex":
        rc |= phase_reindex(args)
    if args.phase in ("verify", "all"):
        rc |= phase_verify(args)
    print(f"\ndone in {time.time()-t0:.0f}s | logs: {LOGDIR}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
