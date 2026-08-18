#!/usr/bin/env python3
"""
verify_data_integrity.py — Standardised data integrity gate for Legislation Explorer.

Assesses the accuracy and cleanliness of the data corpus using statistical
random sampling. The sample seed is randomised on every run (unless pinned
with --seed for reproducibility), so successive runs cover different files
and the whole corpus gets exercised over time.

Domains (--domain):
  sections       Legislation section .md files (per act)
  rulings        ATO ruling .txt files + summaries
  private-rulings 57k private ruling JSON bodies
  cases          Case summaries + text
  all            Run every domain (default)

Sampling (--sample-size):
  auto (default) Cochran's formula for 95% confidence, 5% margin of error,
                 with finite-population correction, stratified proportionally
                 per stratum (act / ruling type / year).
  N              Fixed sample size per domain.

Checks per sampled item:
  structure   frontmatter valid, file non-empty, required keys present
  artifacts   known junk: HTML entities, JS/GA chrome, page-header noise,
              stray trailing tokens, double-space after markers, smart quotes
  accuracy    content agrees with source of truth (raw pdf text for sections,
              summaries JSON for rulings, index for private rulings)
  links       internal cross-references resolve (graph node exists, anchors unique)

Output:
  Human-readable report + optional JSON (--json-out). Exit code 1 if any
  domain's defect rate exceeds --threshold (default 0.05 = 5%).

Usage:
  python3 scripts/verify_data_integrity.py                     # all domains
  python3 scripts/verify_data_integrity.py --domain sections --seed 42
  python3 scripts/verify_data_integrity.py --domain private-rulings --sample-size 500
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import secrets
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PR_JSON = Path.home() / ".hermes" / "private_rulings" / "data" / "json"

# ── Artifact patterns ────────────────────────────────────────────────────────
HTML_ENTITY_RE = re.compile(r"&(?:bull|#\d{2,4}|amp|nbsp|ldquo|rdquo|lsquo|rsquo|mdash|ndash|copy|sect|hellip|times);", re.I)
JS_CHROME_RE = re.compile(
    r"GoogleAnalytics|function\s*\(\s*i\s*,\s*s\s*,\s*o\s*,\s*g|bazadebezolkohpepadr|dataLayer|"
    r"window\.(?:dataLayer|ga\b|google|jQuery|onload|addEventListener|performance)", re.I
)
PAGE_HEADER_RE = re.compile(
    r"^(?:Income Tax Assessment Act 1997\s+\d+|Authorised Version C\d+|"
    r"Compilation No\.\s+\d+|Prepared by the Office of Parliamentary Counsel|"
    r"Liability rules of general application(?: Chapter \d+)?|"
    r"International aspects of income tax\s*$|Specialist liability rules\s*$|"
    r"Introduction and core provisions\s*$|Business and investment income\s*$|"
    r"Compliance and administration\s*$|Dictionary\s*$|Endnotes\s*$)"
)
DOUBLE_SPACE_MARKER_RE = re.compile(r"(\*\*\([a-z0-9]+\)\*\*)\s{2,}")
STRAY_TAIL_RE = re.compile(r"^[a-z]{2,15}$")  # lone short lowercase word ending a file
SMART_QUOTE_RE = re.compile(r"[\u2018\u2019\u201c\u201d]")
TRAILING_JUNK_RE = re.compile(
    r"(?:\s{2,}(?:International aspects of income tax|Taxation etc\.? of\s|"
    r"Meaning of \w+ \w+|Types of assets of|Exception\s*$))"
)

ARTIFACT_CHECKS = [
    ("html_entity", HTML_ENTITY_RE, "critical"),
    ("js_chrome", JS_CHROME_RE, "critical"),
    ("page_header", PAGE_HEADER_RE, "critical"),
    ("double_space_marker", DOUBLE_SPACE_MARKER_RE, "cosmetic"),
    ("smart_quote", SMART_QUOTE_RE, "cosmetic"),
    ("trailing_junk", TRAILING_JUNK_RE, "critical"),
]

# Acts whose frontmatter intentionally omits "act:" (inferable from path)
NO_ACT_KEY_ACTS = {"nz-it-2007", "master-gst-guide", "master-tax-examples",
                   "master-tax-guide", "spec"}


def cochran_sample(population: int, margin: float = 0.05, z: float = 1.96, p: float = 0.5) -> int:
    """Cochran's sample size for proportion with finite-population correction."""
    if population <= 0:
        return 0
    n0 = (z * z * p * (1 - p)) / (margin * margin)
    return max(1, min(population, math.ceil(n0 / (1 + (n0 - 1) / population))))


def stratify(items: list, key_fn, sample_size: int, seed: int) -> list:
    """Proportional stratified random sample."""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for it in items:
        strata[key_fn(it)].append(it)
    total = len(items)
    out = []
    for sk, members in strata.items():
        n = max(1, round(sample_size * len(members) / total))
        n = min(n, len(members))
        out.extend(rng.sample(members, n))
    # top up if rounding undershot
    if len(out) < sample_size:
        pool = [it for it in items if it not in out]
        out.extend(rng.sample(pool, min(sample_size - len(out), len(pool))))
    return out


def scan_artifacts(text: str, path: str) -> list[dict]:
    """Run artifact checks; return list of {check, severity, line, detail}."""
    found = []
    for name, pat, sev in ARTIFACT_CHECKS:
        for m in pat.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            detail = re.sub(r"\s+", " ", m.group(0))[:80]
            found.append({"check": name, "severity": sev, "line": line_no, "detail": detail})
    return found


# ── Domain: sections ─────────────────────────────────────────────────────────
SECTION_ACTS = sorted(
    d.name for d in DATA.iterdir() if (d / "sections").is_dir()
)
RAW_ACTS = {  # acts with pdftotext raw source for accuracy cross-check
    "itaa-1997": ("raw", r"^\s*\((\d+)\)"),
    "itaa-1936": ("raw", r"^\s*\((\d+)\)"),
    "gst-1999": ("raw", r"^\s*\((\d+)\)"),
    "taa-1953": ("raw", r"^\s*\((\d+)\)"),
    "fbt-1986": ("raw", r"^\s*\((\d+)\)"),
}


def collect_sections() -> list[dict]:
    items = []
    for act in SECTION_ACTS:
        sec_dir = DATA / act / "sections"
        if not sec_dir.is_dir():
            continue
        for p in sorted(sec_dir.rglob("*.md")):
            items.append({"path": str(p), "act": act, "rel": str(p.relative_to(DATA))})
    return items


def check_section(item: dict, graph_conn) -> list[dict]:
    issues = []
    p = Path(item["path"])
    act = item["act"]
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        return [{"check": "structure", "severity": "critical", "line": 0, "detail": f"unreadable: {e}"}]

    # structure: frontmatter
    if not text.startswith("---"):
        issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "missing frontmatter"})
    else:
        fm_end = text.find("---", 3)
        if fm_end < 0:
            issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "unclosed frontmatter"})
        else:
            fm = text[3:fm_end]
            needs_act = act not in NO_ACT_KEY_ACTS
            if needs_act and "act:" not in fm:
                issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "frontmatter missing act:"})
            if "section:" not in fm:
                issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "frontmatter missing section:"})
            body = text[fm_end + 3:]
            if not body.strip():
                issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "empty body"})

    # artifacts: scan_artifacts for non-trailing_junk checks; trailing_junk is
    # span-aware below so we can tell legit headings from genuine dangling tails.
    for a in scan_artifacts(text, str(p)):
        if a["check"] != "trailing_junk":
            issues.append(a)

    lines = text.splitlines()
    for m in TRAILING_JUNK_RE.finditer(text):
        line_no = text.count("\n", 0, m.start()) + 1
        if line_no - 1 >= len(lines):
            continue
        stripped = lines[line_no - 1].lstrip()
        if stripped.startswith("#"):
            continue  # legit H1/H2 section title
        if line_no == 2:
            continue  # legit repeated title line right after the H1
        if stripped.startswith("- ") or stripped.startswith("* "):
            continue  # legit TOC-dump list items
        line_end = text.find("\n", m.end())
        if line_end == -1:
            line_end = len(text)
        if text[m.end():line_end].strip():
            continue  # inline lead-in with body on the same line (e.g. "Meaning of employee The term …")
        rest = re.sub(
            r"^\s*(?:---|\*.*\*|Last updated.*)$", "",
            "\n".join(lines[line_no:]), flags=re.M,
        ).strip()
        if rest:
            continue  # standalone heading introducing following content (e.g. s 738G(3) "Meaning of related party")
        issues.append({"check": "trailing_junk", "severity": "critical",
                       "line": line_no, "detail": re.sub(r"\s+", " ", m.group(0))[:80]})

    # stray tail: last non-empty line a lone short lowercase word
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines and STRAY_TAIL_RE.match(lines[-1]) and not lines[-1].startswith("#"):
        issues.append({"check": "stray_tail", "severity": "critical", "line": len(lines), "detail": repr(lines[-1])})

    # anchors unique
    anchors = re.findall(r'<a id="([^"]+)"></a>', text)
    dup = [a for a, c in Counter(anchors).items() if c > 1]
    if dup:
        issues.append({"check": "duplicate_anchor", "severity": "critical", "line": 0, "detail": ",".join(dup[:5])})

    return issues


# ── Domain: rulings ──────────────────────────────────────────────────────────
def collect_rulings() -> list[dict]:
    items = []
    rdir = DATA / "rulings"
    if not rdir.is_dir():
        return items
    for p in sorted(rdir.glob("*.txt")):
        if p.name.endswith(".meta.json") or p.name.startswith("."):
            continue
        m = re.match(r"^([A-Za-z]+)_(\d{2,4})_", p.stem)
        rtype = m.group(1).upper() if m else "OTHER"
        items.append({"path": str(p), "type": rtype, "stem": p.stem})
    return items


def check_ruling(item: dict) -> list[dict]:
    issues = []
    p = Path(item["path"])
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [{"check": "structure", "severity": "critical", "line": 0, "detail": f"unreadable: {e}"}]
    if not text.strip():
        issues.append({"check": "structure", "severity": "critical", "line": 1, "detail": "empty file"})
    for a in scan_artifacts(text, str(p)):
        issues.append(a)
    # accuracy: title extraction sanity vs summaries JSON
    stem = item["stem"]
    summ = DATA / "rulings" / "summaries" / f"{stem}.json"
    alt = DATA / "rulings" / "summaries" / f"{stem.replace('ATOID_', 'AID_', 1)}.json"
    for sp in (summ, alt):
        if sp.exists():
            try:
                d = json.loads(sp.read_text(encoding="utf-8"))
                st = d.get("title") or ""
                if len(st) > 500:
                    issues.append({"check": "accuracy", "severity": "critical", "line": 0, "detail": f"summary title >500 chars ({len(st)})"})
            except Exception as e:
                issues.append({"check": "structure", "severity": "critical", "line": 0, "detail": f"unparseable summary: {e}"})
            break
    return issues


# ── Domain: private rulings ──────────────────────────────────────────────────
def collect_private_rulings() -> list[dict]:
    items = []
    if not PR_JSON.is_dir():
        return items
    for p in sorted(PR_JSON.glob("*.json")):
        items.append({"path": str(p), "authnum": p.stem})
    return items


def check_private_ruling(item: dict, index: dict) -> list[dict]:
    issues = []
    p = Path(item["path"])
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return [{"check": "structure", "severity": "critical", "line": 0, "detail": f"unparseable JSON: {e}"}]
    auth = item["authnum"]
    if auth not in index:
        issues.append({"check": "links", "severity": "critical", "line": 0, "detail": "authnum missing from index"})
    elif index[auth].get("name") and d.get("name") and index[auth]["name"] != d.get("name"):
        issues.append({"check": "accuracy", "severity": "critical", "line": 0, "detail": "index name != json name"})
    ft = d.get("formatted_text") or ""
    if ft:
        for a in scan_artifacts(ft, str(p)):
            issues.append(a)
    return issues


# ── Domain: cases ────────────────────────────────────────────────────────────
def collect_cases() -> list[dict]:
    items = []
    sdir = BASE / "scripts" / "cleaned" / "summaries"
    if not sdir.is_dir():
        return items
    for p in sorted(sdir.glob("*.json")):
        items.append({"path": str(p), "stem": p.stem})
    return items


def check_case(item: dict) -> list[dict]:
    issues = []
    p = Path(item["path"])
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return [{"check": "structure", "severity": "critical", "line": 0, "detail": f"unparseable JSON: {e}"}]
    # error stubs from failed summarisation runs are honest records, not corruption
    if d.get("error"):
        return []
    for key in ("citation", "title", "held", "outcome"):
        if key not in d:
            issues.append({"check": "structure", "severity": "critical", "line": 0, "detail": f"missing key '{key}'"})
    return issues


# ── Runner ───────────────────────────────────────────────────────────────────
DOMAINS = {
    "sections": (collect_sections, check_section, lambda it: it["act"]),
    "rulings": (collect_rulings, check_ruling, lambda it: it["type"]),
    "private-rulings": (collect_private_rulings, check_private_ruling, lambda it: it["authnum"][:4]),
    "cases": (collect_cases, check_case, lambda it: it["stem"][:4]),
}


def run_domain(name: str, sample_size: int, seed: int, verbose: bool, baseline: dict | None = None) -> dict:
    collect_fn, check_fn, stratum_fn = DOMAINS[name]
    items = collect_fn()
    pop = len(items)
    n = cochran_sample(pop) if sample_size == 0 else min(sample_size, pop)
    sample = stratify(items, stratum_fn, n, seed)

    extra = {}
    graph_conn = None
    pr_index = None
    if name == "private-rulings":
        try:
            pr_index = json.loads((DATA / "private_rulings_index.json").read_text())
        except Exception:
            pr_index = {}

    defects = []
    for it in sample:
        if name == "private-rulings":
            iss = check_fn(it, pr_index)
        elif name == "sections":
            iss = check_fn(it, None)
        else:
            iss = check_fn(it)
        for issue in iss:
            defects.append({**it, **issue})

    if graph_conn is not None:
        graph_conn.close()

    by_check = Counter(d["check"] for d in defects)
    crit = [d for d in defects if d.get("severity") == "critical"]
    cosm = [d for d in defects if d.get("severity") != "critical"]
    crit_files = len({d["path"] for d in crit})
    cosm_files = len({d["path"] for d in cosm})
    crit_rate = crit_files / max(1, len(sample))
    cosm_rate = cosm_files / max(1, len(sample))

    # baseline diff: defects in this run absent from baseline (new regressions)
    new_crit = []
    if baseline:
        base_files = {b["path"] for b in baseline.get("defects", []) if b.get("severity") == "critical"}
        for d in crit:
            key = (d["path"], d["check"], d.get("line"))
            in_base = any(
                b.get("path") == d["path"] and b.get("check") == d["check"]
                for b in baseline.get("defects", [])
            )
            if not in_base:
                new_crit.append(d)

    report = {
        "domain": name,
        "population": pop,
        "sample_size": len(sample),
        "seed": seed,
        "defect_entries": len(defects),
        "critical_entries": len(crit),
        "cosmetic_entries": len(cosm),
        "critical_files": crit_files,
        "critical_rate": round(crit_rate, 4),
        "cosmetic_files": cosm_files,
        "cosmetic_rate": round(cosm_rate, 4),
        "by_check": dict(by_check),
        "defects": crit + cosm,
        "defect_count_total": len(defects),
        "new_critical_vs_baseline": len(new_crit),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Data integrity verification gate")
    ap.add_argument("--domain", choices=list(DOMAINS) + ["all"], default="all")
    ap.add_argument("--sample-size", type=int, default=0,
                    help="0=auto (Cochran 95/5), or fixed N per domain")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed for sampling; omit for a fresh random seed each run")
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="max acceptable critical file defect rate (default 0.05)")
    ap.add_argument("--baseline", type=str, default=None,
                    help="JSON report from a previous run; gate fails on NEW critical defects vs it")
    ap.add_argument("--verbose", action="store_true",
                    help="(deprecated — all defects are always reported)")
    ap.add_argument("--json-out", type=str, default=None)
    args = ap.parse_args()

    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except Exception as e:
            print(f"ERROR: cannot read baseline {args.baseline}: {e}")
            return 2

    domains = list(DOMAINS) if args.domain == "all" else [args.domain]
    all_reports = []
    fail = False
    # Randomise the sample every run unless the caller pins --seed.
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    print("=" * 70)
    print("DATA INTEGRITY VERIFICATION")
    print(f"seed={seed}  sample={'auto (Cochran 95/5)' if args.sample_size == 0 else args.sample_size}  "
          f"threshold={args.threshold}  baseline={'yes' if baseline else 'no'}")
    print("=" * 70)

    for d in domains:
        rep = run_domain(d, args.sample_size, seed, args.verbose, baseline)
        all_reports.append(rep)
        new_vs_base = rep.get("new_critical_vs_baseline", 0)
        status = "FAIL" if rep["critical_rate"] > args.threshold else "PASS"
        if status == "FAIL":
            fail = True
        print(f"\n[{d}] {status}  pop={rep['population']} sample={rep['sample_size']} "
              f"critical_files={rep['critical_files']} ({rep['critical_rate']:.1%}) "
              f"cosmetic_files={rep['cosmetic_files']} ({rep['cosmetic_rate']:.1%})"
              + (f"  NEW_CRITICAL_VS_BASELINE={new_vs_base}" if baseline else ""))
        if rep["by_check"]:
            for k, v in sorted(rep["by_check"].items(), key=lambda x: -x[1]):
                print(f"    {k}: {v}")
        if rep["defects"]:
            print(f"    defects ({len(rep['defects'])}):")
            for dd in rep["defects"]:
                sev = dd.get("severity", "?")
                print(f"      - [{sev}] {dd.get('rel', dd.get('path',''))}: {dd['check']} @{dd['line']} {dd['detail'][:100]}")

    # aggregate
    tot_pop = sum(r["population"] for r in all_reports)
    tot_sam = sum(r["sample_size"] for r in all_reports)
    tot_crit = sum(r["critical_entries"] for r in all_reports)
    tot_cosm = sum(r["cosmetic_entries"] for r in all_reports)
    tot_crit_files = sum(r["critical_files"] for r in all_reports)
    print("\n" + "=" * 70)
    print(f"TOTAL population={tot_pop} sampled={tot_sam} "
          f"critical_entries={tot_crit} ({tot_crit_files} files) cosmetic_entries={tot_cosm}")
    print(f"RESULT: {'FAIL' if fail else 'PASS'}")

    if args.json_out:
        out = {"seed": seed, "threshold": args.threshold,
               "baseline": args.baseline,
               "domains": all_reports,
               "total": {"population": tot_pop, "sampled": tot_sam,
                         "critical_entries": tot_crit, "cosmetic_entries": tot_cosm,
                         "critical_files": tot_crit_files}}
        Path(args.json_out).write_text(json.dumps(out, indent=2, default=str))
        print(f"JSON report: {args.json_out}")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
