#!/usr/bin/env python3.12
"""Prove the operator credit works on REAL corpus sections, before anything is written.

For each chosen section it builds the proposal's text into a scratch directory (never the corpus)
and runs the gate three ways:

  A. proposed text + evidence   -> must be ACCEPTED   (the credit is spendable)
  B. proposed text, no evidence -> must be REJECTED   (R2: the operator is an invention)
  C. current text  + evidence   -> must be REJECTED   (R1: the page demands the operator)

If A is not ACCEPTED the proposal is not applicable; if B or C is ACCEPTED the credit proves
nothing, because either the operator was never needed or a gap is silently tolerated.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/harrison/legislation-explorer")
PROPOSAL = Path("/tmp/opres2/proposal.json")
SCRATCH = Path("/tmp/gate-test")


def build(section: str, fences: list[dict]) -> tuple[Path, str]:
    """Write the section's markdown with the proposal's lines applied; return (path, act)."""
    src = Path(fences[0]["file"])
    if not src.is_absolute():
        src = ROOT / src
    act = src.parts[src.parts.index("data") + 1]
    lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    applied = 0
    for fence in fences:
        for ln in fence.get("lines", []):
            if ln.get("status") != "change-needed" or ln.get("proposed") == ln.get("current"):
                continue
            cur, prop = ln["current"], ln["proposed"]
            for i, line in enumerate(lines):
                if line.rstrip("\n") == cur:
                    lines[i] = prop + "\n"
                    applied += 1
                    break
    out = SCRATCH / act / f"{section}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(lines), encoding="utf-8")
    return out, act


def gate(act: str, section: str, ingested: Path, pdf: Path, evidence: Path | None) -> tuple[str, str]:
    cmd = ["/usr/bin/python3.12", str(ROOT / "scripts" / "ingest_reingest_gate.py"),
           "--act", act, "--section", section, "--ingested", str(ingested), "--pdf", str(pdf)]
    if evidence:
        cmd += ["--operator-evidence", str(evidence)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=900)
    out = p.stdout + p.stderr
    verdict = "ACCEPTED" if "ACCEPTED" in out and "REJECTED" not in out else "REJECTED"
    failed = [l.strip() for l in out.splitlines() if "REJECTED" in l or "[FAIL" in l or " FAIL" in l]
    return verdict, (failed[0][:130] if failed else out.strip().splitlines()[-1][:130] if out.strip() else "")


def main() -> int:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    doc = json.loads(PROPOSAL.read_text())
    by_section: dict[str, list[dict]] = {}
    for f in doc["fences"]:
        if f.get("status") == "change-needed":
            by_section.setdefault(f["section"], []).append(f)

    wanted = sys.argv[1:] or ["4-15", "83-170", "705-115"]
    bad = 0
    for section in wanted:
        fences = by_section.get(section)
        if not fences:
            print(f"  [SKIP] {section}: no change-needed fence in the proposal")
            continue
        pdf = ROOT / "source" / fences[0]["file"].split("/")[1] / fences[0]["source"]
        if not pdf.exists():
            print(f"  [SKIP] {section}: no pdf at {pdf}")
            continue
        proposed, act = build(section, fences)
        current = Path(fences[0]["file"])
        if not current.is_absolute():
            current = ROOT / current
        chars = sorted({g["char"] for f in fences for g in f.get("glyphs", [])
                        if g.get("kind") == "operator"})
        print(f"== {act} {section}  (operators: {' '.join(chars)})  pdf={pdf.name}")

        vA, rA = gate(act, section, proposed, pdf, PROPOSAL)
        vB, rB = gate(act, section, proposed, pdf, None)
        vC, rC = gate(act, section, current, pdf, PROPOSAL)
        ok = vA == "ACCEPTED" and vB == "REJECTED" and vC == "REJECTED"
        bad += not ok
        for tag, v, r in (("A proposed + evidence ", vA, rA),
                          ("B proposed, no evidence", vB, rB),
                          ("C current  + evidence ", vC, rC)):
            print(f"   {'ok  ' if True else ''}{tag} -> {v}  {r}")
        print(f"   {'PASS' if ok else 'FAIL: the credit is not proven for this section'}")
    print()
    print("all sections proven" if not bad else f"{bad} section(s) not proven")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
