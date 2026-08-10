from __future__ import annotations

import json
import re
import logging
from pathlib import Path

from fastapi import HTTPException, APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from ..config import DATA_DIR, RULING_DIR, ATO_RULING_DIR
from ..services.data_loader import (
    load_rulings, get_act_section_content, load_ruling_section_refs
)
from ..services.text_cleaner import clean_ruling_body

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/rulings/{act}/{section}")
def rulings_for_section(act: str, section: str, limit: int = 50, offset: int = 0):
    from ..services.data_loader import get_rulings_for_section
    rulings = get_rulings_for_section(act, section, limit, offset)
    ruling_list = load_rulings()
    richer_rulings = []
    for r in rulings:
        found = next((item for item in ruling_list if item["citation"] == r["citation"]), None)
        if found:
            richer_rulings.append(found)
        else:
            # Include basic info even without full manifest entry
            # Extract year from citation when possible (e.g. "TR_2024_1" → 2024)
            fallback_year = 0
            yr_m = re.match(r'^[A-Za-z]+_(\d{2,4})_', r["citation"])
            if yr_m:
                fallback_year = int(yr_m.group(1))
                if fallback_year < 100:
                    fallback_year += 1900 if fallback_year >= 90 else 2000
            richer_rulings.append({
                "citation": r["citation"],
                "title": r.get("title", r["citation"]),
                "type": "ruling",
                "year": fallback_year,
                "ato_url": "",
            })
    return {
        "act": act,
        "section": section,
        "count": len(richer_rulings),
        "rulings": richer_rulings,
    }

TYPE_DISPLAY: dict[str, str] = {
    "ATOID": "ATO ID – ATO Interpretative Decision",
    "GSTR": "GSTR – GST Ruling",
    "IT": "IT – Income Tax Ruling",
    "LCG": "LCG – Law Companion Guideline",
    "MT": "MT – Miscellaneous Tax Ruling",
    "PCG": "PCG – Practical Compliance Guideline",
    "PS LA": "PS LA – Practice Statement (Law Administration)",
    "SGR": "SGR – Superannuation Guarantee Ruling",
    "TA": "TA – Taxpayer Alert",
    "TD": "TD – Tax Determination",
    "TR": "TR – Tax Ruling",
}

@router.get("/api/rulings-list")
def list_rulings(group: str = "year"):
    """
    List all ATO rulings grouped by year or by ruling type.

    Parameters:
    - group: "year" (default) → Year → Type → Rulings
            "type"           → Type → Year → Rulings
    """
    rulings = load_rulings()
    years = {}
    for r in rulings:
        year = r.get("year", 0)
        t = r.get("type", "Ruling")
        if year not in years:
            years[year] = {}
        if t not in years[year]:
            years[year][t] = []
        years[year][t].append(r)

    def ruling_sort_key(r):
        m = re.search(r'(\d+)$', r["citation"])
        return int(m.group(1)) if m else 0

    if group == "type":
        # Group: Type → Year → Rulings
        types: dict[str, dict] = {}
        for year, type_dict in years.items():
            for t, secs in type_dict.items():
                if t not in types:
                    types[t] = {}
                types[t][year] = secs

        parts = []
        for t in sorted(types.keys()):
            year_divs = []
            for year in sorted(types[t].keys(), reverse=True):
                sections = sorted(types[t][year], key=ruling_sort_key)
                year_divs.append({
                    "id": f"{t.lower().replace(' ', '-')}-{year}",
                    "title": str(year),
                    "subdivisions": [],
                    "sections": [
                        {
                            "id": r["citation"],
                            "title": r.get("citation_display", r["citation"]) + (f" — {r.get('full_title', '')}" if r.get('full_title') and r.get('full_title') != r["title"] and 'Legal database' not in r.get('full_title', '') else "") + ("  [WITHDRAWN]" if r.get('withdrawn') else ""),
                            "path": r["citation"],
                            "ato_url": r.get("ato_url", ""),
                            "austlii_url": r.get("austlii_url", ""),
                        }
                        for r in sections
                    ],
                })
            parts.append({
                "id": t.lower().replace(' ', '-'),
                "title": TYPE_DISPLAY.get(t, t),
                "divisions": year_divs,
                "sections": [],
            })
    else:
        # Default: Year → Type → Rulings
        parts = []
        for year in sorted(years.keys(), reverse=True):
            divisions = []
            for t in sorted(years[year].keys()):
                sections = sorted(years[year][t], key=ruling_sort_key)
                divisions.append({
                    "id": f"{year}-{t.lower().replace(' ', '-')}",
                    "title": TYPE_DISPLAY.get(t, t),
                    "subdivisions": [],
                    "sections": [
                        {
                            "id": r["citation"],
                            "title": r.get("citation_display", r["citation"]) + (f" — {r.get('full_title', '')}" if r.get('full_title') and r.get('full_title') != r["title"] and 'Legal database' not in r.get('full_title', '') else "") + ("  [WITHDRAWN]" if r.get('withdrawn') else ""),
                            "path": r["citation"],
                            "ato_url": r.get("ato_url", ""),
                            "austlii_url": r.get("austlii_url", ""),
                        }
                        for r in sections
                    ],
                })
            parts.append({
                "id": str(year),
                "title": "IT Rulings" if year == 0 else str(year),
                "divisions": divisions,
                "sections": [],
            })
    return {"act": "ATO Rulings", "parts": parts}

CITATION_ALIASES = {"LCR": "LCG", "AID": "ATOID"}

_ATO_ID_STRIP = re.compile(
    r'^(ATO\s+Interpretative\s+Decision\s*|ATO\s+ID\s+\d{4}/\d+\s*|=+\s*|File\s+Number\s*|FOI\s+status[^\\n]*|'
    r'This\s+ATO\s+ID[^\\n]*|This\s+document[^\\n]*)',
    re.IGNORECASE | re.MULTILINE
)

def _strip_ato_id_header(text: str) -> str:
    """Remove redundant header lines from ATO ID content (they duplicate page-level metadata)."""
    lines = text.splitlines()
    # Find first substantive line that isn't a header
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r'^(ATO\s+Interpretative\s+Decision|ATO\s+ID\s+\d{4}/\d+|={3,})$', stripped, re.IGNORECASE):
            continue
        if re.match(r'^(File\s+Number|FOI\s+status)', stripped, re.IGNORECASE):
            continue
        # First substantive line found
        return '\n'.join(lines[i:])
    return text

@router.get("/api/ruling/{citation:path}/download")
def download_ruling(citation: str):
    import re as _re
    citation = citation.replace("%20", " ")
    normalized = _re.sub(r'[\s/]+', '_', citation).strip('_')
    candidates = {normalized}
    # Alias resolution: AID → ATOID, LCR → LCG
    prefix_m = _re.match(r'^([A-Za-z]+)_(.*)$', normalized)
    if prefix_m and prefix_m.group(1).upper() in CITATION_ALIASES:
        candidates.add(f"{CITATION_ALIASES[prefix_m.group(1).upper()]}_{prefix_m.group(2)}")
    for r in load_rulings():
        if r["citation"] in candidates:
            path = Path(r["source"])
            if path.exists():
                return FileResponse(
                    path=path,
                    filename=path.name,
                    media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
                )
    raise HTTPException(status_code=404, detail=f"Ruling {citation} not found")


@router.get("/api/ruling/{citation:path}")
def get_ruling(citation: str):
    import re as _re
    citation = citation.replace("%20", " ")
    # Normalize: "TR 2020/1" → "TR_2020_1"
    normalized = _re.sub(r'[\s/]+', '_', citation).strip('_')
    candidates = {normalized}
    prefix_m = _re.match(r'^([A-Za-z]+)_(.*)$', normalized)
    if prefix_m and prefix_m.group(1).upper() in CITATION_ALIASES:
        candidates.add(f"{CITATION_ALIASES[prefix_m.group(1).upper()]}_{prefix_m.group(2)}")
        # Also add the reverse: if normalized is ATOID_2016_1, also check AID_2016_1
        alias_val = CITATION_ALIASES[prefix_m.group(1).upper()]
        if alias_val != prefix_m.group(1).upper():
            candidates.add(f"{prefix_m.group(1).upper()}_{prefix_m.group(2)}")
    # Also check reverse aliases: if citing ATOID_2016_1, also try AID_2016_1
    for alias_src, alias_dst in list(CITATION_ALIASES.items()):
        if alias_src != alias_dst and normalized.startswith(alias_dst + '_'):
            suffix = normalized[len(alias_dst) + 1:]
            candidates.add(f"{alias_src}_{suffix}")

    # First check for a structured summary
    SUMMARY_DIR = DATA_DIR / "rulings" / "summaries"
    from ..services.data_loader import load_rulings as _load_rulings
    for ref in candidates:
        summary_path = SUMMARY_DIR / f"{ref}.json"
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))

                # Build ATO URL
                ato_url = ""
                for r in _load_rulings():
                    if r["citation"] in candidates:
                        ato_url = r.get("ato_url", "")
                        break

                # For ATO IDs, return structured data with notice + body
                if summary.get("type") == "ATO Interpretative Decision" or summary.get("full_text"):
                    return {
                        "frontmatter": {
                            "act": "ATO Rulings",
                            "title": summary.get("title", ref),
                            "part": "ATO ID",
                            "division": summary.get("subject", ""),
                        },
                        "citation": summary.get("citation", ref),
                        "descriptive_title": summary.get("title", ""),
                        "question": summary.get("question", ""),
                        "notice": summary.get("notice", ""),
                        "body": summary.get("body", summary.get("full_text", "")),
                        "type": "ATO ID",
                        "status": summary.get("status", "Final"),
                        "cases_referenced": summary.get("cases_referenced", []),
                        "legislation_referenced": summary.get("legislation_referenced", []),
                        "ato_url": ato_url,
                        "referenced_sections": [],
                    }

                # For full rulings, return structured data
                return {
                    "frontmatter": {
                        "act": "ATO Rulings",
                        "title": summary.get("title", ref),
                        "part": summary.get("type", ""),
                        "division": "",
                    },
                    "citation": summary.get("citation", ref),
                    "descriptive_title": summary.get("title", ""),
                    "subject": summary.get("subject", ""),
                    "background": summary.get("background", ""),
                    "ruling": summary.get("ruling", ""),
                    "body": summary.get("body", ""),
                    "type": summary.get("type", ""),
                    "status": summary.get("status", ""),
                    "date_of_effect": summary.get("date_of_effect", ""),
                    "cases_referenced": summary.get("cases_referenced", []),
                    "legislation_referenced": summary.get("legislation_referenced", []),
                    "related_rulings": summary.get("related_rulings", []),
                    "ato_url": ato_url,
                    "referenced_sections": [],
                }
            except Exception:
                pass  # Fall through to raw text

    # Fall back to raw text from flat files
    for r in _load_rulings():
        if r["citation"] in candidates:
            path = Path(r["source"])
            if path.exists():
                content = path.read_text(encoding="utf-8")
                content = _strip_ato_id_header(content)
                referenced_sections = load_ruling_section_refs(citation)
                cleaned = clean_ruling_body(content)
                body = cleaned["body"]
                return {
                    "frontmatter": {
                        "act": "ATO Rulings",
                        "title": r["title"],
                        "part": r["type"],
                        "division": str(r["year"]),
                    },
                    "descriptive_title": cleaned["descriptive_title"],
                    "body": body,
                    "citation": r["citation"],
                    "type": r["type"],
                    "year": r["year"],
                    "ato_url": r.get("ato_url", ""),
                    "referenced_sections": referenced_sections,
                }
    raise HTTPException(status_code=404, detail=f"Ruling {citation} not found")

@router.get("/api/ruling-sections/{citation:path}")
def get_ruling_sections(citation: str):
    citation = citation.replace("%20", " ")
    referenced_sections = load_ruling_section_refs(citation)
    
    sections_with_titles = []
    for ref in referenced_sections:
        act = ref["act"]
        section = ref["section"]
        
        try:
            fm, body = get_act_section_content(act, section)
            sections_with_titles.append({
                "act": act,
                "section": section,
                "title": fm.get("title", section),
                "full_title": fm.get("full_title", fm.get("title", section)),
            })
        except HTTPException as e:
            logger.warning(f"Could not retrieve content for {act} {section}: {e.detail}")
            sections_with_titles.append({
                "act": act,
                "section": section,
                "title": f"Section {section} (Title not found)",
                "full_title": f"Section {section} (Title not found)",
            })
    return {
        "citation": citation,
        "referenced_sections": sections_with_titles,
    }