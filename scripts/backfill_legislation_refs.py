#!/usr/bin/env python3
"""Backfill missing legislation_refs for cases that have document content but no refs.

Reads case HTML from the documents table, extracts section references using
regex patterns, and inserts into case_legislation_refs. Idempotent.

Usage:
    python3 scripts/backfill_legislation_refs.py                  # backfill all missing
    python3 scripts/backfill_legislation_refs.py --citation "[2022] FCA 1487"  # one case
    python3 scripts/backfill_legislation_refs.py --dry-run        # report only
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_leg_refs")

SEP = "¶"

# ── Act patterns ──────────────────────────────────────────────────────────
ACTS = [
    ("Income Tax Assessment Act 1936", re.compile(r"ITAA\s+1936|Income Tax Assessment Act\s+1936", re.IGNORECASE)),
    ("Income Tax Assessment Act 1997", re.compile(r"ITAA\s+1997|Income Tax Assessment Act\s+1997", re.IGNORECASE)),
    ("Taxation Administration Act 1953", re.compile(r"TAA\s+1953|Taxation Administration Act\s+1953", re.IGNORECASE)),
    ("Fringe Benefits Tax Assessment Act 1986", re.compile(r"FBT[AA]?\s+1986|Fringe Benefits Tax( Assessment)? Act\s+1986", re.IGNORECASE)),
    ("A New Tax System (Goods and Services Tax) Act 1999", re.compile(r"GST Act|GST\s+1999|A New Tax System.*Goods and Services Tax.*Act\s+1999", re.IGNORECASE)),
    ("Corporations Act 2001", re.compile(r"Corporations Act\s+2001", re.IGNORECASE)),
    ("Federal Court of Australia Act 1976", re.compile(r"Federal Court of Australia Act\s+1976", re.IGNORECASE)),
]

SECTION_RE = re.compile(
    r'(?:(?:\b|^)(?:s\s*\.?\s*|section\s+)(\d+[A-Z]*(?:[-–]\d+[A-Z]*)*(?:\(\d+\))*(?:\([a-z]\))*)'
    r'|(?:\b|^)ss\s*\.?\s*(\d+[A-Z]*(?:\s*[,–\s]\s*\d+[A-Z]*)*))',
    re.IGNORECASE
)

# Clean AustLII chrome
CHROME_LINES = [
    "databases", "worldlii", "search", "feedback", "austlii", "noteup", "lawcite",
    "home", "database search", "name search", "recent decisions", "download", "help",
    "last updated", "you are here", "table of contents", "print", "email", "back to browse",
]


def sql(query: str, timeout: int = 30) -> list[list[str]]:
    r = subprocess.run(
        ["docker", "exec", "cadena-postgres", "psql", "-U", "postgres", "-d", "cadena_knowledge",
         "-t", "-F", SEP, "-A", "-c", query],
        capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        log.error("SQL error: %s", r.stderr[:300])
        return []
    rows = []
    for line in r.stdout.split("\n"):
        line = line.strip()
        if line:
            parts = line.split(SEP)
            if len(parts) >= 1 and parts[0].strip():
                rows.append(parts)
    return rows


def is_chrome(line: str) -> bool:
    t = line.strip().lower().rstrip(":.")
    return t in CHROME_LINES or len(t) < 3


def extract_refs(content: str, citation: str) -> list[dict]:
    """Extract legislation references from case HTML/text."""
    refs = []
    # Split into lines and group into rough paragraphs
    lines = content.split("\n")
    paragraphs = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped and current:
            paragraphs.append(" ".join(current))
            current = []
        elif stripped and not is_chrome(stripped):
            current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))

    for para_num, para_text in enumerate(paragraphs, 1):
        if len(para_text) < 30:
            continue

        # Find which acts are mentioned in this paragraph
        acts_found = set()
        for act_name, pattern in ACTS:
            if pattern.search(para_text):
                acts_found.add(act_name)

        # If no act found, default to ITAA 1997
        target_acts = acts_found if acts_found else {"Income Tax Assessment Act 1997"}

        # Scan for section references
        for m in SECTION_RE.finditer(para_text):
            raw = m.group(0).strip()

            context_start = max(0, m.start() - 80)
            context_end = min(len(para_text), m.end() + 80)
            ctx = para_text[context_start:context_end]

            # Handle ss multi-ref: "ss 23, 37AB, 37AE" → split into individual refs
            if raw.lower().startswith("ss"):
                secs = re.split(r'[,–\s]+', raw[2:].strip().lstrip('. '))
                for sec in secs:
                    if sec.strip():
                        for act_title in target_acts:
                            refs.append({
                                "act_title": act_title,
                                "section_reference": f"s.{sec.strip()}",
                                "context": ctx,
                                "paragraph_number": para_num,
                            })
                continue

            section_ref = raw
            # Normalise: s.116 → s.116, section 116 → s.116, s 116 → s.116
            if section_ref.lower().startswith("section "):
                section_ref = "s." + section_ref[8:]
            elif section_ref.lower().startswith("s"):
                num = re.sub(r'^s\s*\.?\s*', '', section_ref, flags=re.IGNORECASE)
                section_ref = "s." + num

            for act_title in target_acts:
                refs.append({
                    "act_title": act_title,
                    "section_reference": section_ref,
                    "context": ctx,
                    "paragraph_number": para_num,
                })

    # Deduplicate (same act + section per paragraph)
    seen = set()
    unique = []
    for r in refs:
        key = (r["act_title"], r["section_reference"], r["paragraph_number"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill missing legislation_refs")
    parser.add_argument("--citation", type=str, help="Backfill a specific case only")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no inserts")
    args = parser.parse_args()

    # Find cases with document content but no legislation_refs
    if args.citation:
        safe = args.citation.replace("'", "''")
        query = (
            f"SELECT c.id, c.citation "
            f"FROM cases c "
            f"JOIN documents d ON d.id = c.document_id "
            f"WHERE c.citation = '{safe}' "
            f"AND LENGTH(COALESCE(d.content, '')) > 100 "
            f"AND NOT EXISTS (SELECT 1 FROM case_legislation_refs lr WHERE lr.case_id = c.id) "
            f"LIMIT 1;"
        )
        log.info("Query: %s", query[:200])
        rows = sql(query)
    else:
        rows = sql(
            "SELECT c.id, c.citation, LEFT(d.content, 100) AS preview "
            "FROM cases c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE LENGTH(COALESCE(d.content, '')) > 100 "
            "AND NOT EXISTS (SELECT 1 FROM case_legislation_refs lr WHERE lr.case_id = c.id)"
        )

    log.info("Found %d cases missing legislation_refs", len(rows))

    if args.dry_run:
        for r in rows:
            log.info("  Would process: %s", r[1] if len(r) > 1 else "?")
        return

    total_inserted = 0
    for row in rows:
        case_id = row[0] if len(row) > 0 else None
        citation = row[1] if len(row) > 1 else "?"
        if not case_id:
            continue
        # Read full content
        safe = citation.replace("'", "''")
        cqr = subprocess.run(
            ["docker", "exec", "cadena-postgres", "psql", "-U", "postgres", "-d", "cadena_knowledge",
             "-t", "-A", "-c",
             f"SELECT content::text FROM documents "
             f"WHERE id = (SELECT document_id FROM cases WHERE citation = '{safe}') LIMIT 1;"],
            capture_output=True, text=True, timeout=30,
        )
        if cqr.returncode != 0 or not cqr.stdout.strip():
            log.warning("  No content for %s", citation)
            continue
        content = cqr.stdout.strip()

        refs = extract_refs(content, citation)
        if not refs:
            log.info("  %s: 0 refs found (skipping)", citation)
            continue

        # Insert one by one via docker exec
        for ref in refs:
            act = ref["act_title"].replace("'", "''")
            sec = ref["section_reference"].replace("'", "''")
            ctx = ref["context"].replace("'", "''")
            para = ref["paragraph_number"]
            sql(
                f"INSERT INTO case_legislation_refs (case_id, act_title, section_reference, context, paragraph_number) "
                f"VALUES ('{case_id}', '{act}', '{sec}', '{ctx}', {para}) "
                f"ON CONFLICT DO NOTHING;"
            )
        total_inserted += len(refs)
        log.info("  %s: %d refs inserted", citation, len(refs))

    log.info("Done. %d refs inserted across %d cases.", total_inserted, len(rows))


if __name__ == "__main__":
    main()