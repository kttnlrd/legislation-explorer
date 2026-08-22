#!/usr/bin/env python3
"""Check ATO website for new and amended rulings.

Uses the same sequential enumeration pattern as bulk_scrape_rulings.py
but only for the current and previous year (fast monthly check).
Detects new rulings (not on disk) and amended rulings (content hash changed).

Outputs JSON to stdout with change log.

Usage:
  python3 scripts/check_ruling_updates.py
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from curl_cffi import requests as curl

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("check_rulings")

RULINGS_DIR = Path("/home/harrison/legislation-explorer/data/rulings")
RULINGS_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
DELAY = 0.5  # seconds between requests
MAX_MISSES = 5  # consecutive 404s before giving up on a year

# Ruling types to check (only current + last year)
# Same DocID format as bulk_scrape_rulings.py
TYPES = {
    "TR":   {"code": "TXR/TR",  "year": "pre2000"},
    "TD":   {"code": "TXD/TD",  "year": "4digit"},
    "PCG":  {"code": "COG/PCG", "year": "4digit"},
    "LCG":  {"code": "COG/LCG", "year": "4digit"},
    "GSTR": {"code": "GST/GSTR","year": "4digit"},
    "PS_LA":{"code": "PSR/PS",  "year": "4digit"},
    "TA":   {"code": "TPA/TA",  "year": "4digit"},
    "MT":   {"code": "MXR/MT",  "year": "4digit"},
    "SGR":  {"code": "SGR/SGR", "year": "4digit"},
    "CR":   {"code": "CLR/CR",  "year": "4digit"},
    "PR":   {"code": "PRR/PR",  "year": "4digit"},
}


def build_url(rtype: str, cfg: dict, year: int, num: int) -> str:
    """Build the ATO print view URL for a given ruling."""
    code = cfg["code"]
    year_mode = cfg["year"]
    if year_mode == "pre2000":
        yr = year % 100 if year < 2000 else year
    else:
        yr = year
    docid = f"{code}{yr}{num}"
    return f"https://www.ato.gov.au/law/view/print?DocID={docid}/NAT/ATO/00001"


def fetch_ruling(url: str) -> tuple[str, str] | None:
    """Fetch a ruling. Returns (normalised text, title) or None if not found."""
    try:
        r = curl.get(url, impersonate="chrome120", headers=HEADERS, timeout=20, verify=False)
    except Exception as e:
        log.warning("Request error %s: %s", url, e)
        return None
    if r.status_code != 200:
        return None
    # Title: the ATO print view renders the ruling title in an <h3> directly
    # after the <h2> citation. Fallbacks: og:title / DC.Title meta, then <title>
    # minus the "| Legal database" suffix (added 2026 page template change).
    title = extract_title(r.text)
    if not title:
        return None
    text = normalize_ruling_text(r.text)
    if len(text) < 100:
        return None
    return (text, title)


def extract_title(page_html: str) -> str:
    """Extract the ruling title from the ATO print view HTML.

    New template (2026): <h2>TR 2026/1</h2> immediately followed by
    <h3>The actual ruling title</h3>. The <title> tag now just says
    "TR 2026/1 | Legal database", which is useless.
    """
    m = re.search(r"<h2[^>]*>\s*(TR|TD|PCG|LCG|GSTR|PS\s+LA|TA|MT|SGR|CR|PR)\s+\d{4}/\d+\s*</h2>\s*<h3[^>]*>(.*?)</h3>", page_html, re.I | re.S)
    if m:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
    # Fallback 1: og:title / DC.Title meta
    m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:title|DC\.Title)["\'][^>]*content=["\']([^"\']+)', page_html, re.I)
    if m:
        return re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    # Fallback 2: <title> tag minus "| Legal database"
    m = re.search(r"<title>(.*?)</title>", page_html, re.I | re.S)
    if m:
        t = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
        return re.sub(r"\s*\|\s*Legal database\s*$", "", t)
    return ""


def normalize_ruling_text(text: str) -> str:
    """Normalise raw HTML/text to a canonical body for title checks and hashing.

    Anchors the body at 'What this Ruling is about' (present in every ruling)
    so page chrome, the logo, and navigation never enter the comparison.
    html.unescape handles the &bull; &ndash; &mdash; entities the 2026 ATO
    template introduced.
    """
    t = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"\s+", " ", t)
    # Anchor: only the substantive ruling body matters for change detection
    i = t.find("What this Ruling is about")
    if i != -1:
        t = t[i:]
    # Cut trailing boilerplate
    for marker in ("Copyright notice", "Our commitment to your privacy", "Feedback about this page"):
        j = t.find(marker)
        if j != -1:
            t = t[:j]
    return t.strip()


def content_hash(text: str) -> str:
    """SHA-256 of the first 2000 chars of the canonical body.

    Both local (already artifact-cleaned) and remote (raw HTML) pass through
    normalize_ruling_text before hashing, so formatting noise (HTML entities,
    whitespace, nav chrome) never produces phantom amendments.
    """
    return hashlib.sha256(text[:2000].encode()).hexdigest()[:16]


def rtype_filename(rtype: str, year: int, num: int) -> str:
    """Build the filename for a ruling on disk."""
    safe = rtype.replace(" ", "_")
    return f"{safe}_{year}_{num}.txt"


def get_existing_rulings() -> dict[str, dict]:
    """Scan disk for existing rulings. Returns {filename: {type, year, num, hash}}."""
    existing = {}
    for f in RULINGS_DIR.glob("*.txt"):
        if not f.name.endswith(".txt"):
            continue
        # Skip meta files and non-ruling files
        if f.name.count("_") < 2:
            continue
        # Try to extract type, year, num from filename
        parts = f.stem.split("_")
        if len(parts) >= 3:
            rtype = parts[0]
            # Check if PS_LA (has underscore in type name)
            if parts[0] == "PS" and parts[1] == "LA":
                rtype = "PS_LA"
                parts = parts[1:]
            try:
                year = int(parts[-2])
                num = int(parts[-1])
            except (ValueError, IndexError):
                continue
            content = f.read_text(encoding="utf-8", errors="replace")
            existing[f.name] = {
                "type": rtype,
                "year": year,
                "num": num,
                "hash": content_hash(normalize_ruling_text(content)),
                "path": str(f),
            }
    return existing


def check_ruling_type(
    rtype: str,
    cfg: dict,
    year: int,
    existing: dict[str, dict],
) -> dict:
    """Check a single ruling type for a single year. Returns change log."""
    new_rulings = []
    amended_rulings = []
    errors = []
    stats = {"checked": 0, "new": 0, "amended": 0, "errors": 0}

    misses = 0
    num = 1
    while misses < MAX_MISSES:
        url = build_url(rtype, cfg, year, num)
        result = fetch_ruling(url)
        if result is None:
            misses += 1
            num += 1
            continue

        text, title = result
        h = content_hash(text)
        fname = rtype_filename(rtype, year, num)
        stats["checked"] += 1

        if fname not in existing:
            stats["new"] += 1
            new_rulings.append({
                "type": rtype, "year": year, "num": num,
                "title": title[:200], "hash": h,
            })
        elif existing[fname]["hash"] != h:
            stats["amended"] += 1
            amended_rulings.append({
                "type": rtype, "year": year, "num": num,
                "title": title[:200],
                "old_hash": existing[fname]["hash"],
                "new_hash": h,
            })

        misses = 0
        num += 1
        time.sleep(DELAY)

    return {
        "type": rtype,
        "year": year,
        "new": new_rulings,
        "amended": amended_rulings,
        "errors": errors,
        "stats": stats,
    }


def main():
    t0 = time.time()
    current_year = datetime.now().year
    years_to_check = {current_year, current_year - 1}

    # Build existing index once
    existing = get_existing_rulings()
    total_existing = len(existing)
    log.info("Existing rulings on disk: %d", total_existing)

    results = []
    total_new = 0
    total_amended = 0
    total_checked = 0

    for rtype, cfg in sorted(TYPES.items()):
        for year in sorted(years_to_check):
            r = check_ruling_type(rtype, cfg, year, existing)
            results.append(r)
            total_new += r["stats"]["new"]
            total_amended += r["stats"]["amended"]
            total_checked += r["stats"]["checked"]

    output = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(time.time() - t0, 2),
        "existing_on_disk": total_existing,
        "years_checked": sorted(years_to_check),
        "total_checked": total_checked,
        "total_new_rulings": total_new,
        "total_amended_rulings": total_amended,
        "results": results,
        "summary": {
            "new_by_type": {r["type"]: r["stats"]["new"] for r in results if r["stats"]["new"]},
            "amended_by_type": {r["type"]: r["stats"]["amended"] for r in results if r["stats"]["amended"]},
        },
    }
    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()