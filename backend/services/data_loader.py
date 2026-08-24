from __future__ import annotations

import functools
import json
import re
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np

from fastapi import HTTPException
from backend.config import DATA_DIR, COMMENTARY_DIR, CASE_DIR, RULING_DIR, ATO_RULING_DIR, PUBLICATION_NAMES, PUB_ACT_MAP

logger = logging.getLogger(__name__)

# Ligature normalisation — some CCH content uses typographic ligatures
# (ﬃ, ﬁ, ﬀ) that don't render on all devices
_LIGATURE_TABLE = str.maketrans({
    '\ufb00': 'ff',   # ﬀ
    '\ufb01': 'fi',   # ﬁ
    '\ufb02': 'fl',   # ﬂ
    '\ufb03': 'ffi',  # ﬃ
    '\ufb04': 'ffl',  # ﬄ
    '\ufb05': 'st',   # ﬅ
    '\ufb06': 'st',   # ﬆ
})
def _normalise_text(s: str) -> str:
    return s.translate(_LIGATURE_TABLE)


_ATO_ID_HEADER = re.compile(
    r'^(ATO\s+Interpretative\s+Decision|ATO\s+ID\s+\d{4}/\d+|={3,}|'
    r'File\s+Number|FOI\s+status|This\s+ATO\s+ID|This\s+document)',
    re.IGNORECASE
)


def _check_withdrawn(content: str) -> bool:
    """Check content for withdrawal/supersession signals.
    
    Only searches within the first 2000 chars (versus full scan) to avoid
    false positives from version-history footers mentioning "Archived" or
    "superseded" in references to other documents.
    """
    head = content[:2000]
    patterns = [
        r'\b(withdrawn|Archived|superseded|no longer current)\b',
        r'has been replaced by',
    ]
    return any(re.search(p, head, re.IGNORECASE) for p in patterns)


def _strip_ato_chrome(text: str) -> str:
    """Strip ATO web chrome boilerplate from ruling text.
    
    Handles multi-line format:
      Legal database
      Legal database
      Contents
      Download
      Email
      Print
      Back to browse
      N related documents
    """
    # Strip the chrome block at the start of the text
    text = re.sub(
        r'(?i)^(Legal\s+database\s*\n){1,2}'
        r'(Contents\s*\n)?'
        r'(Download\s*\n)?'
        r'(Email\s*\n)?'
        r'(Print\s*\n)?'
        r'(Back\s+to\s+browse\s*\n)?'
        r'(\d+\s+related\s+documents\s*\n)?',
        '', text,
    )
    # Also handle single-line format
    text = re.sub(
        r'(?i)^Legal\s+database\s*/\s*Contents\s*/\s*Download\s*/\s*Email\s*/\s*Print\s*/\s*Back\s+to\s+browse.*?\n',
        '', text,
    )
    return text.strip()


# ---------------------------------------------------------------------------
# Acts / sections
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def load_acts_meta() -> list[dict]:
    """Lightweight act metadata for /api/acts — top-level scalars from each
    tree.json, no title normalisation and no cached full-tree copies."""
    acts = []
    for act_dir in sorted(DATA_DIR.iterdir()):
        tree_path = act_dir / "tree.json"
        if act_dir.is_dir() and tree_path.exists():
            tree = json.loads(tree_path.read_text(encoding="utf-8"))
            acts.append({
                "id": act_dir.name,
                "name": tree.get("act", act_dir.name),
                "compilation_no": tree.get("compilation_no"),
                "compilation_date": tree.get("compilation_date"),
            })
    return acts


@functools.lru_cache(maxsize=None)
def load_tree(act: str) -> dict:
    path = DATA_DIR / act / "tree.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Act {act} not found")
    tree = json.loads(path.read_text(encoding="utf-8"))
    # Normalise section titles
    for part in tree.get("parts", []):
        for sec in part.get("sections", []):
            sec["title"] = _normalise_text(sec["title"])
        for div in part.get("divisions", []):
            for sec in div.get("sections", []):
                sec["title"] = _normalise_text(sec["title"])
            for sub in div.get("subdivisions", []):
                for sec in sub.get("sections", []):
                    sec["title"] = _normalise_text(sec["title"])
                sub["title"] = _normalise_text(sub.get("title", ""))
            div["title"] = _normalise_text(div.get("title", ""))
        part["title"] = _normalise_text(part.get("title", ""))
    return tree


@functools.lru_cache(maxsize=None)
def _normalize_term_key(key: str) -> str:
    """Normalize a definition term key for lookup: lowercase + Unicode quote normalization.
    
    PDF-extracted text commonly uses curly apostrophes (U+2019) which must
    be normalized to ASCII apostrophes (U+0027) for index matching.
    """
    return key.lower().replace("\u2018", "'").replace("\u2019", "'")


def _singularise_term(term: str) -> str:
    """Best-effort singularisation for definition lookups.

    Index keys are singular ('capital gain', 'fringe benefit'), but LLMs
    naturally ask with plurals ('capital gains'). Strip a trailing 's'
    unless it looks like an -ss/-us/-is word ('business', 'bonus', 'basis').
    """
    t = term.strip()
    if len(t) <= 3:
        return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith(("ss", "us", "is", "sses")):
        return t
    if t.endswith("s"):
        return t[:-1]
    return t


# Shorthand act ids accepted by the definitions API. Unknown ids pass through.
ACT_ALIASES = {
    "1936": "itaa-1936", "itaa36": "itaa-1936",
    "1997": "itaa-1997", "itaa97": "itaa-1997",
    "gst": "gst-1999", "gst1999": "gst-1999",
    "fbt": "fbt-1986", "fbtaa": "fbt-1986",
    "taa": "taa-1953",
    "sis": "sis-1993",
    "corps": "corporations-act-2001",
    "aml": "aml-ctf-2006", "amlctf": "aml-ctf-2006",
    "nz": "nz-it-2007", "nzit": "nz-it-2007",
}


def resolve_act_id(act: str) -> str:
    return ACT_ALIASES.get(act.strip().lower(), act)


def _definitions_store_path() -> Path | None:
    # Prefer the combined definitions_all.json; fall back to the act-keyed
    # definitions.json when the combined file is absent (both share the
    # {act: {section, terms}} shape).
    for name in ("definitions_all.json", "definitions.json"):
        path = DATA_DIR / name
        if path.exists():
            return path
    return None


@functools.lru_cache(maxsize=4)
def _definitions_store(path_str: str, mtime: float) -> dict:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def _load_definitions_store() -> dict:
    path = _definitions_store_path()
    if not path:
        return {}
    return _definitions_store(str(path), path.stat().st_mtime)


def _canon_section_id(section: str) -> str:
    """Canonicalise letter-suffixed section ids ('6f' -> '6F', '6ab' -> '6AB').

    Section files on disk use lowercase stems, but tree/meta and the graph
    use uppercase suffixes; normalise so lookups and graph edges resolve to
    the canonical node (CDN-0164).
    """
    return re.sub(r"[a-z]+$", lambda m: m.group(0).upper(), section)


def load_definitions(act: str) -> dict[str, dict]:
    act = resolve_act_id(act)
    act_data = _load_definitions_store().get(act, {})
    terms = act_data.get("terms", {})
    out = {}
    for term, info in terms.items():
        norm = {**info}
        if norm.get("section"):
            norm["section"] = _canon_section_id(norm["section"])
        out[_normalize_term_key(term)] = norm
    return out


def _all_definition_acts() -> list[str]:
    """Acts that carry a definitions index, derived from the definitions store."""
    try:
        store = _load_definitions_store()
        if store:
            return list(store.keys())
    except Exception:
        pass
    return ["itaa-1997", "itaa-1936", "gst-1999"]


# ---------------------------------------------------------------------------
# Commentary
# ---------------------------------------------------------------------------

def _normalize_section_ref(ref: str, pub_name: str) -> tuple[str, str] | None:
    ref = ref.strip().replace("\n", " ")
    m = re.search(r's\s+(\d+[A-Za-z]*-[\d\(\) ]+(?:\(\d+\))?)', ref, re.IGNORECASE)
    if not m:
        return None
    section = m.group(1)
    lower = ref.lower()
    if "itaa97" in lower or "itaa 97" in lower:
        return ("itaa-1997", section)
    if "itaa36" in lower or "itaa 36" in lower:
        return ("itaa-1936", section)
    if "gst act" in lower or "gst 1999" in lower:
        return ("gst-1999", section)
    if "gst" in pub_name.lower():
        return ("gst-1999", section)
    return ("itaa-1997", section)


@functools.lru_cache(maxsize=None)
def _load_commentary_index() -> dict[str, list[dict]]:
    commentary_index: dict[str, list[dict]] = {}
    for filename, pub_display in PUBLICATION_NAMES.items():
        path = COMMENTARY_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        pub_name = data.get("name", pub_display)
        for ch in data.get("chapters", []):
            for mh in ch.get("major_headings", []):
                all_refs: set[tuple[str, str]] = set()
                for cb in mh.get("content_blocks", []):
                    for ref in cb.get("section_refs", []):
                        norm = _normalize_section_ref(ref, pub_name)
                        if norm:
                            all_refs.add(norm)
                for sh in mh.get("sub_headings", []):
                    for cb in sh.get("content_blocks", []):
                        for ref in cb.get("section_refs", []):
                            norm = _normalize_section_ref(ref, pub_name)
                            if norm:
                                all_refs.add(norm)
                if all_refs:
                    entry = {
                        "publication": pub_name,
                        "chapter_number": ch.get("number"),
                        "chapter_title": _normalise_text(ch.get("title", "")),
                        "heading_title": _normalise_text(mh.get("title", "")),
                        "paragraph_number": mh.get("paragraph_number"),
                        "content_blocks": mh.get("content_blocks", []),
                        "sub_headings": mh.get("sub_headings", []),
                    }
                    for act, section in all_refs:
                        key = f"{act}:{section}"
                        if key not in commentary_index:
                            commentary_index[key] = []
                        commentary_index[key].append(entry)
    return commentary_index


def get_commentary_for_section(act: str, section: str, limit: int = 50, offset: int = 0) -> list[dict]:
    index = _load_commentary_index()
    key = f"{act}:{section}"
    entries = index.get(key, [])
    if not entries:
        base = section.split("(")[0]
        if base != section:
            entries = index.get(f"{act}:{base}", [])
    end = offset + min(limit, 100)
    return entries[offset:end]


# ---------------------------------------------------------------------------
# Citations (cases / rulings per section)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _load_citation_index() -> dict[str, dict[str, list[dict]]]:
    path = DATA_DIR / "citation_index.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _get_embedding_db():
    """Get a connection to the embeddings database."""
    db_path = DATA_DIR / "embeddings.db"
    if db_path.exists():
        return sqlite3.connect(str(db_path))
    return None


_COURT_MAP = {
    'high court of australia': 'HCA',
    'federal court of australia (full court)': 'FCAFC',
    'federal court of australia - full court': 'FCAFC',
    'full court of the federal court of australia': 'FCAFC',
    'federal court of australia': 'FCA',
    'administrative appeals tribunal': 'AATA',
    'administrative appeals tribunal of australia': 'AATA',
    'administrative review tribunal': 'ARTA',
    'administrative review tribunal (general division)': 'ARTA',
    'administrative review tribunal - general division': 'ARTA',
}

def _map_court(act_name: str, fallback_id: str = "") -> str:
    """Map a full court name to a short code.
    
    Args:
        act_name: The court name from the embeddings 'act' field.
        fallback_id: The source ID (e.g. austlii citation), used to infer
                     court when act_name is 'unknown'.
    """
    key = act_name.lower().strip()
    # Exact match first
    if key in _COURT_MAP:
        return _COURT_MAP[key]
    # Strip parentheticals and try again
    stripped = re.sub(r'[\(\)\-]', '', key).strip()
    if stripped in _COURT_MAP:
        return _COURT_MAP[stripped]
    # Fuzzy: match if all significant words appear
    for pattern, code in _COURT_MAP.items():
        pwords = set(pattern.split())
        kwords = set(key.split())
        if pwords and pwords.issubset(kwords):
            return code
        # Try stripped version
        stripped_pwords = {w.strip('()') for w in pwords}
        stripped_kwords = {w.strip('()') for w in kwords}
        if stripped_pwords and stripped_pwords.issubset(stripped_kwords):
            return code
    # Fallback: try to infer from the citation format
    if fallback_id:
        parts = fallback_id.split('_')
        if len(parts) >= 2:
            court_code = parts[1]
            valid_codes = {'HCA', 'FCAFC', 'FCA', 'AATA', 'ARTA'}
            if court_code in valid_codes:
                return court_code
    return "Other"


def _find_similar_via_embeddings(act: str, section: str, target_type: str, limit: int = 10) -> list[dict]:
    """Find related cases or rulings via embeddings similarity index."""
    db = _get_embedding_db()
    if db is None:
        return []
    
    try:
        # Find section embedding IDs
        sec_ids = db.execute(
            "SELECT id FROM embeddings WHERE act = ? AND section = ? AND source_type = 'section'",
            (act, section)
        ).fetchall()
        
        if not sec_ids:
            return []
        
        ids = [r[0] for r in sec_ids]
        placeholders = ",".join("?" * len(ids))
        
        # Query similarity_index for cross-type neighbors
        rows = db.execute(f"""
            SELECT DISTINCT e.act, e.section, e.section_title, MAX(s.similarity) as max_sim
            FROM similarity_index s
            JOIN embeddings e ON s.neighbor_id = e.id
            WHERE s.embedding_id IN ({placeholders})
            AND e.source_type = ?
            AND e.section IS NOT NULL
            GROUP BY e.section, e.act
            ORDER BY max_sim DESC
            LIMIT ?
        """, ids + [target_type, limit]).fetchall()
        
        results = []
        for r in rows:
            item = {"type": target_type}
            if target_type == "case":
                # For cases: section = austlii citation, section_title = case name
                item["citation"] = r[1]  # e.g., "2023_AATA_3074"
                item["title"] = r[2] or r[1]  # case name
                item["court"] = _map_court(r[0], r[1])  # court code from the act field
            else:
                # For rulings: section = ruling ID, section_title = ruling description
                item["citation"] = r[1]  # e.g., "AID_2011_104"
                item["title"] = r[2] or r[1]  # ruling title
                item["year"] = 0
                item["ato_url"] = ""
            results.append(item)
        return results
    finally:
        db.close()


def get_cases_for_section(act: str, section: str, limit: int = 50, offset: int = 0) -> list[dict]:
    # Primary: embeddings similarity index (vector-based, highest quality)
    cases = _find_similar_via_embeddings(act, section, "case", limit)
    
    # Fallback 1: citation index
    if not cases:
        act_data = _load_citation_index().get(act, {})
        entries = act_data.get(section, [])
        cases = [e for e in entries if e.get("type") == "case"]
        cases = [c for c in cases if classify_case(c.get("title", "")) == "tax"]
    
    # Fallback 2: smartlink index (lowest quality, generic placeholder entries)
    if not cases:
        smartlinks = get_smartlinks_for_item("section", f"{act}#{section}")
        case_links = [s for s in smartlinks if s.get("type") == "case"]
        for cl in case_links:
            case_id = cl.get("id", "")
            cases.append({"type": "case", "title": case_id, "citation": case_id})
    
    end = offset + min(limit, 100)
    return cases[offset:end]


def get_rulings_for_section(act: str, section: str, limit: int = 50, offset: int = 0) -> list[dict]:
    # Primary: embeddings similarity index (vector-based, highest quality)
    rulings = _find_similar_via_embeddings(act, section, "ruling", limit)
    
    # Fallback 1: citation index
    if not rulings:
        act_data = _load_citation_index().get(act, {})
        entries = act_data.get(section, [])
        rulings = [e for e in entries if e.get("type") == "ruling"]
    
    # Fallback 2: smartlink index (lowest quality, generic placeholder entries)
    if not rulings:
        smartlinks = get_smartlinks_for_item("section", f"{act}#{section}")
        ruling_links = [s for s in smartlinks if s.get("type") == "ruling"]
        for rl in ruling_links:
            ruling_id = rl.get("id", "")
            rulings.append({"type": "ruling", "title": ruling_id, "citation": ruling_id})
    
    end = offset + min(limit, 100)
    return rulings[offset:end]


# ---------------------------------------------------------------------------
# Smart links
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _load_smartlink_index() -> dict[str, Any]:
    path = DATA_DIR / "smartlink_index.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    logger.warning("smartlink_index.json not found")
    return {}


def get_smartlinks_for_item(item_type: str, item_id: str) -> list[dict]:
    index = _load_smartlink_index()
    if item_type == "section":
        try:
            act_code, section_id = item_id.split("#")
            return index.get("sections", {}).get(act_code, {}).get(section_id, [])
        except ValueError:
            logger.error("Invalid section item_id format: %s", item_id)
            return []
    elif item_type == "case":
        return index.get("cases", {}).get(item_id, [])
    elif item_type == "ruling":
        return index.get("rulings", {}).get(item_id, [])
    elif item_type == "part":
        try:
            act_code, part_id = item_id.split("#")
            return index.get("parts", {}).get(act_code, {}).get(part_id, [])
        except ValueError:
            logger.error("Invalid part item_id format: %s", item_id)
            return []
    return []


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

TAX_KEYWORDS = ["commissioner of taxation", "federal commissioner of taxation",
                "deputy commissioner of taxation", r"\btax\b", "income tax", "gst"]
ASIC_KEYWORDS = ["australian securities and investments commission",
                 "australian securities commission", r"\basic\b"]


def classify_case(case_name: str) -> str:
    name = case_name.lower()
    is_tax = any(re.search(p, name) for p in TAX_KEYWORDS)
    is_asic = any(re.search(p, name) for p in ASIC_KEYWORDS)
    if is_tax and is_asic:
        return "asic"
    if is_tax:
        return "tax"
    if is_asic:
        return "asic"
    return "other"


def short_case_name(case_name: str) -> str:
    name = case_name.removeprefix("Re ")
    parts = re.split(r'\s+[vV]\s+', name, maxsplit=1)
    if len(parts) == 2:
        left, right = parts[0], parts[1]
        gov = ["commissioner", "commission", "asic", "australian securities",
               "director", "attorney-general", "minister", "administrator"]
        left_gov = any(k in left.lower() for k in gov)
        right_gov = any(k in right.lower() for k in gov)
        if left_gov and not right_gov:
            candidate = right
        elif right_gov and not left_gov:
            candidate = left
        else:
            candidate = left if len(left) < len(right) else right
    else:
        candidate = name
    candidate = re.split(r'[;,]\s+(In the Matter of|in the matter of|Receiver)', candidate)[0]
    candidate = re.split(r'\s+\(', candidate)[0]
    candidate = candidate.strip()
    company_indicators = ['pty ltd', 'ltd', 'limited', 'inc', 'corp', 'corporation',
                          'llc', 'plc', 'group', 'holdings', 'trustee', 'trust',
                          'superannuation', 'nominees']
    is_company = any(ind in candidate.lower() for ind in company_indicators)
    words = candidate.split()
    if not is_company and len(words) >= 2:
        return words[-1]
    return candidate


@functools.lru_cache(maxsize=None)
def load_cases() -> list[dict]:
    cases = []
    for f in sorted(CASE_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            case_name = data.get("case_name", "Unknown")
            cases.append({
                "citation": data.get("citation", f.stem),
                "title": case_name,
                "short_name": short_case_name(case_name),
                "category": classify_case(case_name),
                "court": data.get("court", ""),
                "year": data.get("year", 0),
                "date": data.get("decision_date", ""),
                "source_url": data.get("source_url", ""),
            })
        except Exception:
            logger.exception("Error loading case %s", f.name)
    return cases


# ---------------------------------------------------------------------------
# Rulings
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _summary_title(stem: str) -> str | None:
    """Clean descriptive title from the ruling's summaries/<stem>.json if present."""
    import re as _re
    for cand in (stem, stem.replace("ATOID_", "AID_", 1)):
        try:
            p = RULING_DIR / "summaries" / f"{cand}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text(encoding="utf-8"))
            t = d.get("title")
            if t and len(t) < 800:
                # Strip leading citation prefix if the summary title embeds it
                # e.g. "AID 2001/302 — Superannuation..." -> "Superannuation..."
                t = _re.sub(r"^[A-Z]{2,6} \d{4}/\d+\s*[—\-–]?\s*", "", t).strip()
                return t or None
        except Exception:
            pass
    return None


@functools.lru_cache(maxsize=None)
def load_rulings() -> list[dict]:
    rulings = []
    for f in sorted(RULING_DIR.glob("*.txt")):
        if f.name.endswith(".meta.json"):
            continue
        try:
            meta_path = f.with_suffix(f.suffix + ".meta.json")
            if not meta_path.exists():
                meta_path = f.parent / (f.stem + ".txt.meta.json")
            title = f.stem
            year = 0
            ruling_type = "LCG"
            m = re.match(r'^([A-Za-z]+)_(\d{2,4})_(\d+)', f.stem)
            if m:
                ruling_type = m.group(1).upper()
                # Normalize PSLA → PS LA for display consistency
                if ruling_type == "PSLA":
                    ruling_type = "PS LA"
                # Normalize AID → ATOID for display
                if ruling_type == "AID":
                    ruling_type = "ATOID"
                year = int(m.group(2))
                # Normalise 2-digit years (98 → 1998, 04 → 2004)
                if year < 100:
                    year += 1900 if year >= 90 else 2000
            else:
                # Single-number format: IT_262, SGR_2006_1, etc.
                m2 = re.match(r'^([A-Za-z]+)_(\d+)$', f.stem)
                if m2:
                    ruling_type = m2.group(1).upper()
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                title = meta.get("title", title)
                ruling_type = meta.get("ruling_type") or meta.get("type") or ruling_type
                if meta.get("year"):
                    year = int(meta["year"])
                if meta.get("issue_date"):
                    dm = re.search(r'(\d{4})', str(meta.get("issue_date")))
                    if dm:
                        year = int(dm.group(1))
            content = f.read_text(encoding="utf-8")
            # Extract descriptive title from content (line after the ruling citation)
            full_title = title
            # CDN-0123: prefer clean title from summaries/<stem>.json when available
            summary_title = _summary_title(f.stem)
            # Strip ATO ID header lines before extracting title
            content_for_title = content
            if ruling_type == "PS LA" or ruling_type == "ATOID":
                # Remove known header lines
                ct_lines = content.splitlines()
                for ci, cl in enumerate(ct_lines):
                    if re.match(r'^(ATO\s+Interpretative\s+Decision|=+)$', cl.strip(), re.IGNORECASE):
                        continue
                    if re.match(r'^(File\s+Number|FOI\s+status)', cl.strip(), re.IGNORECASE):
                        continue
                    if not cl.strip():
                        continue
                    content_for_title = '\n'.join(ct_lines[ci:])
                    break
            lines = content_for_title.splitlines()
            for i, ln in enumerate(lines):
                ln = ln.strip()
                # Find the citation line, take the next non-empty line as the title
                _citation_re = r'^[A-Z]+ \d{4}/\d+'  # TR 2020/1, TD 1994/82, etc.
                _citation_2yr_re = r'^[A-Z]+ \d{2}/\d+'  # TD 94/82 (2-digit year)
                _citation_sequential_re = r'^[A-Z]+ \d+ -'  # IT 2346 - (sequential no year)
                _citation_ato_id_re = r'^ATO ID \d{4}/\d+'
                _citation_psla_re = r'^PS LA \d{4}/\d+'
                if re.match(_citation_re, ln) or re.match(_citation_2yr_re, ln) or re.match(_citation_sequential_re, ln) or re.match(_citation_ato_id_re, ln) or re.match(_citation_psla_re, ln) or re.match(r'^\w{2,4} \d{4}/\d+', ln):
                    # If the citation and title are on the same line (e.g. "IT 2346 - Income tax..."),
                    # extract the title directly from the citation line
                    title_from_citation = None
                    if ' - ' in ln:
                        title_from_citation = ln.split(' - ', 1)[1].strip()
                    for j in range(i + 1, min(i + 10, len(lines))):
                        next_ln = lines[j].strip()
                        if not next_ln:
                            continue
                        # Skip known header/boilerplate lines
                        if re.match(r'^(Keywords|Date of decision|SUBJECT|PURPOSE|Paragraph|FOI status|Issue|Decision|Facts|CAUTION|Download|Email|Print|Back to browse|Contents)', next_ln, re.IGNORECASE):
                            continue
                        # Skip single-word category headers (e.g. "Excise", "Income Tax")
                        if re.match(r'^[A-Z][a-z]+( [A-Z][a-z]+)?$', next_ln.strip()):
                            # Check if the next line is indented (actual title) - if so, skip this category header
                            if j + 1 < len(lines) and lines[j + 1].startswith(' ') and lines[j + 1].strip():
                                continue
                        if next_ln and not next_ln.startswith("Please") and not next_ln.startswith("PDF") and not next_ln.startswith("This ATO ID") and not next_ln.startswith("This document") and not re.match(_citation_re, next_ln) and not re.match(_citation_2yr_re, next_ln) and not re.match(r'^={3,}', next_ln):
                            full_title = next_ln
                            break
                    # If no title found on the next line, use the citation line's title (after " - ")
                    if full_title == title and title_from_citation:
                        full_title = title_from_citation
                    # CDN-0123: a single-line file means the "next line" never exists and
                    # title_from_citation can be a body fragment (first " - " deep in text).
                    # Fall back to the clean summary title when the extracted one looks wrong.
                    if (full_title == title or len(full_title) > 200) and summary_title:
                        full_title = summary_title
                    break
            withdrawn = _check_withdrawn(content)
            rulings.append({
                "citation": f.stem.replace("AID_", "ATOID_", 1) if f.stem.startswith("AID_") else f.stem,
                "title": title,
                "full_title": full_title,
                "type": ruling_type,
                "year": year,
                "withdrawn": withdrawn,
                "source": str(f),
                "preview": _strip_ato_chrome(content[:500]),
            })
        except Exception:
            logger.exception("Error loading ruling %s", f.name)
    for subdir in ["td", "tr", "pcg", "ps_la"]:
        p = ATO_RULING_DIR / subdir
        if not p.exists():
            continue
        for f in sorted(p.glob("*.txt")):
            try:
                content = f.read_text(encoding="utf-8")
                lines = content.splitlines()
                title = lines[0].strip() if lines else f.stem
                # Extract descriptive title: find the citation line, take next non-empty meaningful line
                full_title = title
                for i, ln in enumerate(lines):
                    ln = ln.strip()
                    _citation_re = r'^[A-Z]+ \d{4}/\d+'
                    _citation_2yr_re = r'^[A-Z]+ \d{2}/\d+'
                    if re.match(_citation_re, ln) or re.match(_citation_2yr_re, ln) or re.match(r'^\w{2,4} \d{4}/\d+', ln):
                        # If the citation and title are on the same line, extract from the citation line
                        title_from_citation = None
                        if ' - ' in ln:
                            title_from_citation = ln.split(' - ', 1)[1].strip()
                        for j in range(i + 1, min(i + 5, len(lines))):
                            next_ln = lines[j].strip()
                            if next_ln and not next_ln.startswith("Please") and not next_ln.startswith("PDF"):
                                full_title = next_ln
                                break
                        if full_title == title and title_from_citation:
                            full_title = title_from_citation
                        break
                year_match = re.search(r'(\d{4})', f.stem)
                year = int(year_match.group(1)) if year_match else 0
                rulings.append({
                    "citation": f.stem,
                    "title": title,
                    "full_title": full_title,
                    "type": subdir.upper().replace('_', ' '),
                    "year": year,
                    "withdrawn": _check_withdrawn(content),
                    "source": str(f),
                    "preview": _strip_ato_chrome(content[:500]),
                })
            except Exception:
                logger.exception("Error loading ATO ruling %s", f.name)

    # ── URL generators ────────────────────────────────────────────────────────
    _ato_doc_map = {
        "TR": "TXR",
        "TD": "TXD",
        "PCG": "COG",
        "LCG": "COG",
        "LCR": "COG",
        "PS LA": "ATOPSLA",
        "PS_LA": "ATOPSLA",
        "PSLA": "ATOPSLA",
        "GSTR": "GST",
        "MT": "MXR",
        "TA": "TPA",
        "SGR": "SGR",
        "AID": "AID",
        "ATOID": "AID",
        "CR": "CLR",
        "PR": "PRR",
    }

    def _ato_url(rtype: str, prefix: str, year: int | None, num: str) -> str | None:
        """Generate ATO URL — document viewer with PiT parameter.

        Format: law/view/document?DocID={code}/{prefix}{yr}{num}/NAT/ATO/00001&amp;PiT=99991231235958
        PiT=99991231235958 is the "latest point in time" parameter.
        Plain slashes work (no URL encoding needed).
        """
        if rtype == "IT":
            docid = f"ITR/IT{num}/NAT/ATO/00001"
        elif rtype in ("AID", "ATOID"):
            return f"https://www.ato.gov.au/law/view/document?docid=AID/AID{year}{num}/00001"
        else:
            code = _ato_doc_map.get(rtype)
            if not code:
                return None
            yr = str(year) if year else ""
            docid = f"{code}/{prefix}{yr}{num}/NAT/ATO/00001"
        return f"https://www.ato.gov.au/law/view/document?DocID={docid}&PiT=99991231235958"

    def _austlii_url(rtype: str, docid_num: str, year: int) -> str | None:
        ato_path_map = {
            "TR": f"ATOTR/{year}/TR{docid_num}.html",
            "TD": f"ATOTD/{year}/TD{docid_num}.html",
            "PCG": f"ATOPCG/{year}/PCG{docid_num}.html",
            "LCG": f"ATOLCG/{year}/LCG{docid_num}.html",
            "LCR": f"ATOLCR/{year}/LCR{docid_num}.html",
            "PR": f"ATOPR/{year}/PR{docid_num}.html",
            "CR": f"ATOCR/{year}/CR{docid_num}.html",
            "GSTR": f"ATOGSTR/{year}/GSTR{docid_num}.html",
            "MT": f"ATOMT/{year}/MT{docid_num}.html",
            "TA": f"ATOTA/{year}/TA{docid_num}.html",
            "SGR": f"ATOSGR/{year}/SGR{docid_num}.html",
            "ATOID": f"ATOAID/{year}/AID{docid_num}.html",
            "AID": f"ATOAID/{year}/AID{docid_num}.html",
            "PS LA": None,
            "PS_LA": None,
        }
        path = ato_path_map.get(rtype)
        if not path:
            return None
        return f"https://www8.austlii.edu.au/au/other/rulings/ato/{path}"

    for r in rulings:
        parts = r["citation"].split("_", 2)
        if len(parts) == 3:
            rtype, yr_raw, num = parts
            # Handle PS LA citations: "PS"_"LA"_"2011_10" → type="PS_LA", yr=2011, num=10
            if rtype.upper() == "PS" and yr_raw.upper() == "LA":
                rtype = "PSLA"
                yr_doc_num = num.split("_", 1)
                yr_raw = yr_doc_num[0]
                num = yr_doc_num[1] if len(yr_doc_num) > 1 else yr_doc_num[0]
            yr = str(r["year"]) if r["year"] else yr_raw
            # Build the docid number part: <year><num> with correct year width
            if rtype == "PSLA":
                r["citation_display"] = f"PS LA {yr}/{num}"
            elif rtype == "AID":
                r["citation_display"] = f"ATO ID {yr}/{num}"
            else:
                r["citation_display"] = f"{rtype} {yr}/{num}"
            yr_doc = str(r["year"])[-2:] if r["year"] and r["year"] < 2000 else str(r["year"]) if r["year"] else yr_raw
            docid_num = f"{yr_doc}{num}"
            r["ato_url"] = _ato_url(r["type"], rtype, r.get("year"), num) or ""
            r["austlii_url"] = _austlii_url(r["type"], docid_num, r["year"]) or ""
        elif len(parts) == 2 and parts[0].upper() == "IT":
            # IT rulings: IT_262 — sequential numbering, no year
            rtype, num = parts
            r["citation_display"] = f"IT {num}"
            # ATO URL: plain DocID with PiT parameter
            r["ato_url"] = f"https://www.ato.gov.au/law/view/document?DocID=ITR/IT{num}/NAT/ATO/00001&PiT=99991231235958"
            r["austlii_url"] = ""
        else:
            r["citation_display"] = r["citation"]
            r["ato_url"] = ""
            r["austlii_url"] = ""

    return rulings


@functools.lru_cache(maxsize=None)
def _load_ruling_section_index() -> dict[str, list[dict]]:
    path = DATA_DIR / "ruling_section_index.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_ruling_section_refs(citation: str) -> list[dict]:
    return _load_ruling_section_index().get(citation, [])


# ---------------------------------------------------------------------------
# Paragraph index
# ---------------------------------------------------------------------------

def slugify_cch(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s[:80]


@functools.lru_cache(maxsize=None)
def _load_paragraph_index() -> dict[str, dict]:
    paragraph_index: dict[str, dict] = {}
    for filename, pub_id in PUB_ACT_MAP.items():
        path = COMMENTARY_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for ch in data.get("chapters", []):
            for mh in ch.get("major_headings", []):
                para = mh.get("paragraph_number", "")
                heading = mh.get("title", "")
                sec_id = slugify_cch(heading) or f"ch-{ch.get('number', '')}-{len(paragraph_index)}"
                if para:
                    key = f"{pub_id}:{para}"
                    paragraph_index[key] = {
                        "act": pub_id,
                        "section": sec_id,
                        "title": heading,
                        "chapter": ch.get("number"),
                        "paragraph": para,
                    }
                for sh in mh.get("sub_headings", []):
                    sh_para = sh.get("paragraph_number", "")
                    if sh_para:
                        key = f"{pub_id}:{sh_para}"
                        paragraph_index[key] = {
                            "act": pub_id,
                            "section": sec_id,
                            "title": sh.get("title", heading),
                            "chapter": ch.get("number"),
                            "paragraph": sh_para,
                        }
    return paragraph_index


def get_paragraph_info(pub_id: str, para: str) -> dict | None:
    key = f"{pub_id}:{para}"
    return _load_paragraph_index().get(key)


# ---------------------------------------------------------------------------
# Section content
# ---------------------------------------------------------------------------

def find_section_path(act: str, section: str) -> str | None:
    tree = load_tree(act)
    for part in tree.get("parts", []):
        for sec in part.get("sections", []):
            if sec["id"].lower() == section.lower():
                return sec["path"]
        for div in part.get("divisions", []):
            for sec in div.get("sections", []):
                if sec["id"].lower() == section.lower():
                    return sec["path"]
            for sub in div.get("subdivisions", []):
                for sec in sub.get("sections", []):
                    if sec["id"].lower() == section.lower():
                        return sec["path"]
    return None


@functools.lru_cache(maxsize=None)
def get_act_section_content(act: str, section: str) -> tuple[dict, str]:
    section_path = find_section_path(act, section)
    # If no exact match in tree, try case-insensitive glob for markdown file
    if not section_path:
        for md in (DATA_DIR / act / "sections").rglob("*.md"):
            if md.stem.lower() == section.lower():
                section_path = str(md.relative_to(DATA_DIR / act / "sections"))
                break

    # If still no section_path, the section is not in the tree at all
    if not section_path:
        raise HTTPException(status_code=404, detail=f"Section {section} not found")

    md_path = DATA_DIR / act / "sections" / section_path
    if not md_path.exists():
        # This case handles when section_path was found via find_section_path (exact/case-insensitive),
        # but for some reason the file it pointed to doesn't exist.
        # Given find_section_path should point to existing files *or* we handled above for tree-only,
        # this might indicate a data inconsistency. For now, treat as tree-only.
        logger.warning("Section file '%s' expected at path '%s' not found. Returning empty content.", section, md_path)
        return {}, ""


    content = md_path.read_text(encoding="utf-8")
    content = _normalise_text(content)
    fm = {}
    body = content
    if content.startswith("---"):
        fm_end = re.search(r'\n---\s*\n', content)
        if fm_end:
            fm_text = content[3:fm_end.start()].strip()
            for line in fm_text.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"')
            body = content[fm_end.end():]

    return fm, body


@functools.lru_cache(maxsize=None)
def _definition_section_file(act: str, section: str) -> str | None:
    sections_dir = DATA_DIR / act / "sections"
    for f in sections_dir.rglob(f"{section}.md"):
        return str(f)
    return None


def get_definition_text(act: str, term: str) -> dict | None:
    act = resolve_act_id(act)
    defs = load_definitions(act)
    if not defs:
        return None
    info = defs.get(_normalize_term_key(term))
    if not info:
        return None
    section = info.get("section", "")
    if not section:
        return None

    md_file = _definition_section_file(act, section)
    if not md_file:
        return None
    md_path = Path(md_file)

    content = md_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        fm_end = re.search(r"\n---\s*\n", content)
        body = content[fm_end.end():] if fm_end else content
    else:
        body = content
    # Normalize Unicode apostrophes/quotes in body text to match term keys
    body = body.replace("\u2018", "'").replace("\u2019", "'")
    body = body.replace("\u201c", '"').replace("\u201d", '"')
    # Strip standalone asterisk markers — they're PDF cross-reference artifacts
    # that appear inline within terms (e.g. "*life insurance policies means")
    body = body.replace("*", "")

    term_lower = _normalize_term_key(term)
    escaped = re.escape(term_lower)
    # Patterns for definition anchors
    patterns = [
        rf'(?<!\w){escaped}(?:,\s[^.;\n]{{0,200}}?,)?\s+(?:has\s+(?:(?:the|a)\s+)?(?:same\s+)?meaning|is\s+defined\s+in|means|includes)(?:\s|:|$)',
        rf'(?<!\w){escaped}\s*:',
        # NZ IT Act 2007 style: "term— (a) means ..."
        rf'(?<!\w){escaped}\s*—',
    ]

    # Collect ALL matches so we can prefer the primary definition
    # over sub-definitions (e.g. prefer "dividend includes:" over
    # "demerger dividend means:...")
    candidates: list[tuple[re.Match, int]] = []
    for pat in patterns:
        for m in re.finditer(pat, body, re.IGNORECASE):
            before = body[max(0, m.start() - 60):m.start()].rstrip()
            is_primary = (
                m.start() == 0
                or before.endswith('.')
                or before.endswith('.\n')
                or before.endswith(';')
                or before.endswith('\n')
                or before.endswith(':')
                or not before
            )
            priority = 0 if is_primary else 1
            candidates.append((m, priority))

    if not candidates:
        return None

    # Sort: primary definitions first, then by position
    candidates.sort(key=lambda c: (c[1], c[0].start()))
    m = candidates[0][0]
    idx = m.start()

    # Find end: the boundary where this definition ends.
    # Strategy: Scan forward from the match position for:
    #   1. The next defined term in the same section (most reliable for dictionary-style sections)
    #   2. Next definition anchor (<a id="...">) or heading (####) — strong stop
    #   3. End of body
    rest = body[idx + len(m.group()):]

    # Use the sorted definitions index keys to determine the boundary.
    # Collect all terms in the same section, sort alphabetically,
    # and find the alphabetically-next term's definition anchor.
    end_pos = len(body)
    current_lower = _normalize_term_key(term)
    same_section_terms = sorted([
        t for t, info in defs.items()
        if info.get("section") == section
    ])
    try:
        cur_idx = same_section_terms.index(current_lower)
    except ValueError:
        cur_idx = -1
    if cur_idx >= 0 and cur_idx + 1 < len(same_section_terms):
        next_term = same_section_terms[cur_idx + 1]
        escaped_t = re.escape(next_term)
        term_match = re.search(
            rf'(?:\n(?:[-•*]\s+)?|\.\s+)({escaped_t}\s+(?:has\s+(?:(?:the|a)\s+)?(?:same\s+)?meaning|means|includes)(?:\s|:|$))',
            rest,
            re.IGNORECASE,
        )
        if not term_match:
            term_match = re.search(
                rf'(?:\n(?:[-•*]\s+)?|\.\s+)({escaped_t}\s*:)',
                rest,
                re.IGNORECASE,
            )
        if not term_match:
            term_match = re.search(
                rf'(?:\n(?:[-•*]\s+)?|\.\s+|:\s+)({escaped_t}\s*—)',
                rest,
                re.IGNORECASE,
            )
        if term_match:
            end_pos = idx + len(m.group()) + term_match.start()

    # Fallback: next definition anchor or heading
    if end_pos == len(body):
        anchor_end = re.search(r'\n(?:####?\s|<a\s+id=")', rest, re.IGNORECASE)
        if anchor_end:
            end_pos = idx + len(m.group()) + anchor_end.start()

    text = body[idx:end_pos].strip()
    # Hard cap at 5000 characters to prevent boundary-bleeding regression
    MAX_DEF_LENGTH = 5000
    if len(text) > MAX_DEF_LENGTH:
        text = text[:MAX_DEF_LENGTH]
    text = re.sub(r'<a id="[^"]+"></a>\s*\n?', "", text)
    text = re.sub(r">\s*", "", text)
    text = re.sub(r"\*\*\((\d+)\)\*\*\s*", r"(\1) ", text)
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Determine if the definition is a brief cross-reference
    # (e.g. "enterprise has the meaning given by section 9-20.")
    is_cross_ref = bool(re.match(
        r'^[^.]+\bhas\s+the\s+meaning\s+(given\s+by|in)\s',
        text,
        re.IGNORECASE,
    ))

    # Detect if text was truncated (doesn't end with sentence-ending punctuation)
    truncated = bool(text) and not re.search(r'[.\)"\'!?;]\s*$', text)

    return {
        "term": info.get("term", term),
        "act": act,
        "section": section,
        "anchor": info.get("anchor", ""),
        "text": text,
        "path": f"/{act}/s{section}#{info.get('anchor', '')}",
        "truncated": truncated,
        "is_cross_reference": is_cross_ref,
        "text_length": len(text),
    }


# What must follow a term for the occurrence to be a definition anchor.
# Allows an optional ", in relation to X," style qualifier before the verb.
_DEF_ANCHOR_SUFFIX = re.compile(
    r'(?:,\s[^.;\n]{0,200}?,)?'
    r'\s+(?:has\s+(?:(?:the|a)\s+)?(?:same\s+)?meaning|is\s+defined\s+in|means|includes)(?:\s|:|$)'
    r'|\s*:'
    r'|\s*—'
)


def _find_definition_start(key: str, body: str, pos: int) -> int | None:
    """First definition anchor for key at/after pos, preferring anchors at a
    sentence/line boundary; falls back to a full-body retry.

    Uses str.find for the term literal (re's scan is ~100x slower here) and
    validates each occurrence with a word-boundary check plus suffix regex.
    """
    for from_pos in (pos, 0) if pos else (0,):
        first_raw = None
        s = body.find(key, from_pos)
        checked = 0
        while s != -1 and checked < 200:
            checked += 1
            end = s + len(key)
            if (s == 0 or not (body[s - 1].isalnum() or body[s - 1] == "_")) \
                    and _DEF_ANCHOR_SUFFIX.match(body, end):
                if first_raw is None:
                    first_raw = s
                before = body[max(0, s - 60):s].rstrip()
                if not before or before[-1] in '.:;>"\n':
                    return s
            s = body.find(key, s + 1)
        if first_raw is not None:
            return first_raw
    return None


def _clean_definition_snippet(text: str) -> str:
    text = re.sub(r'<a id="[^"]+"></a>\s*\n?', "", text)
    text = re.sub(r">\s*", "", text)
    text = re.sub(r"\*\*\((\d+)\)\*\*\s*", r"(\1) ", text)
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\n{2,}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@functools.lru_cache(maxsize=32)
def _definitions_with_text_cached(act: str, mtime: float) -> tuple:
    raw_terms = _load_definitions_store().get(act, {}).get("terms", {})
    if not raw_terms:
        return ()

    # Group terms by defining section so each section body is scanned once,
    # in alphabetical (= document) order, instead of per-term full scans.
    by_section: dict[str, list[str]] = {}
    for term in raw_terms:
        by_section.setdefault(raw_terms[term].get("section", ""), []).append(term)

    MAX_DEF_LENGTH = 5000
    results = []
    for section, terms in by_section.items():
        texts: dict[str, str] = {}
        md_file = _definition_section_file(act, section) if section else None
        if md_file:
            body = Path(md_file).read_text(encoding="utf-8")
            if body.startswith("---"):
                fm_end = re.search(r"\n---\s*\n", body)
                if fm_end:
                    body = body[fm_end.end():]
            body = body.replace("‘", "'").replace("’", "'")
            body = body.replace("“", '"').replace("”", '"')
            body = body.replace("*", "")
            search_body = body.lower()
            if len(search_body) != len(body):  # pathological unicode lowering
                search_body = body

            # Dictionary sections list terms alphabetically, so scan forward
            # from the previous hit; fall back to a full search on a miss.
            ordered = sorted(terms, key=lambda t: _normalize_term_key(t))
            pos = 0
            starts: list[tuple[int, str]] = []
            for term in ordered:
                start = _find_definition_start(_normalize_term_key(term), search_body, pos)
                if start is not None:
                    starts.append((start, term))
                    pos = max(pos, start)
            starts.sort()
            for i, (start, term) in enumerate(starts):
                end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
                texts[term] = _clean_definition_snippet(body[start:end])[:MAX_DEF_LENGTH]

        for term in terms:
            info = raw_terms[term]
            results.append({
                "term": info.get("term", term),
                "section": _canon_section_id(section) if section else section,
                "anchor": info.get("anchor", ""),
                "text": texts.get(term) or info.get("definition", ""),
            })

    results.sort(key=lambda r: r["term"].lower())
    return tuple(results)


def load_definitions_with_text(act: str) -> list[dict]:
    """Every definition in an act with its resolved text, alphabetically."""
    act = resolve_act_id(act)
    path = _definitions_store_path()
    mtime = path.stat().st_mtime if path else 0.0
    return [dict(item) for item in _definitions_with_text_cached(act, mtime)]


def get_definition_across_acts(term: str, preferred_act: str | None = None) -> dict | None:
    """Look a term up across every act that carries a definitions index.

    Structural note: definitions do not live in a single place. ITAA 1997 and
    the GST Act each have a dictionary section (s 995-1 / s 195-1), but ITAA
    1936 scatters its definitions across the Act (s 6(1), s 317 for the CFC
    rules, s 318 for "associate", etc.), so a term absent from one act's index
    may be defined in another. Returning matches from all acts is an interim
    measure until the per-act indexes fully cover their scattered definitions.

    The requested act (if any) is returned as the primary match; other acts
    that define the same term are listed under ``also_defined_in``.
    """
    order: list[str] = []
    if preferred_act:
        order.append(preferred_act)
    for a in _all_definition_acts():
        if a not in order:
            order.append(a)

    matches: list[dict] = []
    for a in order:
        try:
            r = get_definition_text(a, term)
        except Exception:
            r = None
        if not r:
            # Plural fallback: index keys are singular (e.g. 'capital gain')
            singular = _singularise_term(term)
            if singular != term.strip():
                try:
                    r = get_definition_text(a, singular)
                except Exception:
                    r = None
        if r:
            matches.append(r)

    if not matches:
        return None

    primary = matches[0]
    return {
        **primary,
        "also_defined_in": [
            {
                "act": m["act"],
                "section": m["section"],
                "text": m["text"],
                "path": m.get("path", ""),
            }
            for m in matches[1:]
        ],
    }
