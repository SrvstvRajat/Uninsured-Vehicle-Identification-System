"""
REST client for the source laptops: the ONLY way the Coordinator talks to them.

    api_call()  generic POST/GET to one source's REST API (source_api.py)
    api_query() run one read-only SELECT on a source        (/api/query)
    similar()   SIMILARITY MATCHING done on the source       (/api/similar)
    context()   Phase 3: CONTEXT DISCOVERY done on the source (/api/context)
    docsearch() Phase 3: document search on the source        (/api/docsearch)
    health()    database reachability of one source         (/api/health)

similar() is where similarity matching is requested. The source scores its own
stored values and returns only the best candidates. If a source laptop still
runs the old source_api.py (no /api/similar -> HTTP 404), similar() falls back
to fetching that column's DISTINCT values and scoring them here, so a laptop
that has not been updated yet is slower but never breaks the lookup.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from urllib.parse import urlparse
import urllib.error
import urllib.request
from datetime import datetime

import fuzzy_match
from config import SOURCE_API_TOKENS, SOURCE_API_URLS

API_TIMEOUT_SEC = int(os.getenv("SOURCE_API_TIMEOUT_SEC", "30"))
# A laptop that is switched off does not refuse the connection, it just never answers,
# so every call would wait API_TIMEOUT_SEC. Probe the port quickly instead and remember
# an unreachable laptop for a short while.
CONNECT_TIMEOUT_SEC = float(os.getenv("SOURCE_CONNECT_TIMEOUT_SEC", "2"))
DOWN_CACHE_SEC = int(os.getenv("SOURCE_DOWN_CACHE_SEC", "20"))
_down_until: dict[str, float] = {}
_down_lock = threading.Lock()


def _check_reachable(source: str, base: str):
    """Raise SourceError fast if the laptop's port does not accept a connection."""
    now = time.time()
    with _down_lock:
        if _down_until.get(source, 0) > now:
            raise SourceError(f"The {source} REST API at {base} is unreachable "
                              f"(no answer within {CONNECT_TIMEOUT_SEC:g}s; retrying shortly)")
    url = urlparse(base)
    try:
        socket.create_connection((url.hostname, url.port or 80),
                                 timeout=CONNECT_TIMEOUT_SEC).close()
    except OSError as exc:
        with _down_lock:
            _down_until[source] = now + DOWN_CACHE_SEC
        raise SourceError(f"Cannot reach the {source} REST API at {base} ({exc}). "
                          "Is source_api.py running on that laptop?")
HEALTH_TIMEOUT_SEC = 3
FALLBACK_MAX_DISTINCT = int(os.getenv("SOURCE_FALLBACK_MAX_DISTINCT", "500000"))

# What each source owns (must match source_api.py SOURCES / SIMILAR_COLUMNS).
SOURCE_TABLES = {
    #  source       table                 database                   plate column
    "vehicles":  ("vehicles",           "vehicle_registration_db", "reg_plate"),
    "insurance": ("insurance_policies", "insurance_db",            "vehicle_number"),
    "rto":       ("rto_records",        "rto_db",                  "car_id"),
    "theft":     ("theft_records",      "theft_db",                "plate_no"),
    "mot":       ("mot_reports",        "mot_db",                  "vehicle_plate"),
}
COLUMN_KINDS = {
    "vehicles":  {"reg_plate": "plate", "make": "text", "model": "text",
                  "color": "text", "owner_name": "name",
                  "engine_no": "code", "chassis_no": "code"},
    "insurance": {"vehicle_number": "plate", "insurer_name": "text",
                  "policy_no": "code"},
    "rto":       {"car_id": "plate", "rto_office": "text"},
    "theft":     {"plate_no": "plate", "status": "text"},
    "mot":       {"vehicle_plate": "plate", "flag_reason": "text",
                  "reported_by": "name"},
}
# Phase 3: similarity-matchable columns per TABLE (same map as source_api.py).
# The hub tables keep the Phase 2 COLUMN_KINDS above.
TABLE_KINDS = {
    "vehicles": COLUMN_KINDS["vehicles"],
    "owners": {"full_name": "name", "phone": "code", "city": "text"},
    "vehicle_models": {"make": "text", "model": "text"},
    "dealers": {"dealer_name": "text", "city": "text"},
    "insurance_policies": COLUMN_KINDS["insurance"],
    "customers": {"customer_name": "name", "phone": "code"},
    "agents": {"agent_name": "name"},
    "branches": {"insurer_name": "text", "city": "text"},
    "rto_records": COLUMN_KINDS["rto"],
    "rto_offices": {"office_name": "text", "office_code": "code", "city": "text"},
    "challans": {"offence": "text", "location": "text"},
    "theft_records": COLUMN_KINDS["theft"],
    "firs": {"fir_no": "code", "complainant_name": "name", "complainant_phone": "code"},
    "police_stations": {"station_name": "text", "city": "text"},
    "recoveries": {"location": "text"},
    "mot_reports": COLUMN_KINDS["mot"],
}
ROW_ORDER = {
    "vehicles": "id DESC",
    "insurance": "policy_end_date DESC",
    "rto": "registration_date DESC",
    "theft": "theft_date DESC",
    "mot": "report_date DESC",
}
ROWS_PER_VALUE = 20

# LAN calls to the source laptops must not go through a system HTTP proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SourceError(RuntimeError):
    """A source API could not be reached or refused the request."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def plate_column(source: str) -> str:
    return SOURCE_TABLES[source][2]


def endpoint(source: str, path: str = "/api/query") -> str:
    base = SOURCE_API_URLS.get(source, "")
    return f"{base}{path}" if base else ""


def api_call(source: str, path: str, payload: dict | None = None,
             method: str = "POST", timeout: int = API_TIMEOUT_SEC) -> dict:
    """Send one request to a source laptop's REST API and return its JSON."""
    base = SOURCE_API_URLS.get(source, "")
    if not base:
        raise SourceError(
            f"No REST API URL configured for '{source}'. Set {source.upper()}_API_URL "
            "in .env, e.g. http://<that-laptop-ip>:5100")
    headers = {"Content-Type": "application/json"}
    token = SOURCE_API_TOKENS.get(source, "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    _check_reachable(source, base)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except Exception:
            detail = None
        raise SourceError(f"{source} REST API answered HTTP {exc.code}: "
                          f"{detail or exc.reason}", status=exc.code)
    except (socket.timeout, TimeoutError):
        raise SourceError(f"The {source} REST API at {base} did not answer within "
                          f"{timeout}s")
    except urllib.error.URLError as exc:
        raise SourceError(f"Cannot reach the {source} REST API at {base} ({exc.reason}). "
                          "Is source_api.py running on that laptop?")


def api_query(source: str, sql: str) -> tuple[list[str], list[tuple]]:
    """Run one read-only SELECT on a source; returns (columns, rows)."""
    data = api_call(source, "/api/query", {"sql": sql})
    return data["columns"], [tuple(r) for r in data["rows"]]


def api_query_dicts(source: str, sql: str) -> list[dict]:
    columns, rows = api_query(source, sql)
    return [dict(zip(columns, row)) for row in rows]


def health(source: str) -> dict:
    """{available, error, checked_at} for one source's database."""
    checked_at = datetime.now().isoformat(timespec="seconds")
    try:
        data = api_call(source, "/api/health", method="GET",
                        timeout=HEALTH_TIMEOUT_SEC)
        ok = data.get("database_reachable") is True
        return {"available": ok, "checked_at": checked_at,
                "error": None if ok else f"{source} database is not reachable."}
    except Exception as exc:
        return {"available": False, "checked_at": checked_at, "error": str(exc)}


def _sql_string(value) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _similar_fallback(source: str, column: str, value: str, limit: int,
                      with_rows: bool) -> dict:
    """Old source_api.py without /api/similar: score here instead."""
    table = SOURCE_TABLES[source][0]
    kind = COLUMN_KINDS[source][column]
    _, rows = api_query(
        source,
        f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL "
        f"LIMIT {FALLBACK_MAX_DISTINCT}")
    stored = [str(r[0]) for r in rows if r[0] not in (None, "")]
    result = fuzzy_match.match_value(kind, value, stored, max_matches=limit,
                                     fallback_n=limit)
    matches = [{"value": v, "score": s} for v, s in result["matches"]]
    if with_rows:
        for match in matches:
            match["rows"] = api_query_dicts(
                source,
                f"SELECT * FROM {table} WHERE {column} = {_sql_string(match['value'])} "
                f"ORDER BY {ROW_ORDER[source]} LIMIT {ROWS_PER_VALUE}")
    return {"source": source, "column": column, "kind": kind, "query": value,
            "exact": result["exact"], "low_confidence": result["low_confidence"],
            "candidates_scanned": result["scanned"], "matches": matches,
            "via": "coordinator-fallback"}


def similar(source: str, column: str, value: str, limit: int = 5,
            with_rows: bool = False, table: str | None = None) -> dict:
    """Ask ONE source which of its stored `column` values look like `value`.

    `table` defaults to the source's hub table (Phase 2 behaviour); Phase 3
    sources also accept their other tables (e.g. owners.full_name).
    Returns the /api/similar response: {"matches": [{"value", "score",
    "rows"?}], "exact", "low_confidence", "candidates_scanned", "via"}.
    Raises SourceError if the source is unreachable.
    """
    hub = SOURCE_TABLES[source][0]
    table = table or hub
    if column not in TABLE_KINDS.get(table, {}):
        raise SourceError(f"Column '{table}.{column}' is not similarity-matchable on {source}.")
    payload = {"column": column, "value": value, "limit": limit,
               "with_rows": with_rows}
    if table != hub:
        payload["table"] = table
    try:
        data = api_call(source, "/api/similar", payload)
        data["via"] = "source"
        return data
    except SourceError as exc:
        if exc.status == 404 and table == hub:   # source laptop not updated yet
            return _similar_fallback(source, column, value, limit, with_rows)
        raise


def context(source: str, payload: dict) -> dict:
    """Phase 3: the source discovers its own context by walking its FK graph.

    Raises SourceError; .status is 404 when the laptop still runs a Phase 2
    source_api.py, 400 when a seed table/column is not served there yet.
    """
    return api_call(source, "/api/context", payload, timeout=API_TIMEOUT_SEC)


def docsearch(source: str, payload: dict) -> dict:
    """Phase 3: context-driven search of the source laptop's own documents.

    Raises SourceError; .status 503 = no document index on that laptop yet,
    404 = Phase 2 source_api.py.
    """
    return api_call(source, "/api/docsearch", payload, timeout=API_TIMEOUT_SEC)
