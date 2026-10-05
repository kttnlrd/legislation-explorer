#!/usr/bin/env python3
"""Live MCP wire-protocol test — JSON-RPC tools/list + tools/call.

Runs ON a server (localhost) against its own /mcp streamable-HTTP endpoint,
using the operator token (MCP_AUTH_TOKEN) so it exercises the exact path an
MCP client takes: auth, tool registration, arg validation, result framing.

Usage (from the repo root, .env loaded):
    PYTHONPATH=. python scripts/mcp_wire_test.py --port 8769
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

# (tool, args) — read-only shared surface, plus report_issue (dedup-safe note).
_CALLS = [
    ("get_info", {}),
    ("search", {"query": "capital gains"}),
    ("search", {"query": "capital gains", "types": ["legislation"]}),
    ("search", {"query": "deduction", "types": ["legislation"], "act": "itaa-1997"}),
    ("fetch", {"ref": "leg:itaa-1997:8-1"}),
    ("fetch", {"ref": "TR 2005/23"}),
    ("outline", {}),
    ("outline", {"id": "itaa-1997"}),
    ("resolve_alias", {"reference": "s 8-1"}),
    ("resolve_alias", {"reference": "Div 7A"}),
    ("get_definition", {"act": "itaa-1997", "term": "resident"}),
    ("list_rulings", {}),
    ("related", {"id": "leg:itaa-1997:8-1"}),
    ("graph_neighbourhood", {"key": "section:itaa-1997:8-1"}),
    ("graph_path", {"from_key": "section:itaa-1997:8-1", "to_key": "case:[1986] HCA 45"}),
    ("report_issue", {
        "category": "suggestion", "tool": "search", "params": "{}",
        "expected": "x", "actual": "y", "note": "wire-protocol test (safe to delete)",
    }),
]

# scriptkitty-only internal tools (read-only subset; write tools left uncalled).
_SK_EXTRA = [
    ("list_issues", {}),
    ("standards", {}),
]


def rpc(url: str, method: str, params: dict, _id: int = 1):
    payload = {"jsonrpc": "2.0", "id": _id, "method": method, "params": params}
    # The MCP endpoint refuses rapid-fire fresh connections (FastMCP session
    # manager / uvicorn concurrency); retry once with a short backoff so a
    # burst of audit calls doesn't false-fail.
    last = None
    for attempt in range(3):
        try:
            r = httpx.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json",
                         "Accept": "application/json, text/event-stream"},
                timeout=90,
            )
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", default=None, help="override MCP token (else resolved from env)")
    args = ap.parse_args()

    token = (args.token
             or os.environ.get("MCP_AUTH_TOKEN")
             or os.environ.get("LEGISLATION_BEARER_TOKEN"))
    if not token:
        # scriptkitty stores the operator token in the repo .env (no token_manager);
        # fall back to the Cadena token in ~/.hermes/.env.
        for env_path in (Path(__file__).resolve().parent.parent / ".env",
                         Path.home() / ".hermes" / ".env"):
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    k, _, v = line.partition("=")
                    if k.strip() in ("MCP_AUTH_TOKEN", "CADENA_MCP_TOKEN"):
                        token = v.strip().strip('"').strip("'")
                        break
            if token:
                break
    if not token:
        raise SystemExit("no MCP token found (MCP_AUTH_TOKEN / .env / ~/.hermes/.env)")
    url = f"http://127.0.0.1:{args.port}/mcp/{token}"

    listed = rpc(url, "tools/list", {})
    tools = [t["name"] for t in listed["result"]["tools"]]
    print(f"tools/list -> {len(tools)} tools: {sorted(tools)}\n")

    shared = {"search", "fetch", "outline", "related", "resolve_alias",
              "get_definition", "get_info", "list_rulings", "report_issue",
              "graph_neighbourhood", "graph_path"}
    missing_shared = shared - set(tools)
    print(f"shared 11 present: {not missing_shared}" +
          (f"  (MISSING: {sorted(missing_shared)})" if missing_shared else ""))
    print()

    calls = list(_CALLS)
    for tool, a in _SK_EXTRA:
        if tool in tools:
            calls.append((tool, a))

    passed = failed = 0
    for tool, arguments in calls:
        try:
            body = rpc(url, "tools/call", {"name": tool, "arguments": arguments})
            result = body.get("result", {})
            if result.get("isError"):
                content = result.get("content", [])
                txt = content[0].get("text", "") if content else str(content)
                failed += 1
                print(f"  FAIL  {tool:20s} isError: {txt[:100]}")
                continue
            content = result.get("content", [])
            text = content[0].get("text", "") if content else ""
            try:
                parsed = json.loads(text)
                summary = (f"keys={list(parsed.keys())[:5]}"
                           if isinstance(parsed, dict) else f"len={len(text)}ch")
            except Exception:
                summary = f"raw {len(text)}ch"
            passed += 1
            print(f"  PASS  {tool:20s} {summary}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {tool:20s} {type(e).__name__}: {e}")

    print(f"\n=== {passed} pass, {failed} fail ===")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
