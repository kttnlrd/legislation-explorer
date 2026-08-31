#!/usr/bin/env python3
"""FINAL DATA AUDIT — one entry point, one verdict.

Phases:
  1. INTEGRITY      — verify_data_integrity.py (structural gate: 0 critical)
  2. LAYER+CONTENT  — randomised_api_mcp_test.py (API -> MCP -> full-corpus
                      content scan; new date seed each run)
  3. PROD SUITE     — test_prod_v270.py (52 functional API checks)

Exit 0 only if ALL three pass. Findings sync to CDN tickets via phase 2.
"""
import random, re, subprocess, sys
from datetime import date

ROOT = "/home/harrison/legislation-explorer"
PY = sys.executable


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)


ok = True
results = []

# ── Phase 1: integrity gate ──
p1 = run([PY, "scripts/verify_data_integrity.py"])
r1 = "PASS" if "RESULT: PASS" in p1.stdout else "FAIL"
ok = ok and r1 == "PASS"
results.append(f"[1/3] INTEGRITY     : {r1}")

# ── Phase 2: layer + content (random seed each run; reproducible via --seed N) ──
seed = random.SystemRandom().randrange(10_000_000, 99_999_999)
p2 = run([PY, "scripts/randomised_api_mcp_test.py", "--seed", str(seed)])
m2 = re.search(r"TOTAL: (\d+) checks \| FAIL (\d+) \| FIND (\d+)", p2.stdout)
if m2 and p2.returncode == 0:
    checks, fails, finds = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    phase2 = f"(seed={seed}) {checks} checks | FAIL {fails} | FIND {finds}"
    ok = ok and fails == 0
else:
    phase2 = f"(seed={seed}) RUN FAILED (no summary)"
    ok = False
results.append(f"[2/3] LAYER+CONTENT : {phase2}")

# ── Phase 3: prod suite ──
p3 = run([PY, "backend/tests/test_prod_v270.py"])
m3 = re.search(r"✅ (\d+) passed", p3.stdout)
m3f = re.search(r"❌ (\d+) failed", p3.stdout)
passed = int(m3.group(1)) if m3 else 0
failed = int(m3f.group(1)) if m3f else 1
ok = ok and failed == 0
results.append(f"[3/3] PROD SUITE    : {passed}/{passed + failed} passed")

print("═══ FINAL DATA AUDIT ═══")
for r in results:
    print(r)
print(f"═══ VERDICT: {'PASS' if ok else 'FAIL'} ═══")
sys.exit(0 if ok else 1)
