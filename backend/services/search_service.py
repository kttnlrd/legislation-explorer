"""SQLite FTS5 search service."""
from __future__ import annotations
import json
import logging
import os
import re
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, RULING_DIR, SEARCH_DB, INSOLVENCY_DIR, TREATIES_DIR
from backend.services.data_loader import load_tree, get_act_section_content

logger = logging.getLogger(__name__)


@contextmanager
def search_conn():
    """Yield a fresh SQLite connection (per-request safety)."""
    conn = sqlite3.connect(str(SEARCH_DB))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_search_index() -> None:
    """Build or rebuild the FTS5 search index from sections, rulings, and cases.
    
    Uses WAL mode and explicit transactions so partial failures roll back
    cleanly instead of leaving a 0-byte/empty DB.
    """
    with search_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN")
        try:
            # --- Sections FTS ---
            conn.execute("DROP TABLE IF EXISTS sections_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE sections_fts USING fts5(
                    act, section, title, content,
                    tokenize='porter'
                )
            """)
            conn.execute("DROP TABLE IF EXISTS sections_meta")
            conn.execute("""
                CREATE TABLE sections_meta (
                    act TEXT, section TEXT, title TEXT, part TEXT, division TEXT,
                    UNIQUE (act, section)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_act_section ON sections_meta(act, section)")

            # Track (act, section_id) pairs already indexed so each section is
            # inserted exactly once (first occurrence wins for part/division
            # metadata).  Some tree.json files list the same section under
            # multiple parts/divisions, which previously produced duplicate rows
            # in both sections_fts and sections_meta and multiplied search hits.
            seen: set[tuple[str, str]] = set()

            for act_dir in DATA_DIR.iterdir():
                if not act_dir.is_dir() or not (act_dir / "tree.json").exists():
                    continue
                act = act_dir.name
                tree = load_tree(act)
                for part in tree.get("parts", []):
                    part_id = part.get("id", "")
                    for sec in part.get("sections", []):
                        _index_section(conn, act, sec, part_id, "", seen)
                    for div in part.get("divisions", []):
                        div_id = div.get("id", "")
                        for sec in div.get("sections", []):
                            _index_section(conn, act, sec, part_id, div_id, seen)
                        for sub in div.get("subdivisions", []):
                            for sec in sub.get("sections", []):
                                _index_section(conn, act, sec, part_id, div_id, seen)

            # --- Rulings FTS ---
            conn.execute("DROP TABLE IF EXISTS rulings_fts")
            conn.execute("""
                CREATE VIRTUAL TABLE rulings_fts USING fts5(
                    citation, title, content,
                    tokenize='porter'
                )
            """)
            conn.execute("DROP TABLE IF EXISTS rulings_meta")
            conn.execute("""
                CREATE TABLE rulings_meta (
                    citation TEXT UNIQUE, title TEXT, year INTEGER, ruling_type TEXT
                )
            """)

            ruled_seen: set[str] = set()
            for f in sorted(RULING_DIR.glob("*.txt")):
                if f.name.endswith(".meta.json") or f.name.startswith("."):
                    continue
                citation = f.stem
                if citation in ruled_seen:
                    continue
                ruled_seen.add(citation)

                title = citation
                year = 0
                ruling_type = ""
                m = re.match(r'^([A-Za-z]+)_(\d{2,4})_(\d+)', f.stem)
                if m:
                    ruling_type = m.group(1).upper()
                    year = int(m.group(2))
                    if year < 100:
                        year += 1900 if year >= 90 else 2000

                meta_path = f.with_suffix(f.suffix + ".meta.json")
                if not meta_path.exists():
                    meta_path = f.parent / (f.stem + ".txt.meta.json")
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    title = meta.get("title", citation)

                # Fallback: if title is still the citation (no meta), try summary file
                if title == citation:
                    summary_dir = DATA_DIR / "rulings" / "summaries"
                    summ_path = summary_dir / f"{citation}.json"
                    if summ_path.exists():
                        try:
                            summ_data = json.loads(summ_path.read_text(encoding="utf-8"))
                            title = summ_data.get("title", summ_data.get("subject", title))
                        except Exception:
                            pass

                content_raw = f.read_text(encoding="utf-8", errors="replace")
                content = re.sub(r'[#*`_\[\]\(\)]', ' ', content_raw)
                content = re.sub(r'\s+', ' ', content).strip()[:50000]

                conn.execute(
                    "INSERT INTO rulings_fts (citation, title, content) VALUES (?, ?, ?)",
                    (citation, title, content)
                )
                conn.execute(
                    "INSERT INTO rulings_meta (citation, title, year, ruling_type) VALUES (?, ?, ?, ?)",
                    (citation, title, year, ruling_type)
                )

            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("FTS index build failed, rolled back")
            raise

    # --- Insolvency textbook FTS ---
    if INSOLVENCY_DIR.exists():
        try:
            with search_conn() as conn:
                conn.execute("DROP TABLE IF EXISTS insolvency_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE insolvency_fts USING fts5(
                        chapter, title, content,
                        tokenize='porter'
                    )
                """)
                conn.execute("DROP TABLE IF EXISTS insolvency_meta")
                conn.execute("""
                    CREATE TABLE insolvency_meta (
                        chapter INTEGER UNIQUE, title TEXT, slug TEXT
                    )
                """)

                ch_tree_path = INSOLVENCY_DIR / "ch-tree.json"
                indexed_count = 0
                if ch_tree_path.exists():
                    ch_tree = json.loads(ch_tree_path.read_text(encoding="utf-8"))
                    for ch in ch_tree.get("chapters", []):
                        ch_file = INSOLVENCY_DIR / ch["file"]
                        if not ch_file.exists():
                            continue
                        content_raw = ch_file.read_text(encoding="utf-8", errors="replace")
                        # Strip YAML frontmatter
                        if content_raw.startswith("---"):
                            parts = content_raw.split("---", 2)
                            if len(parts) >= 3:
                                content_raw = parts[2].lstrip("\n")
                        content = re.sub(r'[#*`_\[\]\(\)]', ' ', content_raw)
                        content = re.sub(r'\s+', ' ', content).strip()[:50000]
                        conn.execute(
                            "INSERT INTO insolvency_fts (chapter, title, content) VALUES (?, ?, ?)",
                            (str(ch["chapter"]), ch["title"], content)
                        )
                        conn.execute(
                            "INSERT INTO insolvency_meta (chapter, title, slug) VALUES (?, ?, ?)",
                            (ch["chapter"], ch["title"], ch["slug"])
                        )
                    indexed_count = len(ch_tree.get("chapters", []))
                conn.commit()
                logger.info(f"Insolvency FTS indexed: {indexed_count} chapters")
        except Exception:
            logger.exception("Insolvency FTS index failed (non-fatal)")

    # --- Tax Treaties FTS ---
    if TREATIES_DIR.exists():
        try:
            with search_conn() as conn:
                conn.execute("DROP TABLE IF EXISTS treaties_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE treaties_fts USING fts5(
                        country, article, title, content,
                        tokenize='porter'
                    )
                """)
                conn.execute("DROP TABLE IF EXISTS treaties_meta")
                conn.execute("""
                    CREATE TABLE treaties_meta (
                        country TEXT, article INTEGER,
                        country_slug TEXT, title TEXT, slug TEXT,
                        UNIQUE (country_slug, article)
                    )
                """)
                conn.execute("BEGIN")
                indexed_count = 0
                for country_dir in sorted(TREATIES_DIR.iterdir()):
                    if not country_dir.is_dir():
                        continue
                    tree_path = country_dir / "tree.json"
                    if not tree_path.exists():
                        continue
                    try:
                        tree = json.loads(tree_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    country_slug = country_dir.name
                    country_name = tree.get("treaty", country_slug)
                    for art in tree.get("articles", []):
                        art_file = country_dir / art["file"]
                        if not art_file.exists():
                            continue
                        raw = art_file.read_text(encoding="utf-8", errors="replace")
                        # Strip YAML frontmatter
                        if raw.startswith("---"):
                            parts = raw.split("---", 2)
                            if len(parts) >= 3:
                                raw = parts[2].lstrip("\n")
                        content = re.sub(r'[#*`_\[\]\(\)]', ' ', raw)
                        content = re.sub(r'\s+', ' ', content).strip()[:50000]
                        unique_art_id = hash(f"{country_slug}/{art['article']}")
                        conn.execute(
                            "INSERT INTO treaties_fts (country, article, title, content) VALUES (?, ?, ?, ?)",
                            (country_name, str(art["article"]), art["title"], content)
                        )
                        conn.execute(
                            "INSERT INTO treaties_meta (country, article, country_slug, title, slug) VALUES (?, ?, ?, ?, ?)",
                            (country_name, art["article"], country_slug, art["title"], art["slug"])
                        )
                        indexed_count += 1
                conn.commit()
                logger.info(f"Treaties FTS indexed: {indexed_count} articles across {len([d for d in TREATIES_DIR.iterdir() if d.is_dir()])} countries")
        except Exception:
            logger.exception("Treaties FTS index failed (non-fatal)")

    # --- Case summaries FTS ---
    SUMMARIES_DIR = DATA_DIR / ".." / "scripts" / "cleaned" / "summaries"
    if SUMMARIES_DIR.exists():
        try:
            with search_conn() as conn:
                conn.execute("DROP TABLE IF EXISTS case_summaries_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE case_summaries_fts USING fts5(
                        citation, case_name, court, text,
                        tokenize='porter'
                    )
                """)
                conn.execute("BEGIN")
                count = 0
                for f in sorted(os.listdir(str(SUMMARIES_DIR))):
                    if not f.endswith(".json"):
                        continue
                    try:
                        with open(SUMMARIES_DIR / f) as fh:
                            s = json.load(fh)
                    except Exception:
                        continue
                    citation = s.get("citation", "")
                    case_name = s.get("case_name", "") or s.get("title", "")
                    court = s.get("court", "")
                    text_parts = [
                        s.get("facts", ""),
                        s.get("held", ""),
                        s.get("reasoning", ""),
                        s.get("outcome", ""),
                    ]
                    for lst_key in ("issues", "cases_cited", "legislation_cited"):
                        val = s.get(lst_key, [])
                        if isinstance(val, list):
                            text_parts.extend(str(item) for item in val if isinstance(item, str))
                        elif isinstance(val, str):
                            text_parts.append(val)
                    text = re.sub(r'\s+', ' ', " ".join(text_parts)).strip()
                    if text:
                        conn.execute(
                            "INSERT INTO case_summaries_fts (citation, case_name, court, text) VALUES (?, ?, ?, ?)",
                            (citation, case_name, court, text)
                        )
                        count += 1
                conn.commit()
                logger.info(f"Case summaries FTS indexed: {count} cases")
        except Exception:
            logger.exception("Case summaries FTS index failed (non-fatal)")

    logger.info(f"Search index built: {SEARCH_DB}")


def _index_section(
    conn: sqlite3.Connection,
    act: str,
    sec: dict,
    part: str,
    division: str,
    seen: set[tuple[str, str]],
) -> None:
    sec_id = sec["id"]
    key = (act, sec_id)
    if key in seen:
        return
    seen.add(key)

    title = sec.get("title", "")
    try:
        fm, content_body = get_act_section_content(act, sec_id)
    except Exception:
        logger.exception(f"Error getting section content for {act}/{sec_id}")
        content_body = ""

    content = re.sub(r'[#*`_\[\]\(\)]', ' ', content_body)
    content = re.sub(r'\s+', ' ', content).strip()[:50000]

    conn.execute(
        "INSERT INTO sections_fts (act, section, title, content) VALUES (?, ?, ?, ?)",
        (act, sec_id, title, content)
    )
    conn.execute(
        "INSERT INTO sections_meta (act, section, title, part, division) VALUES (?, ?, ?, ?, ?)",
        (act, sec_id, title, part, division)
    )


# Tax-terminology synonyms. Applied to unquoted query text only, whole words only.
SYNONYMS = {
    "main residence": ["principal place of residence", "PPOR", "family home"],
    "cgt": ["capital gains tax", "capital gain"],
    "rollover": ["roll-over", "roll over"],
    "personal services income": ["PSI"],
    "psi": ["personal services income"],
    "input tax credit": ["ITC"],
    "imputation": ["franking", "dividend imputation"],
    "small business": ["SBE"],
    "employee share scheme": ["ESS"],
    "deceased estate": ["estate of a deceased person"],
    "trading stock": ["stock in trade", "inventory"],
    "superannuation": ["super", "SMSF"],
    "margin scheme": ["GST margin"],
    "non-commercial loss": ["hobby loss"],
    "foreign resident": ["non-resident", "nonresident"],
}
# Longest keys first so "personal services income" wins over a shorter overlap.
_SYNONYM_RE = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in sorted(SYNONYMS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)


def _fts_phrase(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _expand_query(q: str, operator: str = "AND") -> str:
    """Build the FTS5 MATCH string: quoted phrases pass through untouched,
    recognised terms in the free text become OR-groups with their synonyms.
    operator='OR' joins top-level terms with OR instead of AND."""
    out: list[str] = []
    for phrase, word in re.findall(r'"([^"]*)"|(\S+)', q):
        if phrase:
            out.append(_fts_phrase(phrase))
        elif word.endswith('*') and len(word) > 1:
            out.append(_fts_phrase(word[:-1]) + '*')
        else:
            out.append(word)
    # Synonym expansion runs over the free-text run only (quoted parts are already
    # emitted as phrases and never re-matched).
    expanded: list[str] = []
    buf: list[str] = []
    covered: set[str] = set()

    def flush():
        if not buf:
            return
        text = ' '.join(buf)
        buf.clear()
        pos = 0
        for m in _SYNONYM_RE.finditer(text):
            for w in text[pos:m.start()].split():
                expanded.append(_fts_phrase(w))
            alts = [m.group(1)] + SYNONYMS[m.group(1).lower()]
            covered.update(a.lower() for a in alts)
            expanded.append('(' + ' OR '.join(_fts_phrase(a) for a in alts) + ')')
            pos = m.end()
        for w in text[pos:].split():
            expanded.append(_fts_phrase(w))

    for tok in out:
        if tok.startswith('"') or tok.startswith('('):
            flush()
            expanded.append(tok)
        else:
            buf.append(tok)
    flush()
    # A bare word already inside a synonym group would AND it back in and undo
    # the expansion ("employee share scheme ESS" must not require the token ESS).
    expanded = [t for t in expanded if t.strip('"').lower() not in covered or t.startswith('(')]
    return (' OR ' if operator == "OR" else ' AND ').join(expanded)


# Title matches outrank body-only matches. Columns: act, section, title, content.
_BM25 = "bm25(sections_fts, 0.0, 1.0, 10.0, 1.0)"

_CITATION_RE = re.compile(
    r'^\s*(?:s|ss|sec|section)?\s*\.?\s*(\d+[A-Za-z]*(?:-\d+[A-Za-z]*)?(?:\(\d+[A-Za-z]*\))*)\s*$',
    re.IGNORECASE,
)


def search_section_ids(q: str, act: str | None = None, limit: int = 20) -> list[dict]:
    """Citation-style lookup: 's 118-110', '118-110', 's 6(1)' → exact then prefix
    matches on the section id. Returns [] for anything that isn't a citation."""
    m = _CITATION_RE.match(q)
    if not m:
        return []
    sid = m.group(1)
    sql = (
        "SELECT act, section, title, part, division FROM sections_meta "
        "WHERE (section = ?1 COLLATE NOCASE OR section LIKE ?1 || '%' COLLATE NOCASE) "
        + ("AND act = ?3 " if act else "")
        + "ORDER BY (section = ?1 COLLATE NOCASE) DESC, length(section), act LIMIT ?2"
    )
    params: tuple = (sid, limit, act) if act else (sid, limit)
    with search_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {"act": r["act"], "section": r["section"], "title": r["title"],
         "part": r["part"], "division": r["division"], "snippet": ""}
        for r in rows
    ]


def search_sections(q: str, act: str | None = None, limit: int = 50,
                    operator: str = "AND") -> dict:
    """Search using SQLite FTS5 with BM25 ranking.

    Supports double-quoted phrase matching for exact literal search
    (e.g. '"distributable surplus"' matches sections containing that
    exact substring via LIKE, bypassing FTS5 stemming entirely).
    Unquoted multi-word queries use standard FTS5 matching: AND by
    default, OR when operator='OR'.
    """
    # Detect fully quoted phrase — use LIKE for exact literal match
    phrase_match = re.match(r'^\s*"(.+)"\s*$', q)
    if phrase_match:
        exact_q = phrase_match.group(1)
        with search_conn() as conn:
            if act:
                rows = conn.execute(
                    "SELECT s.act, s.section, s.title, "
                    "m.part, m.division, "
                    "0.0 as rank, '' as snippet "
                    "FROM sections_fts s "
                    "JOIN sections_meta m ON s.act = m.act AND s.section = m.section "
                    "WHERE s.act = ? AND (s.content LIKE ? OR s.title LIKE ?) "
                    "ORDER BY CASE WHEN s.title LIKE ? THEN 0 ELSE 1 END "
                    "LIMIT ?",
                    (act, f"%{exact_q}%", f"%{exact_q}%", f"%{exact_q}%", limit),
                ).fetchall()
                total_count = conn.execute(
                    "SELECT COUNT(*) FROM sections_fts WHERE act = ? AND (content LIKE ? OR title LIKE ?)",
                    (act, f"%{exact_q}%", f"%{exact_q}%"),
                ).fetchone()[0]
            else:
                rows = conn.execute(
                    "SELECT s.act, s.section, s.title, "
                    "m.part, m.division, "
                    "0.0 as rank, '' as snippet "
                    "FROM sections_fts s "
                    "JOIN sections_meta m ON s.act = m.act AND s.section = m.section "
                    "WHERE s.content LIKE ? OR s.title LIKE ? "
                    "ORDER BY CASE WHEN s.title LIKE ? THEN 0 ELSE 1 END "
                    "LIMIT ?",
                    (f"%{exact_q}%", f"%{exact_q}%", f"%{exact_q}%", limit),
                ).fetchall()
                total_count = conn.execute(
                    "SELECT COUNT(*) FROM sections_fts WHERE content LIKE ? OR title LIKE ?",
                    (f"%{exact_q}%", f"%{exact_q}%"),
                ).fetchone()[0]
        results = []
        for row in rows:
            results.append({
                "act": row["act"],
                "section": row["section"],
                "title": row["title"],
                "part": row["part"],
                "division": row["division"],
                "snippet": "",
            })
        return {"results": results, "total_count": total_count}

    # Standard FTS5 token-based matching
    if not q.strip():
        return {"results": [], "total_count": 0}
    q_clean = _expand_query(q, operator)
    if not q_clean:
        return {"results": [], "total_count": 0}

    with search_conn() as conn:
        if act:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM sections_fts WHERE sections_fts MATCH ? AND sections_fts.act = ?",
                (q_clean, act)
            ).fetchone()
            total_count = count_row[0] if count_row else 0
            sql = """
                SELECT sections_fts.act, sections_fts.section, sections_fts.title,
                       m.part, m.division,
                       bm25(sections_fts, 0.0, 1.0, 10.0, 1.0) as rank, snippet(sections_fts, 3, '<mark>', '</mark>', '...', 32) as snippet
                FROM sections_fts
                JOIN sections_meta m ON sections_fts.act = m.act AND sections_fts.section = m.section
                WHERE sections_fts MATCH ? AND sections_fts.act = ?
                ORDER BY bm25(sections_fts, 0.0, 1.0, 10.0, 1.0)
                LIMIT ?
            """
            rows = conn.execute(sql, (q_clean, act, limit)).fetchall()
        else:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM sections_fts WHERE sections_fts MATCH ?",
                (q_clean,)
            ).fetchone()
            total_count = count_row[0] if count_row else 0
            sql = """
                SELECT sections_fts.act, sections_fts.section, sections_fts.title,
                       m.part, m.division,
                       bm25(sections_fts, 0.0, 1.0, 10.0, 1.0) as rank, snippet(sections_fts, 3, '<mark>', '</mark>', '...', 32) as snippet
                FROM sections_fts
                JOIN sections_meta m ON sections_fts.act = m.act AND sections_fts.section = m.section
                WHERE sections_fts MATCH ?
                ORDER BY bm25(sections_fts, 0.0, 1.0, 10.0, 1.0)
                LIMIT ?
            """
            rows = conn.execute(sql, (q_clean, limit)).fetchall()

    results = []
    for row in rows:
        results.append({
            "act": row["act"],
            "section": row["section"],
            "title": row["title"],
            "part": row["part"],
            "division": row["division"],
            "snippet": row["snippet"] or "",
        })

    # If query looks like a section number, exact-match it to rank 1
    section_re = re.match(r'^(\d+[A-Z]?-\d+(?:[A-Za-z]*(?:\(\d+(?:\)[a-z])?\))?)?)$', q.strip())
    if section_re:
        section_id = section_re.group(1)
        with search_conn() as conn:
            if act:
                exact = conn.execute(
                    "SELECT act, section, sections_fts.title, part, division, "
                    "snippet(sections_fts, 3, '<mark>', '</mark>', '...', 32) as snippet "
                    "FROM sections_fts JOIN sections_meta m USING(act, section) "
                    "WHERE sections_fts.act = ? AND sections_fts.section = ?",
                    (act, section_id)
                ).fetchone()
            else:
                exact = conn.execute(
                    "SELECT act, section, sections_fts.title, part, division, "
                    "snippet(sections_fts, 3, '<mark>', '</mark>', '...', 32) as snippet "
                    "FROM sections_fts JOIN sections_meta m USING(act, section) "
                    "WHERE sections_fts.section = ?",
                    (section_id,)
                ).fetchone()
        if exact:
            results = [
                {
                    "act": exact["act"],
                    "section": exact["section"],
                    "title": exact["title"],
                    "part": exact["part"],
                    "division": exact["division"],
                    "snippet": exact["snippet"] or "",
                }
            ] + [
                r for r in results
                if not (r["act"] == exact["act"] and r["section"] == exact["section"])
            ]

    return {"results": results[:limit], "total_count": total_count}


_PREFIX_TYPE_MAP = {
    "TR": "Taxation Ruling",
    "TD": "Taxation Determination",
    "IT": "Taxation Ruling",
    "CR": "Class Ruling",
    "GSTR": "Goods and Services Tax Ruling",
    "LCG": "Law Companion Ruling",
    "PCG": "Practical Compliance Guideline",
    "MT": "Miscellaneous Taxation Ruling",
    "PR": "Product Ruling",
    "PS": "Practice Statement Law Administration",
    "PSLA": "Practice Statement Law Administration",
    "SGR": "Superannuation Guarantee Ruling",
    "TA": "Taxpayer Alert",
    "AID": "ATO Interpretative Decision",
}

def _citation_to_display(citation: str) -> str:
    """Convert internal citation format to display format.
    e.g. 'TR_2012_1' → 'TR 2012/1', 'IT_342' → 'IT 342'
    """
    # Year-based citations: TR_2012_1 → TR 2012/1
    m = re.match(r'^([A-Za-z]+)_(\d{4})_(\d+)$', citation)
    if m:
        return f"{m.group(1)} {m.group(2)}/{m.group(3)}"
    # Number-based citations: IT_342 → IT 342
    m = re.match(r'^([A-Za-z]+)_(\d+)$', citation)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return citation.replace("_", " ")

def _ruling_type_from_citation(citation: str) -> str:
    """Derive the canonical ruling type from the citation prefix."""
    m = re.match(r'^([A-Za-z]+)', citation.strip())
    if m:
        return _PREFIX_TYPE_MAP.get(m.group(1).upper(), "")
    return ""


def search_rulings(q: str, limit: int = 20, operator: str = "AND") -> list[dict]:
    """Search rulings using FTS5 BM25 ranking with exact-match boost."""
    tokens = q.split()
    if not tokens:
        return []

    # --- Exact citation match (boost to rank 1) ---
    # Normalize spaces/slashes to underscore format stored in DB
    # e.g. "IT 342" → "IT_342", "TR 2012/1" → "TR_2012_1"
    norm = q.strip().replace(" ", "_").replace("/", "_")
    exact_row = None
    try:
        with search_conn() as conn:
            exact_row = conn.execute(
                "SELECT citation, title, year, ruling_type FROM rulings_meta WHERE citation = ?",
                (norm,)
            ).fetchone()
    except Exception:
        pass

    # --- FTS5 search ---
    quoted = []
    for tok in tokens:
        if tok.endswith('*') and len(tok) > 1:
            inner = tok[:-1].replace('"', '""')
            quoted.append(f'"{inner}"*')
        else:
            quoted.append('"' + tok.replace('"', '""') + '"')
    q_clean = (' OR ' if operator == "OR" else ' ').join(quoted)

    with search_conn() as conn:
        sql = """SELECT rulings_fts.citation, rulings_fts.title,
                       m.year, m.ruling_type,
                       rank, snippet(rulings_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
                FROM rulings_fts
                JOIN rulings_meta m ON rulings_fts.citation = m.citation
                WHERE rulings_fts MATCH ?
                ORDER BY rank
                LIMIT ?"""
        rows = conn.execute(sql, (q_clean, limit)).fetchall()

    # --- LIKE fallback for citation-bound queries FTS5 misses ---
    # FTS5 porter tokenizer treats underscores as part of the token,
    # so "IT 342" (tokenized as "it", "342") won't match "IT_342" (token "IT_342").
    # Fall back to LIKE on citation and content when FTS returns nothing
    # or the query looks like a ruling reference.
    if len(rows) == 0 or re.match(r'^[A-Za-z]+[\s_/]', q.strip()):
        try:
            with search_conn() as conn:
                like_pat = f"%{norm.replace('_', '%')}%"
                like_rows = conn.execute(
                    """SELECT r.citation, r.title, m.year, m.ruling_type,
                              0.0 as rank, '' as snippet
                       FROM rulings_fts r
                       JOIN rulings_meta m ON r.citation = m.citation
                       WHERE r.citation LIKE ? OR r.content LIKE ?
                       ORDER BY CASE WHEN r.citation = ? THEN 0
                                     WHEN r.citation LIKE ? THEN 1
                                     ELSE 2 END
                       LIMIT ?""",
                    (like_pat, like_pat, norm, f"{norm.split('_')[0] if '_' in norm else norm}%", limit)
                ).fetchall()
                if like_rows:
                    # Merge: insert LIKE results that aren't already in FTS results
                    existing = {r[0] for r in rows}
                    for lr in like_rows:
                        if lr[0] not in existing:
                            rows.append(lr)
                            existing.add(lr[0])
        except Exception:
            pass

    results = []
    for row in rows:
        title = row["title"]
        if title == row["citation"]:
            summary_dir = Path(DATA_DIR) / "rulings" / "summaries"
            summ_path = summary_dir / f'{row["citation"].replace("/", "_")}.json'
            if summ_path.exists():
                try:
                    meta = json.loads(summ_path.read_text(encoding="utf-8"))
                    title = meta.get("title", meta.get("subject", title))
                except Exception:
                    pass
        results.append({
            "act": "rulings",
            "section": _citation_to_display(row["citation"]),
            "title": title,
            "citation": row["citation"],
            "year": row["year"],
            "ruling_type": _ruling_type_from_citation(row["citation"]) or row["ruling_type"],
            "snippet": row["snippet"] or "",
        })

    # Pin exact match to rank 1 if found
    if exact_row:
        exact_citation = exact_row["citation"]
        # Remove any existing entry for the exact match
        results = [r for r in results if r["section"] != exact_citation]
        title = exact_row["title"]
        if title == exact_citation:
            summary_dir = Path(DATA_DIR) / "rulings" / "summaries"
            summ_path = summary_dir / f'{exact_citation.replace("/", "_")}.json'
            if summ_path.exists():
                try:
                    meta = json.loads(summ_path.read_text(encoding="utf-8"))
                    title = meta.get("title", meta.get("subject", title))
                except Exception:
                    pass
        results.insert(0, {
            "act": "rulings",
            "section": _citation_to_display(exact_citation),
            "title": title,
            "citation": exact_citation,
            "year": exact_row["year"],
            "ruling_type": _ruling_type_from_citation(exact_citation) or exact_row["ruling_type"],
            "snippet": "",
        })

    return results[:limit]


def search_cases(q: str, limit: int = 20) -> list[dict]:
    """Search case summaries using FTS5 BM25 ranking."""
    tokens = q.split()
    if not tokens:
        return []
    quoted = []
    for tok in tokens:
        if tok.endswith('*') and len(tok) > 1:
            inner = tok[:-1].replace('"', '""')
            quoted.append(f'"{inner}"*')
        else:
            quoted.append('"' + tok.replace('"', '""') + '"')
    q_clean = ' '.join(quoted)

    with search_conn() as conn:
        try:
            sql = """
                SELECT citation, case_name, court,
                       rank, snippet(case_summaries_fts, 3, '<mark>', '</mark>', '...', 32) as snippet
                FROM case_summaries_fts
                WHERE case_summaries_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (q_clean, limit)).fetchall()
        except Exception:
            rows = []
    results = []
    for row in rows:
        results.append({
            "act": "tax-cases",
            "section": row["citation"],
            "title": row["case_name"],
            "court": row["court"],
            "snippet": row["snippet"] or "",
        })
    return results


def search_insolvency(q: str, limit: int = 20) -> dict:
    """Search insolvency textbook chapters using FTS5 BM25 ranking."""
    tokens = q.split()
    if not tokens:
        return {"results": [], "total": 0}
    quoted = []
    for tok in tokens:
        if tok.endswith('*') and len(tok) > 1:
            inner = tok[:-1].replace('"', '""')
            quoted.append(f'"{inner}"*')
        else:
            quoted.append('"' + tok.replace('"', '""') + '"')
    q_clean = ' '.join(quoted)

    with search_conn() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM insolvency_fts WHERE insolvency_fts MATCH ?",
            (q_clean,)
        ).fetchone()
        total = count_row[0] if count_row else 0
        sql = """
            SELECT insolvency_fts.chapter, insolvency_fts.title,
                   m.slug,
                   rank, snippet(insolvency_fts, 2, '<mark>', '</mark>', '...', 32) as snippet
            FROM insolvency_fts
            JOIN insolvency_meta m ON insolvency_fts.chapter = m.chapter
            WHERE insolvency_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        rows = conn.execute(sql, (q_clean, limit)).fetchall()

    results = []
    for row in rows:
        results.append({
            "chapter": int(row["chapter"]),
            "title": row["title"],
            "slug": row["slug"],
            "snippet": row["snippet"] or "",
        })
    return {"results": results, "total": total}


def search_treaties(q: str, limit: int = 20) -> dict:
    """Search treaty articles using FTS5 BM25 ranking."""
    tokens = q.split()
    if not tokens:
        return {"results": [], "total": 0}
    quoted = []
    for tok in tokens:
        if tok.endswith('*') and len(tok) > 1:
            inner = tok[:-1].replace('"', '""')
            quoted.append(f'"{inner}"*')
        else:
            quoted.append('"' + tok.replace('"', '""') + '"')
    q_clean = ' '.join(quoted)

    with search_conn() as conn:
        count_row = conn.execute(
            "SELECT COUNT(*) FROM treaties_fts WHERE treaties_fts MATCH ?",
            (q_clean,)
        ).fetchone()
        total = count_row[0] if count_row else 0
        sql = """
            SELECT treaties_fts.country, treaties_fts.article, treaties_fts.title,
                   m.country_slug, m.slug,
                   rank, snippet(treaties_fts, 3, '<mark>', '</mark>', '...', 32) as snippet
            FROM treaties_fts
            JOIN treaties_meta m ON treaties_fts.article = m.article AND treaties_fts.country = m.country
            WHERE treaties_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """
        rows = conn.execute(sql, (q_clean, limit)).fetchall()

    results = []
    for row in rows:
        results.append({
            "country": row["country"],
            "country_slug": row["country_slug"],
            "article": int(row["article"]) if row["article"] else 0,
            "title": row["title"],
            "slug": row["slug"],
            "snippet": row["snippet"] or "",
        })
    return {"results": results, "total": total}


def get_insolvency_chapter(chapter: int) -> dict | None:
    """Get full chapter text by chapter number."""
    import json
    ch_tree_path = INSOLVENCY_DIR / "ch-tree.json"
    if not ch_tree_path.exists():
        return None
    ch_tree = json.loads(ch_tree_path.read_text(encoding="utf-8"))
    ch_info = None
    for ch in ch_tree.get("chapters", []):
        if ch["chapter"] == chapter:
            ch_info = ch
            break
    if not ch_info:
        return None
    ch_file = INSOLVENCY_DIR / ch_info["file"]
    if not ch_file.exists():
        return None
    content = ch_file.read_text(encoding="utf-8", errors="replace")
    # Strip YAML frontmatter if present
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2].lstrip("\n")
    return {
        "chapter": ch_info["chapter"],
        "title": ch_info["title"],
        "slug": ch_info["slug"],
        "content": content,
    }


def search_cases_fts(q: str, limit: int = 20, operator: str = "AND") -> list[dict]:
    """Search case summaries using FTS5 BM25 ranking.

    Returns list of dicts with citation, case_name, court, has_summary=True.
    """
    tokens = q.split()
    if not tokens:
        return []
    quoted = []
    for tok in tokens:
        if tok.endswith('*') and len(tok) > 1:
            inner = tok[:-1].replace('"', '""')
            quoted.append(f'"{inner}"*')
        else:
            quoted.append('"' + tok.replace('"', '""') + '"')
    q_clean = (' OR ' if operator == "OR" else ' ').join(quoted)
    from urllib.parse import quote

    with search_conn() as conn:
        try:
            rows = conn.execute(
                "SELECT citation, case_name, court, rank "
                "FROM case_summaries_fts WHERE case_summaries_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (q_clean, limit)
            ).fetchall()
        except Exception:
            rows = []

        # If strict quoted-AND query returns nothing, fall back to unquoted OR
        if not rows and len(tokens) > 1:
            try:
                loose = ' OR '.join(t.replace('-', ' ').replace('"', '""') for t in tokens)
                rows = conn.execute(
                    "SELECT citation, case_name, court, rank "
                    "FROM case_summaries_fts WHERE case_summaries_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (loose, limit)
                ).fetchall()
            except Exception:
                rows = []

    results = []
    for row in rows:
        results.append({
            "citation": row["citation"],
            "case_name": row["case_name"],
            "court": row["court"],
            "year": row["citation"][1:5] if row["citation"].startswith("[") else "",
            "has_summary": True,
            "html_url": f"https://legislation.scriptkitty.yachts/tax-cases/{quote(row['citation'])}",
        })
    return results
