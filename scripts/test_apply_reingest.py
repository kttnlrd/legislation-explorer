#!/usr/bin/env python3
"""Tests for scripts/apply_reingest.py — stdlib unittest, temp dirs only.

Nothing here touches data/** or the real staging tree.  Every fixture builds a
throwaway corpus + a throwaway staging root and stages through the real
table_rebuild_staging module, so the verdicts under test are the live ones.

  /usr/bin/python3.12 scripts/test_apply_reingest.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AR = _load("apply_reingest")
STAGING = _load("table_rebuild_staging")

SRC_MD = """---
section: "82-150"
compilation_no: "266"
---

# 82-150  Limit on tax free amount

The amount is worked out under the formula.

| Amount | Years | Base |
| --- | --- | --- |
| 1 | 2 | 3 |
"""
OUT_MD = SRC_MD.replace("| 1 | 2 | 3 |", "| 1 | 2 | 3 |\n| 4 | 5 | 6 |")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Fixture:
    """A temp corpus + temp staging root with one staged section."""

    def __init__(self, tmp: Path, section="82-150", needs_review=False, out_text=OUT_MD):
        self.tmp = tmp
        self.act = "itaa-1997"
        self.section = section
        self.root = tmp / "stage"
        self.corpus = tmp / "data" / self.act / "sections" / "division-82"
        self.corpus.mkdir(parents=True, exist_ok=True)
        self.corpus_file = self.corpus / f"{section}.md"
        self.corpus_file.write_text(SRC_MD)
        cand = tmp / "cand" / f"{section}.md"
        cand.parent.mkdir(parents=True, exist_ok=True)
        cand.write_text(out_text)
        gate = tmp / f"gate-{section}.json"
        gate.write_text(json.dumps({"verdict": "ACCEPTED", "section": section,
                                    "needs_review": needs_review,
                                    "gates": {"R1_pdf_token_recall": {"pass": True}}}))
        self.report = STAGING.stage(self.act, section, self.corpus_file, cand,
                                    gate_report=gate, root=self.root, force=True)
        self.d = self.root / self.act / section

    def run(self, **kw):
        kw.setdefault("guard", False)
        kw.setdefault("keep_going", True)
        return AR.apply_run(self.act, self.root, **kw)


class ApplyReingestTest(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    # 1
    def test_dry_run_writes_nothing(self):
        f = Fixture(self.tmp)
        before = self.corpus_snapshot(f)
        s = f.run(dry_run=True, log=self.tmp / "log.jsonl")
        self.assertEqual(s["applied"], 1)
        self.assertEqual(before, self.corpus_snapshot(f))
        self.assertFalse((self.tmp / "log.jsonl").exists())

    # 2
    def test_ready_applies_byte_identical(self):
        f = Fixture(self.tmp)
        s = f.run(log=self.tmp / "log.jsonl")
        self.assertEqual(s["applied"], 1, s)
        self.assertEqual(f.corpus_file.read_bytes(), (f.d / "output.md").read_bytes())

    # 3
    def test_blocked_preserved_regions_refused(self):
        f = Fixture(self.tmp, needs_review=True)
        before = f.corpus_file.read_bytes()
        s = f.run(only=[f.section])
        self.assertEqual(s["applied"], 0)
        self.assertIn("preserved_regions", s["refusals"][0])
        self.assertEqual(before, f.corpus_file.read_bytes())

    # 4
    def test_tampered_staged_output_refused(self):
        f = Fixture(self.tmp)
        (f.d / "output.md").write_text(OUT_MD + "\nsmuggled\n")
        s = f.run(only=[f.section])
        self.assertEqual(s["applied"], 0)
        # staging itself calls this FAIL (tampered); either way it must not land
        self.assertRegex(s["refusals"][0], "tamper")
        self.assertEqual(f.corpus_file.read_text(), SRC_MD)

    # 5
    def test_corpus_moved_since_staging_refused(self):
        f = Fixture(self.tmp)
        f.corpus_file.write_text(SRC_MD + "\nsomeone edited this\n")
        s = f.run(only=[f.section])
        self.assertEqual(s["applied"], 0)
        self.assertIn("changed since staging", s["refusals"][0])

    # 6
    def test_review_pinned_to_other_hash_refused(self):
        f = Fixture(self.tmp, needs_review=True)          # risky -> needs review
        STAGING.review(f.act, f.section, by="test", root=f.root)
        self.assertEqual(STAGING.verify(f.root)[f"{f.act}/{f.section}"]["status"], "READY")
        rev = json.loads((f.d / "review.json").read_text())
        rev["output_sha256"] = "0" * 64
        (f.d / "review.json").write_text(json.dumps(rev))
        s = f.run(only=[f.section])
        self.assertEqual(s["applied"], 0)
        self.assertEqual(f.corpus_file.read_text(), SRC_MD)

    # 7
    def test_log_hashes_and_resume(self):
        f = Fixture(self.tmp)
        log = self.tmp / "log.jsonl"
        old = sha(f.corpus_file)
        new = sha(f.d / "output.md")
        f.run(log=log)
        rec = json.loads(log.read_text().splitlines()[0])
        self.assertEqual(rec["old_sha256"], old)
        self.assertEqual(rec["new_sha256"], new)
        self.assertEqual(rec["bytes"], (f.d / "output.md").stat().st_size)
        self.assertTrue(rec["changed"])
        s2 = f.run(log=log)
        self.assertEqual((s2["applied"], s2["skipped_already_applied"]), (0, 1))
        self.assertEqual(len(log.read_text().splitlines()), 1)

    # 8
    def test_interrupted_write_leaves_original_intact(self):
        f = Fixture(self.tmp)
        orig = f.corpus_file.read_bytes()
        real_replace = os.replace

        def boom(src, dst):
            raise KeyboardInterrupt("crash between fsync and replace")

        AR.os.replace = boom
        try:
            with self.assertRaises(KeyboardInterrupt):
                AR.atomic_write(f.corpus_file, b"half a file")
        finally:
            AR.os.replace = real_replace
        self.assertEqual(f.corpus_file.read_bytes(), orig)
        leftovers = [p.name for p in f.corpus.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_new_section_without_corpus_file_refused(self):
        f = Fixture(self.tmp)
        rep = json.loads((f.d / "report.json").read_text())
        rep["source_path"] = None
        (f.d / "report.json").write_text(json.dumps(rep))
        s = f.run(only=[f.section])
        self.assertEqual(s["applied"], 0)
        self.assertIn("new section", s["refusals"][0])

    # the applier's own tamper/review checks, independent of the staging
    # snapshot (which may be stale by the time we write)
    def test_plan_section_rechecks_tamper_and_review_pin(self):
        f = Fixture(self.tmp)
        ready = {"status": "READY", "risks": [], "gate": "ACCEPTED"}
        (f.d / "output.md").write_text(OUT_MD + "\nsmuggled\n")
        with self.assertRaisesRegex(AR.ApplyError, "tampered after staging"):
            AR.plan_section(f.act, f.section, ready, f.root)
        (f.d / "output.md").write_text(OUT_MD)
        (f.d / "review.json").write_text(json.dumps({"output_sha256": "0" * 64}))
        with self.assertRaisesRegex(AR.ApplyError, "stale approval"):
            AR.plan_section(f.act, f.section, ready, f.root)
        self.assertEqual(f.corpus_file.read_text(), SRC_MD)

    def corpus_snapshot(self, f) -> dict:
        return {str(p): sha(p) for p in sorted(f.corpus.rglob("*")) if p.is_file()}


if __name__ == "__main__":
    unittest.main(verbosity=2)
