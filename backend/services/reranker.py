"""Cross-encoder reranking via Ollama. Best-effort: returns None on any failure."""
import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger("reranker")

RERANK_URL = os.getenv("RERANK_URL", "http://100.76.149.2:11434/api/rerank")
RERANK_MODEL = os.getenv("RERANK_MODEL", "qllama/bge-reranker-v2-m3")
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "1").lower() not in ("0", "false", "no", "")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "50"))

# ponytail: urllib, not requests — requests isn't a backend dependency and this is one POST.
# Single timeout covers connect+read; urllib has no separate connect timeout.
_TIMEOUT = 1.5
# After a failure (gamingpc asleep etc), skip rerank attempts for this long so a
# dead host doesn't add _TIMEOUT to every query. Re-engages automatically.
_FAILURE_COOLDOWN_S = 120
_last_failure = 0.0


def rerank(query: str, docs: list[str], top_n: int) -> list[float] | None:
    """Score each doc against query. Returns one float per doc (aligned to `docs`),
    or None if reranking is disabled or the call failed in any way.

    The endpoint only returns the top_n best docs; unscored docs get -inf so a
    stable sort leaves them in their original (RRF) relative order.
    """
    global _last_failure
    if not RERANK_ENABLED or not docs:
        return None
    if time.monotonic() - _last_failure < _FAILURE_COOLDOWN_S:
        return None

    payload = json.dumps({
        "model": RERANK_MODEL,
        "query": query,
        "documents": docs,
        "top_n": top_n,
    }).encode()
    req = urllib.request.Request(
        RERANK_URL, data=payload, headers={"Content-Type": "application/json"}
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.load(resp)
        scores = [float("-inf")] * len(docs)
        for item in body["results"]:
            i = int(item["index"])
            if 0 <= i < len(docs):
                scores[i] = float(item["relevance_score"])
    except Exception as e:  # timeout, refused, non-200, bad JSON, bad shape — all the same
        _last_failure = time.monotonic()
        ms = int((time.monotonic() - started) * 1000)
        logger.warning("[reranker] %d docs -> %d ms (fail: %s: %s; cooldown %ds)",
                       len(docs), ms, type(e).__name__, e, _FAILURE_COOLDOWN_S)
        return None
    ms = int((time.monotonic() - started) * 1000)
    logger.info("[reranker] %d docs -> %d ms (ok)", len(docs), ms)
    return scores


def _self_check():
    global RERANK_URL
    assert rerank("q", [], 5) is None
    RERANK_URL = "http://127.0.0.1:1/api/rerank"  # nothing listening
    assert rerank("q", ["a", "b"], 5) is None
    print("ok")


if __name__ == "__main__":
    _self_check()
