"""
REST client for the source laptops: the ONLY way the Coordinator talks to them.

    api_call()  generic POST/GET to one source's REST API (source_api.py)
    api_query() run one read-only SELECT on a source        (/api/query)
    similar()   SIMILARITY MATCHING done on the source       (/api/similar)
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
import urllib.error
import urllib.request
from datetime import datetime

import fuzzy_match
from config import SOURCE_API_TOKENS, SOURCE_API_URLS

API_TIMEOUT_SEC = int(os.getenv("SOURCE_API_TIMEOUT_SEC", "30"))
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
            with_rows: bool = False) -> dict:
    """Ask ONE source which of its stored `column` values look like `value`.

    Returns the /api/similar response: {"matches": [{"value", "score",
    "rows"?}], "exact", "low_confidence", "candidates_scanned", "via"}.
    Raises SourceError if the source is unreachable.
    """
    if column not in COLUMN_KINDS.get(source, {}):
        raise SourceError(f"Column '{column}' is not similarity-matchable on {source}.")
    payload = {"column": column, "value": value, "limit": limit,
               "with_rows": with_rows}
    try:
        data = api_call(source, "/api/similar", payload)
        data["via"] = "source"
        return data
    except SourceError as exc:
        if exc.status == 404:          # source laptop not updated yet
            return _similar_fallback(source, column, value, limit, with_rows)
        raise