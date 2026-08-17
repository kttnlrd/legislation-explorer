#!/usr/bin/env python3
"""Pre-graph data integrity verification — private rulings + all other data types.

Checks every data source the graph ETL (docs/specs/graph.md §9) consumes, so the
graph build only runs on verified inputs. Prints PASS/FAIL per check; exit 0 only
if everything is green.

Usage:
    python3 scripts/verify_graph_readiness.py [--require-mop-complete]

--require-mop-complete: fail if the private-rulings LLM mop-up hasn't reached
57,608/57,608 (default: warn only, so the non-private checks can run early).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RULINGS = DATA / "rulings"
SUMMARIES = RULINGS / "summaries"
PRIV = Path(os.environ.get("HERMES_RULINGS_DIR", Path.home() / ".hermes" / "private_rulings")) / "data"
JSON_DIR = PRIV / "json"
JSON_LLM = PRIV / "json_llm"
MOP_MARKED = PRIV / "mop_marked"

ACTS = ["itaa-1997", "itaa-1936", "gst-1999", "fbt-1986", "taa-1953",
        "corporations-act-2001", "aml-ctf-2006", "aml-ctf-rules-2007", "sis-1993",
        "nz-it-2007"]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


def act_tree_ids(act: str) -> set[str]:
    tree = json.loads((DATA / act / "tree.json").read_text())
    ids: set[str] = set()
    stack = [tree]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            if "id" in item:
                ids.add(str(item["id"]))
            stack.extend(v for v in item.values() if isinstance(v, (list, dict)))
    return ids


def load(name: str):
    p = DATA / name
    if not p.exists():
        return None
    return json.loads(p.read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-mop-complete", action="store_true")
    args = ap.parse_args()

    print("== Private rulings (mop-up enrichment) ==")
    if not JSON_LLM.is_dir():
        check("private: json_llm dir exists", False, str(JSON_LLM))
    else:
        llm_files = sorted(JSON_LLM.glob("*.json"))
        json_files = sorted(JSON_DIR.glob("*.json")) if JSON_DIR.is_dir() else []
        check("private: json_llm count matches corpus", len(llm_files) == len(json_files),
              f"{len(llm_files)} vs {len(json_files)}")

        mop_done = (MOP_MARKED.is_dir() and len(list(MOP_MARKED.glob("*.ok"))) == len(json_files)) \
            if json_files else False
        if not mop_done:
            marked = len(list(MOP_MARKED.glob("*.ok"))) if MOP_MARKED.is_dir() else 0
            if args.require_mop_complete:
                check("private: mop-up complete", False, f"{marked}/{len(json_files)} marked")
            else:
                check("private: mop-up complete", True, f"WARN {marked}/{len(json_files)} marked (not gating)")

        # sample scan (bounded: up to 2000 files) for status/parse stats
        import random
        sample = random.sample(llm_files, min(2000, len(llm_files)))
        ok_files = err_files = 0
        authnums: set[str] = set()
        dup_authnums = 0
        bad_authnums = 0
        leg_parsed = leg_skip = leg_unparsed = 0
        case_kept = case_dropped = 0
        sec_refs_unknown_act: set[str] = set()
        sec_refs_not_in_tree: dict[str, int] = {}

        sys.path.insert(0, str(ROOT))
        from pipeline import graph_etl as ge

        # act -> tree section ids (only section leaves, matching load_acts)
        tree_sec_ids: dict[str, set[str]] = {}
        for act in ge.ACTS:
            if (DATA / act / "tree.json").exists():
                tree_sec_ids[act] = act_tree_ids(act)

        for f in sample:
            try:
                d = json.loads(f.read_text())
            except Exception:
                err_files += 1
                continue
            if d.get("mop_status") != "ok":
                err_files += 1
            else:
                ok_files += 1
            an = str(d.get("authorisation_number", ""))
            if an in authnums:
                dup_authnums += 1
            authnums.add(an)
            if not re.fullmatch(r"\d{13}", an):
                bad_authnums += 1
            if d.get("mop_status") == "ok":
                for ref in d.get("legislation_refs_llm", []) or []:
                    r = ge._parse_leg_ref(ref)
                    if r == "non-section":
                        leg_skip += 1
                    elif r:
                        leg_parsed += 1
                        for act, sec in r:
                            if act not in ge.ACTS:
                                sec_refs_unknown_act.add(act)
                            elif act in tree_sec_ids and sec not in tree_sec_ids[act]:
                                sec_refs_not_in_tree[sec] = sec_refs_not_in_tree.get(sec, 0) + 1
                    else:
                        leg_unparsed += 1
                for cit in d.get("case_refs_llm", []) or []:
                    if ge._case_key(cit):
                        case_kept += 1
                    else:
                        case_dropped += 1

        n = len(sample)
        err_rate = err_files / max(n, 1)
        check("private: sample usable (ok+err read)", ok_files + err_files == n and n > 0,
              f"{ok_files} ok, {err_files} err in {n}")
        check("private: err rate < 1%", err_rate < 0.01,
              f"{err_rate * 100:.2f}% ({err_files}/{n}) — err rulings get regex-ref nodes only")
        check("private: authnums unique + 13-digit", dup_authnums == 0 and bad_authnums == 0,
              f"{dup_authnums} dup, {bad_authnums} bad format")
        total_leg = leg_parsed + leg_skip + leg_unparsed
        check("private: legislation refs parse rate", total_leg > 0 and leg_unparsed / total_leg < 0.25,
              f"{leg_parsed} parsed, {leg_skip} div-skip, {leg_unparsed} unparsed ({100 * leg_unparsed / max(total_leg, 1):.1f}%)")
        if sec_refs_unknown_act:
            check("private: section refs act known", False,
                  f"unknown acts: {sorted(sec_refs_unknown_act)[:5]}")
        else:
            check("private: section refs act known", True)
        unknown_sec_total = sum(sec_refs_not_in_tree.values())
        check("private: section refs resolve in act trees", unknown_sec_total / max(leg_parsed, 1) < 0.10,
              f"{unknown_sec_total}/{leg_parsed} refs point at ids absent from trees")

    print("== Public rulings ==")
    txt = [f for f in RULINGS.glob("*.txt") if not f.name.endswith(".meta.json")]
    check("rulings: txt corpus", len(txt) > 10000, f"{len(txt)} files")
    if SUMMARIES.is_dir():
        sums = {f.stem for f in SUMMARIES.glob("*.json")}
        missing = [f.stem for f in txt if f.stem not in sums]
        check("rulings: every txt has a summary", len(missing) == 0, f"{len(missing)} missing")
        err_stubs = []
        no_ruling = []
        for f in SUMMARIES.glob("*.json"):
            try:
                d = json.loads(f.read_text())
            except Exception:
                err_stubs.append(f.name)
                continue
            if "error" in d:
                err_stubs.append(f.name)
            elif "ruling" not in d and "full_text" not in d \
                    and d.get("summary_type") != "auto_extracted":
                no_ruling.append(f.name)
        check("rulings: zero error stubs", len(err_stubs) == 0, f"{len(err_stubs)}: {err_stubs[:5]}")
        check("rulings: summaries have body fields", len(no_ruling) == 0,
              f"{len(no_ruling)}: {no_ruling[:5]} (legacy auto_extracted OK)")

    print("== Sections ==")
    for act in ACTS:
        tree_p = DATA / act / "tree.json"
        if not tree_p.exists():
            check(f"sections: {act} tree.json", False)
            continue
        tree = json.loads(tree_p.read_text())
        n_sections = 0
        missing_files = 0
        stack = [tree]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "path" in item and "id" in item:
                    n_sections += 1
                    if not (DATA / act / "sections" / item["path"]).exists():
                        missing_files += 1
                stack.extend(v for v in item.values() if isinstance(v, (list, dict)))
        check(f"sections: {act}", n_sections > 0 and missing_files == 0,
              f"{n_sections} sections, {missing_files} missing files")

    print("== Cases ==")
    csr = load("case_section_refs.json") or {}
    sci = load("section_case_index.json") or {}
    bad_cites = [k for k in csr if not re.search(r"\[\d{4}\]\s*[A-Z]+", k)]
    check("cases: case_section_refs", len(csr) > 1000, f"{len(csr)} cases")
    check("cases: neutral citation format", len(bad_cites) == 0, f"{len(bad_cites)} non-neutral")
    check("cases: section_case_index", len(sci) > 100, f"{len(sci)} keys")

    print("== Definitions ==")
    defs = load("definitions_all.json") or {}
    n_terms = sum(len(v.get("terms", {})) for v in defs.values())
    check("definitions: acts + terms", len(defs) >= 4 and n_terms > 1000, f"{len(defs)} acts, {n_terms} terms")

    print("== Commentary ==")
    for g in ("master-tax-guide", "master-gst-guide", "master-tax-examples"):
        t = load(f"{g}/tree.json")
        parts = len(t.get("parts", [])) if t else 0
        check(f"commentary: {g}", bool(t) and parts > 0, f"{parts} parts")

    print("== Treaties ==")
    tdir = DATA / "treaties"
    if tdir.is_dir():
        tdirs = [d for d in tdir.iterdir() if d.is_dir()]
        total_articles = 0
        missing_articles = 0
        for d in tdirs:
            t = load(f"treaties/{d.name}/tree.json")
            if not t:
                missing_articles += 1
                continue
            arts = t.get("articles", [])
            total_articles += len(arts)
            missing_articles += sum(1 for a in arts if not (d / a["file"]).exists())
        check("treaties: countries + article files", len(tdirs) >= 40 and missing_articles == 0,
              f"{len(tdirs)} countries, {total_articles} articles, {missing_articles} missing files")

    print("== Smartlinks / cross-refs ==")
    sl = load("smartlink_index.json") or {}
    if isinstance(sl, dict) and sl:
        sample_keys = list(sl.keys())[:1]
        check("smartlinks: index populated", True, f"{len(sl)} keys, sample {sample_keys}")
    else:
        check("smartlinks: index populated", False, "empty")

    print("== Embeddings ==")
    emb = DATA / "embeddings.db"
    if emb.exists():
        con = sqlite3.connect(emb)
        n_emb = con.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        n_sim = con.execute("SELECT COUNT(*) FROM similarity_index").fetchone()[0]
        check("embeddings: rows present", n_emb > 100000 and n_sim > 500000,
              f"{n_emb} embeddings, {n_sim} similarity")
    else:
        check("embeddings: embeddings.db", False)

    print("== Search index ==")
    sdb = DATA.parent / "search_index.db"
    if sdb.exists():
        con = sqlite3.connect(sdb)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        check("search: FTS tables present", len(tables) > 0, f"tables: {tables[:6] or 'NONE'}")
    else:
        check("search: search_index.db exists", False)

    print()
    fails = [r for r in results if not r[1]]
    print(f"{len(results) - len(fails)}/{len(results)} checks passed, {len(fails)} failed")
    for name, _, detail in fails:
        print(f"  FAIL: {name} — {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
