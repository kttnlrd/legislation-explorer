"""Proposed-law tracker v2 — tree model.

Each item (a measure) carries:
  commentary : one big markdown section (Harry's notes on the proposal)
  acts       : acts proposed to be amended or introduced, each with the
               proposed sections as {title, content} markdown

Store: data/proposed-law/items.json
Statuses: announced | exposure_draft | before_parliament | passed | enacted | withdrawn
Relation: amended | introduced
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[2] / "data" / "proposed-law"
ITEMS_FILE = DATA / "items.json"

router = APIRouter(prefix="/api/proposed-law", tags=["proposed-law"])

MEASURE_TYPES = {"bill", "exposure_draft", "announcement", "ato_draft", "other"}
STATUSES = {"announced", "exposure_draft", "before_parliament", "passed", "enacted", "withdrawn"}
RELATIONS = {"amended", "introduced"}


def load_items():
    if not ITEMS_FILE.exists():
        return []
    return json.loads(ITEMS_FILE.read_text(encoding="utf-8"))


def save_items(items):
    ITEMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ITEMS_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def _find(items, item_id):
    for idx, it in enumerate(items):
        if it.get("id") == item_id:
            return idx, it
    raise HTTPException(404, "item not found")


class ItemIn(BaseModel):
    title: str = ""
    measure_type: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    announced_date: Optional[str] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None
    commentary: Optional[str] = None
    acts: Optional[list] = None
    documents: Optional[list] = None


def _validate_acts(acts):
    """Normalise acts payload (list of {name, relation, sections[]}) for storage."""
    REL = {"amended", "introduced", "new"}
    clean = []
    for a in acts or []:
        if not isinstance(a, dict) or not str(a.get("name", "")).strip():
            continue
        rel = str(a.get("relation", "amended")).strip()
        if rel not in REL:
            rel = "amended"
        if rel == "introduced":
            rel = "new"
        secs = []
        for sec in (a.get("sections") or []):
            if isinstance(sec, dict) and str(sec.get("title", "")).strip():
                secs.append({
                    "title": str(sec["title"]).strip(),
                    "content": str(sec.get("content", "")),
                })
        clean.append({"name": str(a["name"]).strip(), "relation": rel, "sections": secs})
    return clean


def _validate_documents(documents):
    """Normalise documents payload (list of {title, url, note?})."""
    clean = []
    for d in documents or []:
        if not isinstance(d, dict) or not str(d.get("title", "")).strip():
            continue
        clean.append({
            "title": str(d["title"]).strip(),
            "url": str(d.get("url", "")).strip(),
            "note": str(d.get("note", "")).strip(),
        })
    return clean


@router.get("")
def list_items():
    return {"items": load_items()}


@router.post("")
def add_item(body: ItemIn):
    title = body.title.strip() if body.title else ""
    if not title:
        raise HTTPException(400, "title is required")
    if body.measure_type and body.measure_type not in MEASURE_TYPES:
        raise HTTPException(400, f"measure_type must be one of {sorted(MEASURE_TYPES)}")
    if body.status and body.status not in STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    items = load_items()
    item = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S"),
        "title": title,
        "measure_type": body.measure_type or "other",
        "status": body.status or "announced",
        "summary": (body.summary or "").strip(),
        "announced_date": body.announced_date,
        "source_url": body.source_url,
        "notes": (body.notes or "").strip(),
        "commentary": body.commentary or "",
        "acts": _validate_acts(body.acts),
        "documents": _validate_documents(body.documents),
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    items.insert(0, item)
    save_items(items)
    return {"ok": True, "item": item}


@router.patch("/{item_id}")
def patch_item(item_id: str, body: ItemIn):
    items = load_items()
    idx, it = _find(items, item_id)
    if body.title and body.title.strip():
        it["title"] = body.title.strip()
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
        it["status"] = body.status
    if body.measure_type is not None:
        if body.measure_type not in MEASURE_TYPES:
            raise HTTPException(400, f"measure_type must be one of {sorted(MEASURE_TYPES)}")
        it["measure_type"] = body.measure_type
    if body.summary is not None:
        it["summary"] = body.summary
    if body.notes is not None:
        it["notes"] = body.notes
    if body.announced_date is not None:
        it["announced_date"] = body.announced_date
    if body.source_url is not None:
        it["source_url"] = body.source_url
    if body.commentary is not None:
        it["commentary"] = body.commentary
    if body.acts is not None:
        it["acts"] = _validate_acts(body.acts)
    if body.documents is not None:
        it["documents"] = _validate_documents(body.documents)
    save_items(items)
    return {"ok": True, "item": it}


@router.delete("/{item_id}")
def delete_item(item_id: str):
    items = load_items()
    idx, _ = _find(items, item_id)
    items.pop(idx)
    save_items(items)
    return {"ok": True}


# ---- tree content endpoints ----

def _act(it, act_idx):
    acts = it.get("acts") or []
    if not (0 <= act_idx < len(acts)):
        raise HTTPException(404, "act not found")
    return acts[act_idx]


@router.put("/{item_id}/commentary")
async def set_commentary(item_id: str, request: Request):
    body = await request.json()
    items = load_items()
    _, it = _find(items, item_id)
    it["commentary"] = (body.get("content") or "").strip()
    save_items(items)
    return {"ok": True, "item": it}


class ActIn(BaseModel):
    name: str
    relation: str = "amended"


@router.post("/{item_id}/acts")
def add_act(item_id: str, body: ActIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "act name is required")
    if body.relation not in RELATIONS:
        raise HTTPException(400, f"relation must be one of {sorted(RELATIONS)}")
    items = load_items()
    _, it = _find(items, item_id)
    it.setdefault("acts", []).append({"name": name, "relation": body.relation, "sections": []})
    save_items(items)
    return {"ok": True, "item": it}


@router.delete("/{item_id}/acts/{act_idx}")
def delete_act(item_id: str, act_idx: int):
    items = load_items()
    _, it = _find(items, item_id)
    _act(it, act_idx)
    it["acts"].pop(act_idx)
    save_items(items)
    return {"ok": True, "item": it}


class SectionIn(BaseModel):
    title: str
    content: str = ""


@router.post("/{item_id}/acts/{act_idx}/sections")
def add_section(item_id: str, act_idx: int, body: SectionIn):
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "section title is required")
    items = load_items()
    _, it = _find(items, item_id)
    act = _act(it, act_idx)
    act.setdefault("sections", []).append({"title": title, "content": body.content})
    save_items(items)
    return {"ok": True, "item": it}


@router.put("/{item_id}/acts/{act_idx}/sections/{sec_idx}")
def update_section(item_id: str, act_idx: int, sec_idx: int, body: SectionIn):
    items = load_items()
    _, it = _find(items, item_id)
    act = _act(it, act_idx)
    if not (0 <= sec_idx < len(act.get("sections", []))):
        raise HTTPException(404, "section not found")
    act["sections"][sec_idx] = {"title": body.title.strip() or act["sections"][sec_idx]["title"],
                                "content": body.content}
    save_items(items)
    return {"ok": True, "item": it}


@router.delete("/{item_id}/acts/{act_idx}/sections/{sec_idx}")
def delete_section(item_id: str, act_idx: int, sec_idx: int):
    items = load_items()
    _, it = _find(items, item_id)
    act = _act(it, act_idx)
    if not (0 <= sec_idx < len(act.get("sections", []))):
        raise HTTPException(404, "section not found")
    act["sections"].pop(sec_idx)
    save_items(items)
    return {"ok": True, "item": it}
