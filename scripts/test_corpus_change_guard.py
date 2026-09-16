#!/usr/bin/env python3
"""Tests for corpus_change_guard: it must fail the 82-150 corruption shapes and
pass a legitimate compilation update.  Pure stdlib unittest (no pytest in repo).

    /usr/bin/python3.12 scripts/test_corpus_change_guard.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_s = importlib.util.spec_from_file_location("corpus_change_guard",
                                            SCRIPTS / "corpus_change_guard.py")
G = importlib.util.module_from_spec(_s)
_s.loader.exec_module(G)

FM = """---
act: "ITAA 1997"
section: "82-150"
compilation_no: {comp}
---
# 82-150  What is an invalidity segment?

"""

PROSE = ("**(1)** An *employment termination payment includes an invalidity segment if "
         "the payment was made to a person because he or she stops being *gainfully "
         "employed, and the person stopped being gainfully employed because he or she "
         "suffered from ill-health, and the gainful employment stopped before the "
         "person's *last retirement day, and 2 legally qualified medical practitioners "
         "have certified that it is unlikely that the person can ever be gainfully "
         "employed in a capacity for which he or she is reasonably qualified.\n")

GOOD_TABLE = """**Value of trading stock**

| Item | For this situation: | See: |
| --- | --- | --- |
| 1 | In working out attributable income of a non-resident trust estate | Section 102AAY |
| 2 | In working out attributable income of a controlled foreign corporation | Section 397 |

"""


def f(*parts, comp=265):
    return FM.format(comp=comp) + "".join(parts)


class GuardTest(unittest.TestCase):
    maxDiff = None

    def check(self, old, new, name="data/itaa-1997/sections/part-2-40/division-82/82-150.md"):
        r = G.check_file(old, new, name)
        print(f"\n  {r['status']:5} {name}")
        for why in r["reasons"]:
            print(f"        {why}")
        return r

    def test_1_real_82_150_shape(self):
        """Formula ingested as a 3-cell table with the 'where:' prose sucked in."""
        old = f(PROSE, "**(2)** Work out the amount of the invalidity segment by applying "
                       "the formula: termination payment x days to retirement / employment days.\n"
                       "where: days to retirement is the number of days from the day on which "
                       "the person's employment was terminated to the *last retirement day. "
                       "employment days is the number of days of employment to which the "
                       "payment relates.\n")
        new = f(PROSE, "**(2)** Work out the amount of the invalidity segment by applying the\n\n"
                       "| termination payment | Employment | Days to |\n"
                       "| --- | --- | --- |\n"
                       " where: days to retirement is the number of days from the day on which "
                       "the person's employment was terminated to the *last retirement day.\n",
                comp=266)
        self.assertEqual("BLOCK", self.check(old, new)["status"])

    def test_2_legitimate_compilation_update(self):
        """Prose amended, a real table row added, separator present."""
        old = f(PROSE, GOOD_TABLE)
        # an amendment that adds words: no prose token is lost, so no G-B warning
        new = f(PROSE.replace("reasonably qualified.", "reasonably qualified by education, experience or training."),
                GOOD_TABLE.rstrip("\n") +
                "| 3 | Some anti-avoidance provisions reduce the cost of an item | Subsection 52A(7) |\n\n",
                comp=266)
        self.assertEqual("OK", self.check(old, new, "data/itaa-1997/sections/part-2-25/division-70/70-45.md")["status"])

    def test_3_prose_converted_to_rows(self):
        """Non-pipe content collapses >40% while pipe content grows."""
        old = f(PROSE * 3)
        new = f(PROSE,
                "| a | b | c |\n| --- | --- | --- |\n"
                "| the payment was made to a person because he | or she stops being | gainfully employed |\n"
                "| the person stopped being gainfully employed | because he or she | suffered ill-health |\n\n",
                comp=266)
        r = self.check(old, new)
        self.assertEqual("BLOCK", r["status"])
        self.assertTrue(any("G-B" in x and "[BLOCK]" in x for x in r["reasons"]), r["reasons"])

    def test_4_formula_glyph_in_new_row(self):
        old = f(PROSE, GOOD_TABLE)
        new = f(PROSE, GOOD_TABLE.replace("| 2 | In working out", "| 2 | ç In working out"), comp=266)
        r = self.check(old, new)
        self.assertEqual("BLOCK", r["status"])
        self.assertTrue(any("glyph" in x for x in r["reasons"]), r["reasons"])

    def test_5_unrelated_prose_edit(self):
        old = f(PROSE)
        new = f(PROSE.replace("ill-health", "ill health"), comp=266)
        r = self.check(old, new)
        self.assertIn(r["status"], ("OK", "WARN"))
        self.assertNotEqual("BLOCK", r["status"])

    def test_6_cli_exit_codes(self):
        """The CLI must exit 1 on a BLOCK file and 0 on a clean one, via --paths."""
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "data" / "itaa-1997" / "sections"
            d.mkdir(parents=True)
            bad, good = d / "bad.md", d / "good.md"
            bad.write_text(f(PROSE, "**(2)** Work out the amount by applying the\n\n"
                                    "| termination payment | Employment | Days to |\n"
                                    "| --- | --- | --- |\n where: days to retirement is the number of days.\n"))
            good.write_text(f(PROSE, GOOD_TABLE))
            for path, want in ((bad, 1), (good, 0)):
                p = subprocess.run([sys.executable, str(SCRIPTS / "corpus_change_guard.py"),
                                    "--paths", str(path)], capture_output=True, text=True, cwd=td)
                print(f"\n  exit {p.returncode} (want {want}) for {path.name}")
                print("      " + p.stdout.strip().replace("\n", "\n      "))
                self.assertEqual(want, p.returncode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
