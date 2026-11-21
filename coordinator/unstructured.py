"""
Phase 3 — Unstructured data integration (Coordinator, M1).

The documents live on the source laptops (FIRs on M5, claim reports on M3, ...).
The coordinator sends the QUERY CONTEXT (identifiers found by context discovery,
places, event-date window, intents) to every laptop's POST /api/docsearch in
parallel, merges the answers, and attaches each document to the context row it
supports (FIR narrative -> the FIR row, sale deed -> the transfer row ...).

Only documents the source accepted are returned: they must agree with the context
on an identifier (plate, phone, FIR / policy / chassis number ...) or be very
close in meaning. Documents about other vehicles are rejected at the source.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor

from config import SOURCE_NAMES
from mediator import normalize_plate
from source_client import SourceError, docsearch as source_docsearch

SOURCES = ("vehicles", "insurance", "rto", "theft")
DOCS_PER_SOURCE = 5
MAX_IDS_PER_KIND = 15
ID_KINDS = ("plates", "phones", "names", "fir_nos", "policy_nos", "chassis", "engines",
            "certificates", "claim_nos")


def build_request(ctx: dict, k: int = DOCS_PER_SOURCE, use_context: bool = True) -> dict:
    """The /api/docsearch payload.

    use_context=False is the BASELINE: only what the user typed (the plate / phone /
    FIR number in the question and its words), without anything that context
    discovery added (other stored spellings of the plate, owner phones and names,
    FIR / policy / chassis numbers, places, date window).
    """
    if not use_context:
        parsed = ctx["parsed"]
        typed = {kind: parsed.get(kind, []) for kind in ID_KINDS if parsed.get(kind)}
        return {"identifiers": typed, "keywords": parsed["terms"],
                "description": ctx["query"], "k": k}
    ids = {kind: ctx["identifiers"].get(kind, [])[:MAX_IDS_PER_KIND] for kind in ID_KINDS
           if ctx["identifiers"].get(kind)}
    payload = {"identifiers": ids,
               "keywords": list(dict.fromkeys(ctx["intents"] + ctx["parsed"]["terms"]))[:20],
               "places": ctx.get("places", [])[:10], "description": ctx.get("description", ""),
               "k": k}
    if ctx.get("date_window"):
        payload["date_window"] = ctx["date_window"]
    return payload


def _search_one(source: str, payload: dict) -> dict:
    t0 = time.perf_counter()
    try:
        data = source_docsearch(source, payload)
        return {"source": source, "status": "ok", "docs": data.get("docs", []),
                "stats": data.get("stats"), "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except SourceError as exc:
        status = {404: "phase2_api", 503: "no_index"}.get(exc.status, "unreachable")
        return {"source": source, "status": status, "docs": [], "error": str(exc),
                "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return {"source": source, "status": "error", "docs": [], "error": str(exc),
                "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _norm(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


# Which context table a document type documents (event rows first).
DOC_TABLE = {
    "sale_deed": "ownership_transfers", "transfer_letter": "ownership_transfers",
    "claim_report": "claims", "surveyor_note": "claims",
    "fir_narrative": "firs", "recovery_report": "recoveries", "news_article": "theft_records",
    "inspection_report": "fitness_certificates", "challan_notice": "challans",
}


def _attach(doc: dict, nodes: list[dict]) -> dict | None:
    """The context row this document supports.

    1. a row of the table this document type is about (sale deed -> transfer),
       preferring the one whose date appears in the document;
    2. otherwise a row of the same source that shares a matched value;
    3. otherwise that source's seed row.
    """
    same = [n for n in nodes if n["source"] == doc["source"]]
    doc_dates = set(doc.get("dates") or [])
    wanted = DOC_TABLE.get(doc.get("doc_type"))
    typed = [n for n in same if n["table"] == wanted]
    if typed:
        dated = [n for n in typed if any(str(v)[:10] in doc_dates for v in n["row"].values()
                                         if v)]
        best = max(dated or typed, key=lambda n: n["relevance"])
        return {"key": best["key"], "table": best["table"], "id": best["id"],
                "how": "date + document type" if dated else "document type"}
    reasons = _norm(" ".join(doc.get("matched_on") or []))
    snippet = _norm(doc.get("snippet"))
    best = None
    for node in same:
        for column, value in node["row"].items():
            text = _norm(value)
            if len(text) < 6 or column == "id" or column.endswith("_id"):
                continue
            if text in reasons or (len(text) >= 8 and text in snippet):
                if best is None or node["relevance"] > best["relevance"]:
                    best = node
                break
    how = "shared identifier"
    if best is None:
        best = next((n for n in same if n["hop"] == 0 and n["round"] == 1), None)
        how = "source seed row"
    return ({"key": best["key"], "table": best["table"], "id": best["id"], "how": how}
            if best else None)


def search_documents(ctx: dict, k: int = DOCS_PER_SOURCE, use_context: bool = True) -> dict:
    """Federated, context-driven document search; returns merged docs + per-source status."""
    payload = build_request(ctx, k, use_context)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        results = list(pool.map(lambda s: _search_one(s, payload), SOURCES))
    docs = []
    for result in results:
        for doc in result["docs"]:
            doc = dict(doc, source=result["source"],
                       machine=SOURCE_NAMES.get(result["source"], result["source"]))
            doc["attached_to"] = _attach(doc, ctx.get("nodes", [])) if use_context else None
            docs.append(doc)
    docs.sort(key=lambda d: -d["score"])
    return {"request": payload, "docs": docs,
            "per_source": [{k2: v for k2, v in r.items() if k2 != "docs"} | {
                "returned": len(r["docs"])} for r in results],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1)}


def plates_of(ctx: dict) -> set:
    return {normalize_plate(p) for p in ctx.get("identifiers", {}).get("plates", [])}
