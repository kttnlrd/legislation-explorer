from __future__ import annotations

import json
import logging

from fastapi import HTTPException, APIRouter

from backend.config import DATA_DIR, INSOLVENCY_DIR
from backend.services.data_loader import load_tree, get_act_section_content
from backend.services.search_service import get_insolvency_chapter
from backend.processors.markdown import (
    link_definitions, format_definition_terms,
    link_section_references, link_cross_act_references, auto_link_definitions,
)
from backend.services.text_cleaner import strip_scraped_markup

from .rulings import list_rulings, get_ruling
from .tax_cases import list_tax_cases_tree, get_tax_case_by_citation
from .regulatory_guides import list_regulatory_guides, get_regulatory_guide

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/acts")
def list_acts():
    acts = []
    for act_dir in sorted(DATA_DIR.iterdir()):
        if act_dir.is_dir() and (act_dir / "tree.json").exists():
            tree = load_tree(act_dir.name)
            acts.append({
                "id": act_dir.name,
                "name": tree.get("act", act_dir.name),
                "compilation_no": tree.get("compilation_no"),
                "compilation_date": tree.get("compilation_date"),
            })
    acts.append({"id": "rulings", "name": "ATO Rulings", "compilation_no": None, "compilation_date": None})
    acts.append({"id": "tax-cases", "name": "Tax Cases", "compilation_no": None, "compilation_date": None})
    acts.append({"id": "private-rulings", "name": "Private Rulings", "compilation_no": None, "compilation_date": None})
    acts.append({"id": "regulatory-guides", "name": "ASIC Regulatory Guides", "compilation_no": None, "compilation_date": None})
    acts.append({"id": "insolvency-keays", "name": "Keays Insolvency", "compilation_no": None, "compilation_date": None})
    acts.append({"id": "treaties", "name": "Tax Treaties", "compilation_no": None, "compilation_date": None})
    return acts


def _build_insolvency_tree():
    """Build a parts/sections tree from the insolvency ch-tree.json for
    frontend compatibility with the TreeNode component."""
    ch_tree_path = INSOLVENCY_DIR / "ch-tree.json"
    if not ch_tree_path.exists():
        raise HTTPException(status_code=404, detail="Insolvency textbook not found")
    ch_tree = json.loads(ch_tree_path.read_text(encoding="utf-8"))
    chapters = ch_tree.get("chapters", [])
    parts = []
    for ch in chapters:
        n = ch["chapter"]
        parts.append({
            "id": f"ch-{n}",
            "title": f"Chapter {n}: {ch['title']}",
            "sections": [
                {
                    "id": str(n),
                    "title": ch["title"],
                    "path": str(n),
                }
            ],
        })
    return {"act": "Keays Insolvency Textbook", "parts": parts}


def _build_private_rulings_tree() -> dict:
    """Years → rulings as a Tree for the sidebar.

    Divisions are years (with counts); sections are empty — the per-year
    ruling list loads on demand via /api/private-rulings?year=. 57,608
    sections inline would make the tree ~15MB.
    """
    from .private_rulings import _load_index

    idx = _load_index()
    by_year: dict[int, int] = {}
    undated = 0
    for meta in idx.values():
        y = meta.get("year")
        if y:
            by_year[y] = by_year.get(y, 0) + 1
        else:
            undated += 1
    divisions = [
        {
            "id": str(y),
            "title": f"{y} ({c})",
            "subdivisions": [],
            "sections": [],
        }
        for y, c in sorted(by_year.items(), reverse=True)
    ]
    if undated:
        divisions.append({
            "id": "undated",
            "title": f"Undated ({undated})",
            "subdivisions": [],
            "sections": [],
        })
    return {
        "act": "Private Rulings",
        "parts": [{
            "id": "private-rulings",
            "title": "Private Rulings",
            "divisions": divisions,
            "sections": [],
        }],
    }


@router.get("/api/tree/{act}")
def get_tree(act: str):
    if act == "rulings":
        return list_rulings()
    if act == "tax-cases":
        return list_tax_cases_tree()
    if act == "private-rulings":
        return _build_private_rulings_tree()
    if act == "regulatory-guides":
        return list_regulatory_guides()
    if act == "insolvency-keays":
        return _build_insolvency_tree()
    return load_tree(act)


@router.get("/api/section/{act}/{section:path}")
def get_section(act: str, section: str):
    if act == "rulings":
        return get_ruling(section)

    if act == "tax-cases":
        return get_tax_case_by_citation(section)

    if act == "private-rulings":
        from .private_rulings import private_ruling_detail
        return private_ruling_detail(section)

    if act == "regulatory-guides":
        return get_regulatory_guide(int(section))

    if act == "insolvency-keays":
        return _get_insolvency_chapter_section(section)

    # Strip leading 's' prefix from section id if present (e.g. s8-1 → 8-1).
    # Sections are stored WITHOUT the s prefix in the data files.
    # Digit lookahead guard: genuine ids like 'schedule-2' (itaa-1936) must NOT be stripped.
    if section.startswith('s') and len(section) > 1 and section[1].isdigit():
        section = section[1:]

    fm, body = get_act_section_content(act, section)

    # Strip scraped markup FIRST (CDN-0094) — clean artifacts before processors inject anchors
    body = strip_scraped_markup(body)

    # Then run definition/formatters — these inject <a id> anchors that survive cleanup
    body = format_definition_terms(body, section, act)
    body = link_definitions(body, act)
    body = link_section_references(body, act)
    body = link_cross_act_references(body, act)
    body = auto_link_definitions(body, act, section)

    result = {"frontmatter": fm, "body": body}

    # Include ASIC Regulatory Guides for corps act sections
    if act == "corporations-act-2001":
        try:
            from .regulatory_guides import get_rgs_for_section
            rg_result = get_rgs_for_section(act, section)
            if rg_result["count"] > 0:
                result["regulatory_guides"] = rg_result["regulatory_guides"]
        except Exception:
            pass

    return result


def _get_insolvency_chapter_section(section: str):
    """Fetch an insolvency chapter and return it in standard section format
    so the SectionContent component can render it."""
    try:
        chapter_num = int(section)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid chapter number: {section}")
    result = get_insolvency_chapter(chapter_num)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Chapter {chapter_num} not found")

    title = result.get("title", f"Chapter {chapter_num}")
    body = result.get("content", "")
    return {
        "frontmatter": {"title": title},
        "body": strip_scraped_markup(body),
    }