"""Proposed-law tracker: items Harry adds as measures are announced/developing.

Store: data/proposed-law/items.json (plain array, newest first).
Statuses: announced | exposure_draft | before_parliament | passed | enacted | withdrawn
Measure types: bill | exposure_draft | announcement | ato_draft | other
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[2] / "data" / "proposed-law"
ITEMS_FILE = DATA / "items.json"

router = APIRouter(prefix="/api/proposed-law", tags=["proposed-law"])

STATUSES = {"announced", "exposure_draft", "before_parliament", "passed", "enacted", "withdrawn"}
MEASURE_TYPES = {"bill", "exposure_draft", "announcement", "ato_draft", "other"}


class ProposedLawIn(BaseModel):
    title: str
    measure_type: str = "other"
    status: str = "announced"
    summary: str = ""
    announced_date: Optional[str] = None
    source_url: Optional[str] = None
    notes: str = ""


class ProposedLawPatch(BaseModel):
    status: Optional[str] = None
    measure_type: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None


def load_items() -> list[dict]:
    if not ITEMS_FILE.exists():
        return []
    try:
        return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def save_items(items: list[dict]) -> None:
    ITEMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ITEMS_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _validate(item: ProposedLawIn | ProposedLawPatch) -> None:
    if item.status is not None and item.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    if item.measure_type is not None and item.measure_type not in MEASURE_TYPES:
        raise HTTPException(400, f"measure_type must be one of {sorted(MEASURE_TYPES)}")


@router.get("")
def list_items():
    """All proposed-law items, newest first."""
    return {"items": list(reversed(load_items()))}


@router.post("")
def add_item(body: ProposedLawIn):
    """Add a proposed-law item (kept newest-first in the store)."""
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    _validate(body)
    items = load_items()
    item = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "title": body.title.strip(),
        "measure_type": body.measure_type,
        "status": body.status,
        "summary": body.summary.strip(),
        "announced_date": body.announced_date,
        "source_url": body.source_url,
        "notes": body.notes.strip(),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    # ensure id uniqueness
    while any(x["id"] == item["id"] for x in items):
        item["id"] += "x"
    items.append(item)
    save_items(items)
    return {"ok": True, "item": item}


@router.patch("/{item_id}")
def update_item(item_id: str, body: ProposedLawPatch):
    """Update status / measure_type / summary / notes / source_url."""
    _validate(body)
    items = load_items()
    for it in items:
        if it["id"] == item_id:
            for field in ("status", "measure_type", "summary", "notes", "source_url"):
                value = getattr(body, field)
                if value is not None:
                    it[field] = value
            save_items(items)
            return {"ok": True, "item": it}
    raise HTTPException(404, "item not found")


@router.delete("/{item_id}")
def delete_item(item_id: str):
    items = load_items()
    remaining = [it for it in items if it["id"] != item_id]
    if len(remaining) == len(items):
        raise HTTPException(404, "item not found")
    save_items(remaining)
    return {"ok": True}
