"""Quoting tool — standalone quote list with one-way PII anonymisation.

Not connected to the rest of the data model: quotes live in a single JSON
file (data/quotes.json). MCP tools quote_info / quote_fetch plus the REST
POST /api/quotes (and GET /api/quotes for inspection).

Anonymisation is ONE-WAY pseudonymisation ported from the firm's
file-anonymizer (same detection order and placeholder scheme, no mapping):
TFN/ABN/ACN/email/phone/PO Box/address/DOB/names -> [KIND_n].
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/quotes", tags=["quotes"])

QUOTES_FILE = Path(__file__).resolve().parents[2] / "data" / "quotes.json"
_lock = threading.Lock()

# ────────────────────────── anonymisation (one-way) ──────────────────────────

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# ABN/ACN BEFORE grouped TFN so their digit groups aren't eaten as TFNs.
ABN_RE = re.compile(r"\bABN\s*[: ]?\s*(\d{2}\s?\d{3}\s?\d{3}\s?\d{3})", re.I)
ACN_RE = re.compile(r"\bACN\s*[: ]?\s*(\d{3}\s?\d{3}\s?\d{3})", re.I)
TFN_GROUPED_RE = re.compile(r"\b\d{3}\s\d{3}\s\d{3}\b")
TFN_LABEL_RE = re.compile(r"\b(?:TFN|tax file number)\s*[: (]*(\d{3}[ -]?\d{3}[ -]?\d{3}|\d{9})", re.I)
MOBILE_RE = re.compile(r"(?<!\d)(?:\+61\s?|0)4\d{2}\s?\d{3}\s?\d{3}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)(?:\+61\s?|0)[2-8]\d?\s?\d{4}\s?\d{4}(?!\d)")
POBOX_RE = re.compile(r"\bPO\s?Box\s+\d+\b", re.I)
ADDR_RE = re.compile(
    r"\b\d+\s+[A-Z][A-Za-z'’-]*(?:[ ,]+[A-Z][A-Za-z'’-]*){0,4}"
    r"\s+(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\b"
)
STATE_POSTCODE_RE = re.compile(r"\b(?:NSW|VIC|QLD|SA|WA|TAS|NT|ACT)\s+\d{4}\b")
DOB_RE = re.compile(
    r"\b(?:born|DOB|date of birth)\s*[: (]+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})",
    re.I,
)
NAME_TITLE_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|A/Prof|Hon)\.?\s+([A-Z][A-Za-z'’-]+(?:[ \t]+[A-Z][A-Za-z'’-]+){0,3})"
)
DEAR_RE = re.compile(
    r"\bDear\s+(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|A/Prof|Hon)\.?\s+)?"
    r"([A-Z][A-Za-z'’-]+(?:[ \t]+[A-Z][A-Za-z'’-]+){0,3})",
    re.I,
)
LABEL_RE = re.compile(
    r"\b(?:Client|Taxpayer|Customer|Applicant|Respondent|Trustee|Beneficiary|Director|Partner|Employee)\s*[:.]?[ \t]+"
    r"([A-Z][A-Za-z'’-]+(?:[ \t]+[A-Z][A-Za-z'’-]+){0,3})",
    re.I,
)
SIGN_OFF_RE = re.compile(
    r"(?:Regards|Kind regards|Yours sincerely|Yours faithfully|Best regards)\s*[,:]?\s*"
    r"\n\s*([A-Z][A-Za-z'’-]+(?:[ \t]+[A-Z][A-Za-z'’-]+){0,2})"
)

# Order matters (same as file-anonymizer).
_DETECTORS = [
    ("ABN", ABN_RE),
    ("ACN", ACN_RE),
    ("TFN", TFN_GROUPED_RE),
    ("TFN", TFN_LABEL_RE),
    ("EMAIL", EMAIL_RE),
    ("PHONE", MOBILE_RE),
    ("PHONE", LANDLINE_RE),
    ("POBOX", POBOX_RE),
    ("ADDR", ADDR_RE),
    ("DOB", DOB_RE),
]


def anonymise_text(text: str, extra_names: list[str] | None = None) -> str:
    """Replace PII with [KIND_n] placeholders. One-way: no mapping kept."""
    counters: dict[str, int] = {}
    out = text

    def _ph(kind: str, original: str) -> str:
        counters[kind] = counters.get(kind, 0) + 1
        return f"[{kind}_{counters[kind]}]"

    for kind, rx in _DETECTORS:
        def _sub(m, kind=kind, rx=rx):
            if kind == "TFN" and rx is TFN_LABEL_RE:
                return m.group(0).replace(m.group(1), _ph("TFN", m.group(1)))
            if kind in ("ABN", "ACN"):
                return m.group(0).replace(m.group(1), _ph(kind, m.group(1)))
            if kind == "DOB":
                return m.group(0).replace(m.group(1), _ph("DOB", m.group(1)))
            return _ph(kind, m.group(0))

        out = rx.sub(_sub, out)

    for kind, rx in [("NAME", NAME_TITLE_RE), ("NAME", DEAR_RE), ("NAME", LABEL_RE), ("NAME", SIGN_OFF_RE)]:
        def _nsub(m, kind=kind, rx=rx):
            if rx is NAME_TITLE_RE:
                return _ph("NAME", m.group(0).strip())
            if rx is SIGN_OFF_RE:
                return m.group(0).replace(m.group(1), _ph("NAME", m.group(1))) if m.group(1) else m.group(0)
            return m.group(0).replace(m.group(1), _ph("NAME", m.group(1)))

        out = rx.sub(_nsub, out)

    out = STATE_POSTCODE_RE.sub(lambda m: _ph("ADDR", m.group(0)), out)

    # explicit names list (word-boundary, case-insensitive) — same behaviour
    # as the firm's file-anonymizer --names: zero false positives by design
    for name in (extra_names or []):
        name = name.strip()
        if name:
            out = re.sub(r"\b" + re.escape(name) + r"\b", lambda m: _ph("NAME", m.group(0)), out, flags=re.I)
    return out


# ────────────────────────── storage ──────────────────────────

def _load() -> list[dict]:
    if not QUOTES_FILE.exists():
        return []
    try:
        return json.loads(QUOTES_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save(quotes: list[dict]) -> None:
    QUOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUOTES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(quotes, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(QUOTES_FILE)


def add_quote(title: str, date: str, text: str, names: list[str] | None = None,
              tag: str | None = None, cost: str | None = None, currency: str | None = None,
              terms: str | None = None, alt: str | None = None) -> dict:
    quote = {
        "id": uuid.uuid4().hex[:12],
        "title": anonymise_text(title, names),
        "date": date.strip(),
        "text": anonymise_text(text, names),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    for key, val in (("tag", tag), ("cost", cost), ("currency", currency), ("terms", terms), ("alt", alt)):
        if val is not None and str(val).strip() != "":
            quote[key] = anonymise_text(str(val).strip(), names) if key == "alt" else str(val).strip()
    with _lock:
        quotes = _load()
        quotes.append(quote)
        _save(quotes)
    return quote


def quote_info() -> list[dict]:
    quotes = _load()
    return sorted(
        (
            {"id": q.get("id"), "title": q.get("title"), "date": q.get("date"), "text": q.get("text"),
             **{k: q.get(k) for k in ("tag", "cost", "currency", "terms", "alt") if q.get(k) is not None}}
            for q in quotes
        ),
        key=lambda q: (q.get("date") or ""),
    )


def quote_fetch(keyword: str, limit: int = 20) -> list[dict]:
    kw = (keyword or "").strip().lower()
    if not kw:
        return []
    scored = []
    for q in quote_info():
        title = (q.get("title") or "").lower()
        text = (q.get("text") or "").lower()
        score = title.count(kw) * 2 + text.count(kw)
        if score:
            scored.append((score, q))
    scored.sort(key=lambda t: -t[0])
    return [q for _, q in scored[:limit]]


# ────────────────────────── REST endpoints ──────────────────────────

class QuoteIn(BaseModel):
    title: str
    date: str
    text: str
    names: list[str] | None = None  # optional known names to mask (zero false positives)


@router.post("")
def create_quote(body: QuoteIn):
    if not body.title.strip() or not body.text.strip():
        raise HTTPException(status_code=400, detail="title and text are required")
    quote = add_quote(body.title, body.date, body.text, body.names)
    return {"ok": True, "anonymised": True, "quote": quote}


@router.get("")
def list_quotes():
    return {"quotes": quote_info()}
