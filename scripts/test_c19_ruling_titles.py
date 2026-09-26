#!/usr/bin/env python3.12
"""C19 (CDN-0204) must flag the three fragment shapes and clear a whole title.

The ticket's population is the SERVED title list (data_loader.load_rulings), so the decision is
split into title_fragment_reason() and this test drives that same function with planted titles;
scan_ruling_title_fragments(titles=...) is the seam the live scan uses with the served list.

At HEAD the live scan reports 26 fragments - the plan's TARGET, not the 273 it measured, because
the 0204 extractor (_wrapped_title / _best_authoritative / _is_title_truncation) landed in
3b715b745. This test therefore does NOT assert a corpus count (that would fail the day the last
26 are repaired); it asserts the rule, and the live count is reported by the nightly.

Run: /usr/bin/python3.12 scripts/test_c19_ruling_titles.py      (exit 1 on any failure)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import scan_corpus_error_classes as S  # noqa: E402

# (citation, title, expected_to_fire) - the fragments are verbatim from the 26 the live scan
# reports at HEAD; the whole titles are served titles that must never be flagged.
CASES = [
    ("ATOID_2002_942", "ogroup ratio test", True),
    ("ATOID_2003_973", "ogroup ratio test", True),
    ("ATOID_2006_258", "(b)any net capital loss that is made in an income year", True),
    ("ATOID_2004_967", "Interaction between Division 7A of the", True),
    ("TR_2023_2", "Income tax: application of paragraph 8-1(2)(a) of the Income Tax Assessment "
                  "Act 1997 to labour costs related to the construction or creation of capital assets", False),
    ("TD_2019_6", "Deductions for prepaid expenditure payments", False),
    ("CR_2017_74", "Private rulings: whether a payment is deductible under section 8-1", False),
    ("GSTR_2000_20W", "GST and cancellation of supplies", False),
]

failures = 0


def check(ok: bool, label: str):
    global failures
    failures += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")


for citation, title, expect in CASES:
    why = S.title_fragment_reason(title)
    fired = why is not None
    check(fired == expect,
          f"{citation:16s} fired={fired} expected={expect} :: {why or 'whole title'}")

S.findings.clear()
S.scan_ruling_title_fragments(titles=[(c, t) for c, t, _ in CASES])
flagged = {f["path"].rsplit("/", 1)[-1] for f in S.findings}
expected_flagged = {c for c, _, e in CASES if e}
check(flagged == expected_flagged,
      f"the detector flags exactly the planted fragments -> {sorted(flagged)}")
check(all("data/rulings/" in f["path"] for f in S.findings),
      "findings are located by citation under data/rulings/")
check(len(S.findings) == len(expected_flagged),
      f"one finding per fragment, no duplicates (got {len(S.findings)})")

# an empty title is a finding too: it is the shape a failed extraction leaves
check(S.title_fragment_reason("") == "empty title" and S.title_fragment_reason(None) == "empty title",
      "an empty/None title is reported rather than silently passed")

print("PASS" if not failures else f"{failures} FAILURE(S)")
sys.exit(1 if failures else 0)
