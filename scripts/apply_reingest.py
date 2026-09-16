#!/usr/bin/env python3
"""CDN-0193 — the whole-section applier: staged READY re-ingest -> live corpus.

The counterpart to scripts/apply_itaa_table_fixes.py, which is a per-TABLE
driver: it re-extracts a table from the PDF and rebuilds the text itself, so it
cannot write a table-less section and it does not write the bytes a human
reviewed.  This one does exactly one thing: it copies a staged `output.md` over
the corpus file BYTE-FOR-BYTE.  Nothing is re-extracted, re-rendered or
reformatted here — the reviewed bytes are the bytes that land.

Refusals (a refusal is per section; the batch continues only with --keep-going):
  * not READY in the staging tree (verdict comes from table_rebuild_staging,
    never reimplemented here);
  * the staged output's sha256 no longer matches its staging record (tamper);
  * the corpus file's sha256 no longer matches the source hash recorded at
    staging time (the corpus moved underneath the candidate);
  * a review record that is not pinned to this exact output hash;
  * no corpus file recorded at staging time (a NEW section — creating files is
    a different decision from replacing reviewed ones).

Writes are atomic per file (temp file in the same directory, fsync, os.replace)
and resumable (an append-only JSONL log; a re-run skips what it already wrote
unless --force).  After a real batch, scripts/corpus_change_guard.py runs over
the changed files and a BLOCK is a hard failure.

Usage
  /usr/bin/python3.12 scripts/apply_reingest.py --act itaa-1997 \\
      --staging-root ../legislation-explorer-staging/table-rebuild \\
      [--only 82-150,30-15] [--limit N] [--dry-run] [--keep-going] \\
      [--force] [--log apply-log.jsonl] [--corpus-root DIR] [--no-guard]

Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


STAGING = _load("table_rebuild_staging")   # verdict logic lives there, not here


class ApplyError(RuntimeError):
    """This section will not be written; the reason is the message."""


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ── the per-section decision ────────────────────────────────────────────────
def plan_section(act: str, section: str, status: dict, root: Path,
                 corpus_root: Path | None = None) -> dict:
    """What would be written for one section, or ApplyError with the reason.

    `status` is table_rebuild_staging's own verdict for this section.
    """
    key = f"{act}/{section}"
    if status is None:
        raise ApplyError(f"{key}: not staged under {root}")
    if status["status"] != "READY":
        why = "; ".join(status.get("reasons") or []) or ",".join(status.get("risks") or [])
        raise ApplyError(f"{key}: {status['status']} — {why}")

    d = root / act / section
    rep = json.loads((d / "report.json").read_text())

    out_path = d / "output.md"
    new_bytes = out_path.read_bytes()
    new_sha = _sha(new_bytes)
    want = (rep.get("artifacts") or {}).get("output.md", {}).get("sha256")
    if want != new_sha:
        raise ApplyError(f"{key}: staged output.md sha256 {new_sha[:12]} != staged record "
                         f"{str(want)[:12]} — tampered after staging")

    src = rep.get("source_path")
    if not src:
        raise ApplyError(f"{key}: no corpus file recorded at staging time (new section) — "
                         f"this applier replaces reviewed files, it does not create them")
    target = Path(src)
    if corpus_root:   # tests / throwaway copies: re-root the recorded path
        target = Path(corpus_root) / target.relative_to(_corpus_base(src, act))
    if not target.is_file():
        raise ApplyError(f"{key}: corpus file {target} is gone since staging")
    old_bytes = target.read_bytes()
    old_sha = _sha(old_bytes)
    if old_sha != rep.get("source_sha256"):
        raise ApplyError(f"{key}: corpus file changed since staging "
                         f"(now {old_sha[:12]}, staged against {str(rep.get('source_sha256'))[:12]})")

    rev_path = d / "review.json"
    if rev_path.is_file():
        rev = json.loads(rev_path.read_text())
        if rev.get("output_sha256") != new_sha:
            raise ApplyError(f"{key}: review.json is pinned to output "
                             f"{str(rev.get('output_sha256'))[:12]}, not {new_sha[:12]} "
                             f"— stale approval")

    return {"act": act, "section": section, "target": target, "bytes": new_bytes,
            "old_sha256": old_sha, "new_sha256": new_sha, "size": len(new_bytes),
            "verdict": status["status"], "changed": old_sha != new_sha,
            "reviewed_by": status.get("reviewed_by")}


def _corpus_base(src: str, act: str) -> Path:
    """The `data/<act>` prefix of a recorded corpus path, for re-rooting."""
    p = Path(src)
    for parent in p.parents:
        if parent.name == act:
            return parent
    raise ApplyError(f"cannot locate '{act}' in recorded corpus path {src}")


# ── the write ───────────────────────────────────────────────────────────────
def atomic_write(target: Path, data: bytes) -> None:
    """Temp file in the same directory, fsync, os.replace: no partial file."""
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_log(path: Path) -> set[str]:
    """Sections already written, for resume."""
    done: set[str] = set()
    if not path.is_file():
        return done
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("applied"):
            done.add(f"{rec.get('act')}/{rec.get('section')}")
    return done


def append_log(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def run_guard(paths: list[Path]) -> tuple[int, str]:
    """corpus_change_guard over the files we just changed. rc 1 == BLOCK."""
    rel = []
    for p in paths:
        try:
            rel.append(str(p.resolve().relative_to(REPO)))
        except ValueError:
            rel.append(str(p))
    proc = subprocess.run([sys.executable, str(SCRIPTS / "corpus_change_guard.py"),
                           "--paths", *rel, "--quiet-ok"],
                          capture_output=True, text=True, cwd=str(REPO))
    text = (proc.stdout + proc.stderr).strip()
    # The guard only looks at data/<act>/sections/*.md paths inside the repo.
    # A run that inspected 0 files is not a pass — say so rather than show a
    # green line over files nobody checked.
    if " 0 changed section file(s)" in text:
        return 1, text + ("\n*** guard inspected 0 files — the applied paths are "
                          "outside the repo corpus, so nothing was checked ***")
    return proc.returncode, text


# ── driver ──────────────────────────────────────────────────────────────────
def apply_run(act: str, root: Path, only: list[str] | None = None, limit: int | None = None,
              dry_run: bool = False, keep_going: bool = False, force: bool = False,
              log: Path | None = None, corpus_root: Path | None = None,
              guard: bool = True, out=sys.stdout) -> dict:
    root = STAGING.stage_root(root)
    statuses = STAGING.verify(root)          # one pass; verdicts are theirs
    done = load_log(log) if (log and not force) else set()

    if only:
        sections = list(only)
    else:
        sections = [k.split("/", 1)[1] for k in sorted(statuses)
                    if k.split("/", 1)[0] == act and statuses[k]["status"] == "READY"]
    if limit is not None:
        sections = sections[:limit]

    applied, skipped, refused, unchanged = [], [], [], 0
    for section in sections:
        key = f"{act}/{section}"
        if key in done:
            skipped.append(key)
            continue
        try:
            plan = plan_section(act, section, statuses.get(key), root, corpus_root)
        except ApplyError as exc:
            refused.append(str(exc))
            print(f"REFUSE {exc}", file=out)
            if not keep_going:
                break
            continue

        if not plan["changed"]:
            unchanged += 1
        if dry_run:
            print(f"WOULD  {key}  {plan['old_sha256'][:12]} -> {plan['new_sha256'][:12]}  "
                  f"{plan['size']}B{'' if plan['changed'] else '  (no byte change)'}  {plan['target']}",
                  file=out)
            applied.append(plan)
            continue

        atomic_write(plan["target"], plan["bytes"])
        rec = {"ts": _now(), "act": act, "section": section, "path": str(plan["target"]),
               "old_sha256": plan["old_sha256"], "new_sha256": plan["new_sha256"],
               "bytes": plan["size"], "verdict": plan["verdict"],
               "changed": plan["changed"], "applied": True}
        if log:
            append_log(log, rec)
        print(f"APPLY  {key}  {plan['old_sha256'][:12]} -> {plan['new_sha256'][:12]}  "
              f"{plan['size']}B", file=out)
        applied.append(plan)

    summary = {"act": act, "root": str(root), "dry_run": dry_run,
               "considered": len(sections), "applied": len(applied),
               "unchanged_bytes": unchanged, "skipped_already_applied": len(skipped),
               "refused": len(refused), "refusals": refused}

    if not dry_run and applied and guard:
        rc, text = run_guard([p["target"] for p in applied])
        summary["guard"] = {"returncode": rc, "verdict": "BLOCK" if rc else "OK",
                            "output": text}
        print(text, file=out)
        if rc:
            print("*** corpus_change_guard BLOCKED the applied files — "
                  "this batch is NOT safe to keep. ***", file=out)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--act", required=True)
    ap.add_argument("--staging-root")
    ap.add_argument("--corpus-root", help="re-root recorded corpus paths (throwaway copies/tests)")
    ap.add_argument("--only", help="comma-separated section ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-going", action="store_true", help="continue past a refusal")
    ap.add_argument("--force", action="store_true", help="ignore the log and re-apply")
    ap.add_argument("--log", help="append-only JSONL apply log")
    ap.add_argument("--no-guard", action="store_true", help="skip corpus_change_guard")
    ap.add_argument("--summary", help="write the run summary JSON here")
    args = ap.parse_args()

    try:
        summary = apply_run(
            args.act, args.staging_root,
            only=[s.strip() for s in args.only.split(",") if s.strip()] if args.only else None,
            limit=args.limit, dry_run=args.dry_run, keep_going=args.keep_going,
            force=args.force, log=Path(args.log) if args.log else None,
            corpus_root=Path(args.corpus_root) if args.corpus_root else None,
            guard=not args.no_guard)
    except STAGING.StagingError as exc:
        print(f"apply_reingest: {exc}", file=sys.stderr)
        return 2

    print(f"apply_reingest: {'would apply' if args.dry_run else 'applied'} {summary['applied']}"
          f"/{summary['considered']} — {summary['skipped_already_applied']} already applied, "
          f"{summary['refused']} refused, {summary['unchanged_bytes']} byte-identical")
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    if summary.get("guard", {}).get("returncode"):
        return 1
    return 1 if summary["refused"] and not args.keep_going else 0


if __name__ == "__main__":
    sys.exit(main())
