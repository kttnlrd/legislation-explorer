#!/usr/bin/env python3
"""FINAL DATA AUDIT — one entry point, one verdict.

Phases:
  1. INTEGRITY      — verify_data_integrity.py (structural gate: 0 critical)
  2. LAYER+CONTENT  — randomised_api_mcp_test.py (API -> MCP -> full-corpus
                      content scan; new date seed each run)
  3. PROD SUITE     — test_prod_v270.py (52 functional API checks)

Exit 0 only if ALL three pass. Findings sync to CDN tickets via phase 2.
"""
import os, random, re, subprocess, sys
from datetime import date

ROOT = "/home/harrison/legislation-explorer"

# Audit the app with the interpreter the APP runs under (systemd ExecStart uses
# /usr/bin/python3.12). Phases 2-3 import backend modules; the cron wrapper is
# launched by the Hermes venv python, which has no psycopg2/psycopg2.extras —
# running the prod suite under sys.executable crashed with ModuleNotFoundError
# and reported a meaningless "0/1 passed" (CDN-0191-era misdiagnosis, 2026-09-10).
PY = "/usr/bin/python3.12" if os.path.exists("/usr/bin/python3.12") else sys.executable


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)


def why(p):
    """Last meaningful line of a crashed phase, so the verdict names the cause
    instead of a bare 0/1 (a traceback used to read as 'PROD SUITE: 0/1')."""
    lines = [l.strip() for l in ((p.stdout or "") + "\n" + (p.stderr or "")).splitlines() if l.strip()]
    return lines[-1][:160] if lines else f"no output (exit {p.returncode})"


ok = True
results = []

# ── Phase 1: integrity gate ──
p1 = run([PY, "scripts/verify_data_integrity.py"])
pass1 = "RESULT: PASS" in p1.stdout
ok = ok and pass1
results.append(f"[1/3] INTEGRITY     : {'PASS' if pass1 else f'FAIL ({why(p1)})'}")

# ── Phase 2: layer + content (random seed each run; reproducible via --seed N) ──
seed = random.SystemRandom().randrange(10_000_000, 99_999_999)
p2 = run([PY, "scripts/randomised_api_mcp_test.py", "--seed", str(seed)])
m2 = re.search(r"TOTAL: (\d+) checks \| FAIL (\d+) \| FIND (\d+)", p2.stdout)
if m2 and p2.returncode == 0:
    checks, fails, finds = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    phase2 = f"(seed={seed}) {checks} checks | FAIL {fails} | FIND {finds}"
    ok = ok and fails == 0
else:
    phase2 = f"(seed={seed}) RUN FAILED (exit {p2.returncode}: {why(p2)})"
    ok = False
results.append(f"[2/3] LAYER+CONTENT : {phase2}")

# ── Phase 3: prod suite ──
p3 = run([PY, "backend/tests/test_prod_v270.py"])
m3 = re.search(r"✅ (\d+) passed", p3.stdout)
m3f = re.search(r"❌ (\d+) failed", p3.stdout)
if m3:
    passed = int(m3.group(1))
    failed = int(m3f.group(1)) if m3f else 0
    ok = ok and failed == 0
    results.append(f"[3/3] PROD SUITE    : {passed}/{passed + failed} passed")
else:
    ok = False
    results.append(f"[3/3] PROD SUITE    : RUN FAILED (exit {p3.returncode}: {why(p3)})")

print("═══ FINAL DATA AUDIT ═══")
for r in results:
    print(r)
print(f"═══ VERDICT: {'PASS' if ok else 'FAIL'} ═══")
sys.exit(0 if ok else 1)
