from __future__ import annotations

import logging
import re

from fastapi import HTTPException, APIRouter

from backend.services.data_loader import load_definitions, get_definition_text, get_act_section_content, get_definition_across_acts

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/definitions/{act}")
def get_definitions(act: str):
    defs = load_definitions(act)
    return {"act": act, "count": len(defs), "terms": defs}


@router.get("/api/definition/{act}/{term}")
def get_definition(act: str, term: str):
    # Return the term wherever it is defined, preferring the requested act.
    result = get_definition_across_acts(term, preferred_act=act)
    if not result:
        raise HTTPException(status_code=404, detail=f"Definition for '{term}' not found")
    return result


@router.get("/api/definition-text/{act}/{term}")
def get_definition_text_route(act: str, term: str):
    result = get_definition_text(act, term)
    if not result:
        raise HTTPException(status_code=404, detail=f"Definition for '{term}' not found")
    return result


@router.get("/api/section-defined-terms/{act}/{section}")
def section_defined_terms(act: str, section: str):
    """Return defined terms that appear in a section's body text.

    For dictionary sections (6, 195-1, 995-1), terms are returned from the
    definitions index because the raw body uses plain-text definition
    patterns (not wrapped in *asterisks*), which the formatting pipeline
    only wraps at serve time.
    """
    defs = load_definitions(act)
    if not defs:
        return {"act": act, "section": section, "count": 0, "terms": []}

    # Dictionary sections: return all terms from the index for this section
    DICT_SECTIONS = frozenset({"6", "195-1", "995-1"})
    if section in DICT_SECTIONS:
        found = [
            {"term": term, "section": info.get("section", ""), "anchor": info.get("anchor", "")}
            for term, info in defs.items()
            if info.get("section") == section
        ]
        found.sort(key=lambda t: len(t["term"]), reverse=True)
        return {"act": act, "section": section, "count": len(found), "terms": found}

    # Non-dictionary sections: scan body text for *italicized* terms
    try:
        fm, body = get_act_section_content(act, section)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error loading section content")
        return {"act": act, "section": section, "count": 0, "terms": []}

    if not body:
        return {"act": act, "section": section, "count": 0, "terms": []}

    found = []
    seen = set()
    for m in re.finditer(r"\*([^*\n]+?)\*", body):
        term = m.group(1).strip()
        key = term.lower()
        if key in defs and key not in seen:
            info = defs[key]
            seen.add(key)
            found.append({
                "term": term,
                "section": info.get("section", ""),
                "anchor": info.get("anchor", ""),
            })
    found.sort(key=lambda t: len(t["term"]), reverse=True)
    return {"act": act, "section": section, "count": len(found), "terms": found}
