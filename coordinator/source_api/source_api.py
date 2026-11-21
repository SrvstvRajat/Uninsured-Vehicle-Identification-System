"""
Source REST API: runs on EACH source laptop and is the ONLY thing that
talks to that laptop's MySQL.

The Coordinator no longer opens MySQL connections to other laptops. It sends
the sub-query produced by its decomposition step to this service over HTTP,
and gets the rows back as JSON.

    python3 source_api/source_api.py vehicles      # on the registration laptop
    python3 source_api/source_api.py insurance     # on the insurance laptop
    python3 source_api/source_api.py rto           # on the RTO laptop
    python3 source_api/source_api.py theft         # on the theft laptop
    python3 source_api/source_api.py mot           # on the MoT laptop
(or set SOURCE_NAME=theft in the environment)

Endpoints
    GET  /api/health    liveness + DB ping (no auth, reveals nothing sensitive)
    GET  /api/schema    tables and columns this source owns          (token)
    POST /api/query     {"sql": "SELECT ..."}  read-only sub-query   (token)
    POST /api/execute   {"sql": "INSERT|UPDATE|DELETE ..."}  writes  (token,
                        only if SOURCE_API_ALLOW_WRITES=true on THIS laptop)
    POST /api/similar   {"column": "reg_plate", "value": "UPo9AI88@5",
                         "limit": 5, "with_rows": true}                (token)
                        SIMILARITY MATCHING, done here next to the data:
                        returns the stored values of ONE column that look
                        like the noisy value, with scores (and, optionally,
                        their rows). Deciding which records across sources
                        are the same vehicle (entity matching) is left to
                        the Coordinator.

Safety (this service never runs text it has not parsed):
    * every request needs  Authorization: Bearer <token>
    * /api/query accepts ONE plain SELECT, on this source's own tables only;
      no INTO OUTFILE, no locking reads, no variables, no SLEEP/BENCHMARK/
      LOAD_FILE, no comments that MySQL would execute (/*! ... */)
    * the SQL that is executed is regenerated from the parsed tree, not the
      raw text that was sent
    * reads run in a READ ONLY session with an execution time limit
    * /api/execute accepts ONE INSERT/UPDATE/DELETE on ONE owned table; DDL
      is rejected; and it is OFF unless enabled on this laptop
    * MySQL's own GRANTs still apply underneath
    * /api/similar never accepts SQL: the column must be in this source's
      SIMILAR_COLUMNS allow-list and the value is only used as a bound
      parameter / in Python scoring

Phase 3 endpoints (context discovery + unstructured data):
    POST /api/context   {"seeds": [{"table","column","values"}], "match": "exact"|"similar",
                         "query_terms": [...], "intents": [...], "max_depth": 2, ...}  (token)
                        THIS database discovers its own context: starting from the seed
                        rows it walks the FK->PK graph (discovered automatically from
                        information_schema) up and down, scores every row for relevance
                        to the query and returns only the related rows + identifiers.
    POST /api/docsearch {"identifiers": {...}, "keywords": [...], "places": [...],
                         "date_window": [from, to], "k": 5}                  (token)
                        searches THIS machine's documents (unstructured/index, built by
                        phase3/build_doc_index.py) using the query context.
    Tables served = SOURCE_TABLES[source] that exist in the database (so a laptop that
    has not been migrated yet keeps serving only its Phase 2 table).

Terminal response log (for the operator's own verification):
    Every /api/* response is printed as a readable block: who asked, what was
    asked, what is being sent back (matches + scores, row previews, rows
    affected, errors), status, size and time. The API token is never printed.
    ON by default on the registration laptop (vehicles), OFF elsewhere.
        SOURCE_API_VERBOSE=true|false     force it on / off on any laptop
        SOURCE_API_LOG_ROWS=5             rows / matches previewed per response
"""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
import sqlglot
from dotenv import load_dotenv
from flask import (Flask, jsonify, request, render_template_string, redirect,
                   url_for, flash, g)
from sqlglot import exp
from pathlib import Path

load_dotenv()

# fuzzy_match.py (the similarity library) lives in the project root, one level
# above source_api/. Python only puts source_api/ on sys.path, so add the root
# (and the current directory, which is the root when started as documented).
for _root in (Path(__file__).resolve().parent.parent, Path.cwd()):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
try:
    import fuzzy_match
    _FUZZY_IMPORT_ERROR = None
except Exception as _exc:  # keep /api/query etc. working even without it
    fuzzy_match = None
    _FUZZY_IMPORT_ERROR = str(_exc)

# --------------------------------------------------------------------------
# What each source owns, and its default port
# --------------------------------------------------------------------------
SOURCES = {
    #  name        database                   table                 port
    "vehicles":  ("vehicle_registration_db", "vehicles",           5101),
    "insurance": ("insurance_db",            "insurance_policies", 5102),
    "rto":       ("rto_db",                  "rto_records",        5103),
    "theft":     ("theft_db",                "theft_records",      5104),
    "mot":       ("mot_db",                  "mot_reports",        5105),
}

SOURCE_NAME = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("SOURCE_NAME", "")).lower()
if SOURCE_NAME not in SOURCES:
    sys.exit("Usage: python3 source_api/source_api.py <" + "|".join(SOURCES) + ">\n"
             "       (or set SOURCE_NAME in the environment)")

DATABASE, TABLE, DEFAULT_PORT = SOURCES[SOURCE_NAME]
ALLOWED_TABLES = {TABLE}          # Phase 2 name; Phase 3 uses _allowed_tables()

# Token: <SOURCE>_API_TOKEN (the same variable the Coordinator reads), or SOURCE_API_TOKEN.
TOKEN = os.getenv(f"{SOURCE_NAME.upper()}_API_TOKEN") or os.getenv("SOURCE_API_TOKEN", "")
if len(TOKEN) < 8:
    sys.exit(f"Refusing to start: set {SOURCE_NAME.upper()}_API_TOKEN in .env "
             "(at least 8 characters). The same value goes in the Coordinator's .env.")

DB_HOST = os.getenv("SOURCE_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("SOURCE_DB_PORT", os.getenv("DB_PORT", "3306")))
DB_USER = os.getenv("SOURCE_DB_USER") or os.getenv("COORDINATOR_USER")
DB_PASSWORD = os.getenv("SOURCE_DB_PASSWORD") or os.getenv("COORDINATOR_PASSWORD")
API_HOST = os.getenv("SOURCE_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("SOURCE_API_PORT", str(DEFAULT_PORT)))
MAX_ROWS = int(os.getenv("SOURCE_API_MAX_ROWS", "500000"))
QUERY_TIMEOUT_SEC = int(os.getenv("SOURCE_API_QUERY_TIMEOUT_SEC", "20"))
ALLOW_WRITES = os.getenv("SOURCE_API_ALLOW_WRITES", "false").lower() == "true"
MAX_SQL_CHARS = 20000

# Detailed terminal log of every API response (see module docstring).
VERBOSE_LOG = os.getenv(
    "SOURCE_API_VERBOSE", "true" if SOURCE_NAME == "vehicles" else "false"
).lower() == "true"
LOG_PREVIEW_ROWS = int(os.getenv("SOURCE_API_LOG_ROWS", "5"))

# --------------------------------------------------------------------------
# Similarity matching (/api/similar)
# --------------------------------------------------------------------------
# Which columns of THIS source can be fuzzy-matched, and how:
#   plate = OCR-aware plate matcher   code = OCR-aware edit distance
#   name  = any word order, partial   text = general text similarity
# This is also the allow-list: any other column is rejected.
SIMILAR_COLUMNS = {
    "vehicles": {
        "vehicles": {"reg_plate": "plate", "make": "text", "model": "text", "color": "text",
                     "owner_name": "name", "engine_no": "code", "chassis_no": "code"},
        "owners": {"full_name": "name", "phone": "code", "city": "text"},
        "vehicle_models": {"make": "text", "model": "text"},
        "dealers": {"dealer_name": "text", "city": "text"},
    },
    "insurance": {
        "insurance_policies": {"vehicle_number": "plate", "insurer_name": "text",
                               "policy_no": "code"},
        "customers": {"customer_name": "name", "phone": "code"},
        "agents": {"agent_name": "name"},
        "branches": {"insurer_name": "text", "city": "text"},
    },
    "rto": {
        "rto_records": {"car_id": "plate", "rto_office": "text"},
        "rto_offices": {"office_name": "text", "office_code": "code", "city": "text"},
        "challans": {"offence": "text", "location": "text"},
    },
    "theft": {
        "theft_records": {"plate_no": "plate", "status": "text"},
        "firs": {"fir_no": "code", "complainant_name": "name", "complainant_phone": "code"},
        "police_stations": {"station_name": "text", "city": "text"},
        "recoveries": {"location": "text"},
    },
    "mot": {
        "mot_reports": {"vehicle_plate": "plate", "flag_reason": "text", "reported_by": "name"},
    },
}

# Phase 3: every table each source may serve (only those that exist are used).
SOURCE_TABLES = {
    "vehicles": ["vehicles", "owners", "vehicle_models", "dealers", "ownership_transfers"],
    "insurance": ["insurance_policies", "customers", "agents", "branches", "claims"],
    "rto": ["rto_records", "rto_offices", "fitness_certificates", "challans",
            "puc_certificates"],
    "theft": ["theft_records", "police_stations", "firs", "recoveries",
              "shredding_certificates"],
    "mot": ["mot_reports"],
}
# Lookup tables: walking DOWN from them would return thousands of unrelated rows
# (every car of a dealer, every policy of a branch).
NO_DOWNWARD = {
    "vehicles": {"vehicle_models", "dealers"},
    "insurance": {"branches", "agents"},
    "rto": {"rto_offices"},
    "theft": {"police_stations"},
    "mot": set(),
}
# Intent -> tables of THIS source that matter for it (relevance boost).
INTENT_TABLES = {
    "vehicles": {"ownership": {"owners", "ownership_transfers", "vehicles"},
                 "dealer": {"dealers"},
                 "vehicle": {"vehicle_models", "vehicles"}},
    "insurance": {"insurance": {"insurance_policies", "customers"}, "claim": {"claims"},
                  "agent": {"agents", "branches"}},
    "rto": {"compliance": {"challans", "fitness_certificates", "puc_certificates"},
            "registration": {"rto_records", "rto_offices"}},
    "theft": {"theft": {"theft_records", "firs", "police_stations", "recoveries"},
              "scrap": {"shredding_certificates"}},
    "mot": {},
}
# Words that reveal an intent (used when the caller sends only query_terms).
INTENT_LEXICON = {
    "insurance": ["insured", "insurance", "policy", "cover", "expired", "premium", "uninsured"],
    "claim": ["claim", "claims", "damage", "accident", "settled", "surveyor"],
    "theft": ["stolen", "theft", "fir", "police", "missing", "recovered", "found", "station"],
    "scrap": ["scrapped", "shredded", "scrap", "yard"],
    "ownership": ["owner", "owned", "owns", "sold", "transfer", "bought", "history", "seller",
                  "buyer"],
    "dealer": ["dealer", "purchase", "showroom"],
    "vehicle": ["model", "make", "fuel", "body", "seating", "spec"],
    "compliance": ["challan", "fine", "offence", "fitness", "puc", "pollution", "traffic"],
    "registration": ["registration", "renewal", "rto", "office", "registered"],
    "agent": ["agent", "branch"],
}

# Newest record first when several rows share one matched value.
ROW_ORDER = {
    "vehicles": "id DESC",
    "insurance": "policy_end_date DESC",
    "rto": "registration_date DESC",
    "theft": "theft_date DESC",
    "mot": "report_date DESC",
}
SIMILAR_MAX_LIMIT = int(os.getenv("SOURCE_API_SIMILAR_MAX_LIMIT", "25"))
SIMILAR_MAX_VALUE_CHARS = 100
SIMILAR_ROWS_PER_VALUE = int(os.getenv("SOURCE_API_SIMILAR_ROWS_PER_VALUE", "20"))
SIMILAR_CACHE_TTL_SEC = int(os.getenv("SOURCE_API_SIMILAR_TTL", "60"))
SIMILAR_MAX_DISTINCT = int(os.getenv("SOURCE_API_SIMILAR_MAX_DISTINCT", "500000"))
SIMILAR_MIN_SCORE = float(os.getenv("SOURCE_API_SIMILAR_MIN", "0.60"))
SIMILAR_FLOOR = float(os.getenv("SOURCE_API_SIMILAR_FLOOR", "0.25"))

# "table.column" -> (loaded_at, [distinct stored values]); only values, never rows
_similar_cache: dict[str, tuple[float, list]] = {}
_similar_cache_lock = threading.Lock()


def _clear_similar_cache():
    """Called after any write so new/changed values are matched immediately."""
    with _similar_cache_lock:
        _similar_cache.clear()


# --------------------------------------------------------------------------
# Phase 3: schema discovery (tables served + FK graph), cached
# --------------------------------------------------------------------------
SCHEMA_TTL_SEC = int(os.getenv("SOURCE_API_SCHEMA_TTL", "300"))
_schema_cache = {"at": 0.0, "data": None}
_schema_lock = threading.Lock()


def _schema(force: bool = False) -> dict:
    """Tables this source serves, their columns, primary keys and the FK graph.

    Read from information_schema, so FK joins are never hard-coded. A table that
    does not exist yet (laptop not migrated) is simply not served.
    """
    now = time.time()
    with _schema_lock:
        cached = _schema_cache["data"]
        if cached and not force and now - _schema_cache["at"] < SCHEMA_TTL_SEC:
            return cached
    wanted = SOURCE_TABLES.get(SOURCE_NAME, [TABLE])
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = %s ORDER BY TABLE_NAME, ORDINAL_POSITION", (DATABASE,))
        columns: dict[str, list] = {}
        for table, column, dtype in cur.fetchall():
            if table in wanted:
                columns.setdefault(table, []).append((column, str(dtype).lower()))
        cur.execute("SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                    "WHERE TABLE_SCHEMA = %s AND CONSTRAINT_NAME = 'PRIMARY'", (DATABASE,))
        pks = {t: c for t, c in cur.fetchall() if t in columns}
        cur.execute("SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, "
                    "REFERENCED_COLUMN_NAME, CONSTRAINT_NAME FROM "
                    "information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA = %s AND "
                    "REFERENCED_TABLE_NAME IS NOT NULL", (DATABASE,))
        fks = [{"child": c, "child_col": cc, "parent": p, "parent_col": pc, "name": n}
               for c, cc, p, pc, n in cur.fetchall() if c in columns and p in columns]
        cur.close()
        tables = [t for t in wanted if t in columns]
        if TABLE not in tables:
            tables.insert(0, TABLE)
        date_col = {}
        for table, cols in columns.items():
            for column, dtype in cols:
                if dtype in ("date", "datetime", "timestamp"):
                    date_col[table] = column
                    break
        data = {"tables": tables, "columns": {t: [c for c, _ in v] for t, v in columns.items()},
                "types": {t: dict(v) for t, v in columns.items()}, "pks": pks, "fks": fks,
                "date_col": date_col}
        with _schema_lock:
            _schema_cache.update(at=now, data=data)
        return data
    except Exception as exc:                     # DB down: serve the hub table only
        print(f"[schema] discovery failed: {exc!r}", flush=True)
        return {"tables": [TABLE], "columns": {}, "types": {}, "pks": {}, "fks": [],
                "date_col": {}}
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


def _allowed_tables() -> set:
    return set(_schema()["tables"])


def _similar_kinds(table: str) -> dict:
    """{column: kind} that can be similarity-matched in `table` on this source."""
    if table not in _allowed_tables():
        return {}
    return SIMILAR_COLUMNS.get(SOURCE_NAME, {}).get(table, {})

app = Flask(__name__)
app.json.sort_keys = False


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
class Rejected(Exception):
    """The request was refused before reaching MySQL."""


def _connect():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DATABASE, connection_timeout=5,
    )


def _json_safe(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, set):
        return ",".join(sorted(v))
    return v


_FORBIDDEN = re.compile(
    r"\b(sleep|benchmark|load_file|get_lock|release_lock|is_free_lock|is_used_lock|"
    r"sys_exec|sys_eval|outfile|dumpfile|load_data|master_pos_wait)\b", re.I)


def _parse_one(sql: str) -> exp.Expression:
    if not isinstance(sql, str) or not sql.strip():
        raise Rejected("Empty SQL.")
    if len(sql) > MAX_SQL_CHARS:
        raise Rejected("SQL is too long.")
    if "/*!" in sql or "/*+" in sql:
        raise Rejected("Executable comments are not allowed.")
    try:
        trees = [t for t in sqlglot.parse(sql.strip().rstrip(";"), read="mysql") if t]
    except sqlglot.errors.SqlglotError as exc:
        raise Rejected(f"SQL syntax error: {str(exc).splitlines()[0]}")
    if len(trees) != 1:
        raise Rejected("Exactly one statement is allowed.")
    return trees[0]


def _check_common(tree: exp.Expression) -> set[str]:
    """Checks shared by reads and writes. Returns the tables referenced."""
    if any(True for _ in tree.find_all(exp.Parameter, exp.SessionParameter,
                                       exp.Placeholder)):
        raise Rejected("Variables and placeholders are not allowed.")
    tables = set()
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        db = t.args.get("db")
        if t.args.get("catalog") or (db and db.name.lower() != DATABASE.lower()):
            raise Rejected(f"Only the '{DATABASE}' database is reachable here.")
        allowed = _allowed_tables()
        if name not in allowed:
            raise Rejected(f"Table '{t.name}' is not served by this source "
                           f"(allowed: {', '.join(sorted(allowed))}).")
        tables.add(name)
    return tables


def _validate_select(sql: str) -> str:
    tree = _parse_one(sql)
    if not isinstance(tree, exp.Select):
        raise Rejected("Only a plain SELECT is allowed on /api/query.")
    if tree.args.get("into") or tree.args.get("locks") or tree.args.get("with") \
            or tree.args.get("with_"):
        raise Rejected("INTO, locking reads and WITH are not allowed.")
    _check_common(tree)
    safe = tree.sql(dialect="mysql")
    if _FORBIDDEN.search(safe):
        raise Rejected("A function or clause in this query is not allowed.")
    return safe


def _validate_write(sql: str) -> tuple[str, str]:
    tree = _parse_one(sql)
    if not isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
        raise Rejected("Only INSERT, UPDATE or DELETE is allowed on /api/execute.")
    tables = _check_common(tree)
    if len(tables) != 1:
        raise Rejected("A write must touch exactly one table.")
    safe = tree.sql(dialect="mysql")
    if _FORBIDDEN.search(safe):
        raise Rejected("A function or clause in this statement is not allowed.")
    return safe, next(iter(tables))


def _authorised() -> bool:
    header = request.headers.get("Authorization", "")
    supplied = header[7:] if header.lower().startswith("bearer ") \
        else request.headers.get("X-API-Token", "")
    return hmac.compare_digest(supplied.encode(), TOKEN.encode())


@app.before_request
def _gate():
    # Browser UI routes are served by this same Flask process/port.
    # API endpoints other than /api/health still require the bearer token.
    if request.path in {"/api/health", "/api/search"} or not request.path.startswith("/api/"):
        return None
    if not _authorised():
        return jsonify(error="Missing or wrong API token."), 401
    return None


def _read_only_session(cur):
    """READ ONLY session with an execution time limit (MySQL and MariaDB)."""
    try:
        cur.execute("SET SESSION TRANSACTION READ ONLY")
    except mysql.connector.Error:
        pass
    for stmt in (f"SET SESSION MAX_EXECUTION_TIME={QUERY_TIMEOUT_SEC * 1000}",   # MySQL
                 f"SET SESSION max_statement_time={QUERY_TIMEOUT_SEC}"):         # MariaDB
        try:
            cur.execute(stmt)
        except mysql.connector.Error:
            pass


def _log(kind: str, sql: str, note: str = ""):
    one_line = re.sub(r"\s+", " ", sql)[:160]
    print(f"[{datetime.now():%H:%M:%S}] {request.remote_addr} {kind} {one_line} {note}",
          flush=True)


# --------------------------------------------------------------------------
# Terminal response log
# --------------------------------------------------------------------------
# Fields shown first when a row is previewed (others follow if space allows).
_PREVIEW_FIELDS = {
    "vehicles": ("reg_plate", "make", "model", "color", "owner_name",
                 "engine_no", "chassis_no"),
    "insurance": ("vehicle_number", "insurer_name", "policy_no", "policy_end_date"),
    "rto": ("car_id", "rto_office", "registration_date", "renewal_date"),
    "theft": ("plate_no", "status", "theft_date", "shredded_date"),
    "mot": ("vehicle_plate", "report_date", "flag_reason", "reported_by"),
}


def _short(value, width: int = 40) -> str:
    text = "NULL" if value is None else str(value)
    return text if len(text) <= width else text[:width - 1] + "…"


def _row_brief(row) -> str:
    """One readable line for a row given as a dict (or as a list + columns)."""
    if not isinstance(row, dict):
        return " | ".join(_short(v, 24) for v in row)
    preferred = [f for f in _PREVIEW_FIELDS.get(SOURCE_NAME, ()) if f in row]
    keys = preferred or [k for k in row if k != "id"][:6]
    return " | ".join(f"{k}={_short(row.get(k), 28)}" for k in keys)


def _size(num_bytes: int) -> str:
    return f"{num_bytes} B" if num_bytes < 1024 else f"{num_bytes / 1024:.1f} KB"


def _start_timer():
    g._api_t0 = time.perf_counter()


def _request_summary(body: dict) -> list[str]:
    path = request.path
    if path == "/api/similar":
        return [f"request : table={body.get('table') or TABLE!r} column={body.get('column')!r} "
                f"value={body.get('value')!r} limit={body.get('limit', 5)} "
                f"with_rows={bool(body.get('with_rows'))}"]
    if path == "/api/context":
        seeds = "; ".join(f"{s.get('table')}.{s.get('column')} in {s.get('values')}"
                          for s in (body.get("seeds") or []) if isinstance(s, dict))
        return [f"seeds   : {_short(seeds, 200)}  match={body.get('match', 'exact')}",
                f"query   : terms={body.get('query_terms') or []} "
                f"intents={body.get('intents') or '(auto)'} depth={body.get('max_depth', 2)} "
                f"min_relevance={body.get('min_relevance', 0.30)}"]
    if path == "/api/docsearch":
        ids = {k: v for k, v in (body.get("identifiers") or {}).items() if v}
        return [f"context : {_short(json.dumps(ids), 220)}",
                f"query   : keywords={body.get('keywords') or []} places="
                f"{body.get('places') or []} window={body.get('date_window') or '-'} "
                f"k={body.get('k', 5)}"]
    if path in ("/api/query", "/api/execute"):
        sql = re.sub(r"\s+", " ", str(body.get("sql") or "")).strip()
        return [f"sql     : {_short(sql, 300)}"]
    return []


def _response_summary(data: dict) -> list[str]:
    path = request.path
    lines = []
    if "error" in data:
        lines.append(f"ERROR   : {data.get('error')} (code={data.get('code', '-')})")
        return lines

    if path == "/api/similar":
        matches = data.get("matches") or []
        lines.append(
            f"result  : {len(matches)} match(es) from {data.get('candidates_scanned', 0)} "
            f"stored {data.get('column')} values  [kind={data.get('kind')}, "
            f"exact={data.get('exact')}, low_confidence={data.get('low_confidence')}]")
        for i, match in enumerate(matches[:LOG_PREVIEW_ROWS], 1):
            rows = match.get("rows")
            extra = f"   rows={len(rows)}" if rows is not None else ""
            lines.append(f"  {i:>2}. {_short(match.get('value'), 24):<24} "
                         f"score={float(match.get('score', 0)):.4f}{extra}")
            for row in (rows or [])[:2]:
                lines.append(f"        └─ {_row_brief(row)}")
        if len(matches) > LOG_PREVIEW_ROWS:
            lines.append(f"      … {len(matches) - LOG_PREVIEW_ROWS} more match(es)")
    elif path == "/api/context":
        stats = data.get("stats") or {}
        lines.append(f"result  : {stats.get('rows_returned', 0)} context rows "
                     f"(examined {stats.get('rows_examined', 0)}, pruned "
                     f"{stats.get('pruned', 0)})  per table {stats.get('per_table', {})}  "
                     f"intents={data.get('intents')}")
        for node in (data.get("nodes") or [])[:LOG_PREVIEW_ROWS * 2]:
            lines.append(f"  hop {node.get('hop')}  rel {node.get('relevance'):.2f}  "
                         f"{node.get('id'):<28} via {node.get('via') or 'SEED'}")
        if len(data.get("nodes") or []) > LOG_PREVIEW_ROWS * 2:
            lines.append(f"      … {len(data['nodes']) - LOG_PREVIEW_ROWS * 2} more node(s)")
        ids = data.get("identifiers") or {}
        lines.append("ids     : " + _short(", ".join(
            f"{k}={v[:4]}" for k, v in ids.items() if k != "dates"), 300))
    elif path == "/api/docsearch":
        stats = data.get("stats") or {}
        lines.append(f"result  : {stats.get('returned', 0)} document(s) returned, "
                     f"{stats.get('accepted', 0)} accepted of {stats.get('chunks', 0)} chunks, "
                     f"semantic={'on' if stats.get('semantic') else 'off'}")
        for doc in (data.get("docs") or [])[:LOG_PREVIEW_ROWS]:
            lines.append(f"  {doc.get('doc_id'):<26} score={doc.get('score'):.3f}  "
                         f"{_short('; '.join(doc.get('matched_on') or []), 90)}")
    elif path == "/api/query":
        columns, rows = data.get("columns") or [], data.get("rows") or []
        lines.append(f"result  : {data.get('row_count', len(rows))} row(s), "
                     f"truncated={data.get('truncated')}, columns={columns}")
        for row in rows[:LOG_PREVIEW_ROWS]:
            lines.append(f"        └─ {_row_brief(dict(zip(columns, row)))}")
        if len(rows) > LOG_PREVIEW_ROWS:
            lines.append(f"      … {len(rows) - LOG_PREVIEW_ROWS} more row(s)")
    elif path == "/api/execute":
        lines.append(f"result  : rows_affected={data.get('rows_affected')} "
                     f"last_insert_id={data.get('last_insert_id')} "
                     f"table={data.get('table')}")
    elif path == "/api/health":
        lines.append(f"result  : status={data.get('status')} "
                     f"database_reachable={data.get('database_reachable')} "
                     f"writes_enabled={data.get('writes_enabled')}")
    elif path == "/api/schema":
        tables = data.get("tables") or {}
        lines.append("result  : " + ", ".join(
            f"{t}({len(cols)} cols)" for t, cols in tables.items()))
        if data.get("similar_columns"):
            lines.append(f"similar : {data.get('similar_columns')}")
    else:
        lines.append(f"result  : keys={list(data)[:10]}")
    return lines


def _log_response(response):
    """Print a readable block for every /api/* response (never the token)."""
    if not VERBOSE_LOG or not request.path.startswith("/api/"):
        return response
    try:
        t0 = g.get("_api_t0")
        ms = f"{(time.perf_counter() - t0) * 1000:.1f} ms" if t0 else "-"
        body = request.get_json(silent=True) if request.method == "POST" else None
        payload = response.get_data() if not response.direct_passthrough else b""
        data = None
        if response.is_json and payload:
            try:
                data = json.loads(payload)
            except ValueError:
                data = None

        head = (f"[{datetime.now():%Y-%m-%d %H:%M:%S}] RESPONSE {request.method} "
                f"{request.path} -> {response.status_code}  {ms}  "
                f"{_size(len(payload))}  to {request.remote_addr}  "
                f"[source={SOURCE_NAME}, db={DATABASE}]")
        lines = ["", "─" * 100, head]
        lines += _request_summary(body if isinstance(body, dict) else {})
        if isinstance(data, dict):
            lines += _response_summary(data)
        lines.append("─" * 100)
        print("\n".join(lines), flush=True)
    except Exception as exc:       # logging must never break a response
        print(f"[response-log] could not log {request.path}: {exc!r}", flush=True)
    return response


app.before_request(_start_timer)
app.after_request(_log_response)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
@app.get("/api/health")
def health():
    db_ok = True
    try:
        c = _connect()
        c.close()
    except Exception:
        db_ok = False
    return jsonify(status="ok" if db_ok else "degraded", source=SOURCE_NAME,
                   database_reachable=db_ok, writes_enabled=ALLOW_WRITES)


@app.get("/api/schema")
def schema():
    info = _schema(force=True)
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (DATABASE,))
        served = set(info["tables"])
        tables: dict[str, list] = {}
        for t, c, d in cur.fetchall():
            if t in served:
                tables.setdefault(t, []).append({"name": c, "type": d})
        index = _load_doc_index()
        return jsonify(
            source=SOURCE_NAME, database=DATABASE, hub_table=TABLE, tables=tables,
            primary_keys=info["pks"],
            fk_graph=[{"child": f"{f['child']}.{f['child_col']}",
                       "parent": f"{f['parent']}.{f['parent_col']}", "name": f["name"]}
                      for f in info["fks"]],
            similar_columns={t: c for t, c in SIMILAR_COLUMNS.get(SOURCE_NAME, {}).items()
                             if t in served},
            documents={"indexed_chunks": len(index["chunks"]) if index else 0,
                       "semantic": bool(index and index["emb"] is not None),
                       "index_dir": str(DOC_INDEX_DIR)})
    finally:
        conn.close()


@app.post("/api/query")
def query():
    body = request.get_json(silent=True) or {}
    t0 = time.perf_counter()
    try:
        safe_sql = _validate_select(body.get("sql"))
    except Rejected as exc:
        _log("QUERY REJECTED", str(body.get("sql")), f"-> {exc}")
        return jsonify(error=str(exc), code="rejected"), 400

    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        _read_only_session(cur)
        cur.execute(safe_sql)
        columns = list(cur.column_names)
        raw = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(raw) > MAX_ROWS
        rows = [[_json_safe(v) for v in r] for r in raw[:MAX_ROWS]]
        ms = round((time.perf_counter() - t0) * 1000, 1)
        _log("QUERY", safe_sql, f"-> {len(rows)} rows, {ms} ms")
        return jsonify(source=SOURCE_NAME, database=DATABASE, columns=columns,
                       rows=rows, row_count=len(rows), truncated=truncated,
                       elapsed_ms=ms)
    except mysql.connector.Error as exc:
        _log("QUERY DB-ERROR", safe_sql, f"-> {exc}")
        return jsonify(error=str(exc), code="db_error", mysql_errno=exc.errno), 400
    except Exception as exc:  # never leak a traceback
        _log("QUERY FAILED", safe_sql, f"-> {exc!r}")
        return jsonify(error="Internal error in the source API.", code="internal"), 500
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


@app.post("/api/execute")
def execute():
    body = request.get_json(silent=True) or {}
    if not ALLOW_WRITES:
        return jsonify(error=f"Writes are disabled on the {SOURCE_NAME} source API. "
                             "Set SOURCE_API_ALLOW_WRITES=true on that laptop and restart it.",
                       code="writes_disabled"), 403
    try:
        safe_sql, table = _validate_write(body.get("sql"))
    except Rejected as exc:
        _log("WRITE REJECTED", str(body.get("sql")), f"-> {exc}")
        return jsonify(error=str(exc), code="rejected"), 400

    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(safe_sql)
        conn.commit()
        _clear_similar_cache()
        affected, last_id = cur.rowcount, cur.lastrowid
        _log("WRITE", safe_sql, f"-> {affected} rows")
        return jsonify(source=SOURCE_NAME, database=DATABASE, table=table,
                       rows_affected=affected, last_insert_id=last_id)
    except mysql.connector.Error as exc:
        if conn is not None:
            conn.rollback()
        _log("WRITE DB-ERROR", safe_sql, f"-> {exc}")
        return jsonify(error=str(exc), code="db_error", mysql_errno=exc.errno), 400
    except Exception as exc:
        _log("WRITE FAILED", safe_sql, f"-> {exc!r}")
        return jsonify(error="Internal error in the source API.", code="internal"), 500
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


def _distinct_values(conn, column: str, table: str | None = None) -> list:
    """Distinct non-empty values of one allow-listed column, cached briefly."""
    table = table or TABLE
    key = f"{table}.{column}"
    now = time.time()
    with _similar_cache_lock:
        hit = _similar_cache.get(key)
        if hit and now - hit[0] < SIMILAR_CACHE_TTL_SEC:
            return hit[1]
    cur = conn.cursor()
    _read_only_session(cur)
    # `table` / `column` come from SIMILAR_COLUMNS (allow-list) checked against the
    # discovered schema, never from the raw request, so quoting them here is safe.
    cur.execute(
        f"SELECT DISTINCT `{column}` FROM `{table}` "
        f"WHERE `{column}` IS NOT NULL AND `{column}` <> '' "
        f"LIMIT {SIMILAR_MAX_DISTINCT}"
    )
    values = [str(_json_safe(row[0])) for row in cur.fetchall()]
    cur.close()
    with _similar_cache_lock:
        _similar_cache[key] = (now, values)
    return values


def _order_clause(table: str) -> str:
    if table == TABLE:
        return ROW_ORDER.get(SOURCE_NAME, "id DESC")
    schema = _schema()
    column = schema["date_col"].get(table) or schema["pks"].get(table)
    return f"`{column}` DESC" if column else "1"


def _rows_for_values(conn, column: str, values: list, table: str | None = None) -> dict:
    """Rows whose `column` equals each matched value (newest first, capped)."""
    table = table or TABLE
    order = _order_clause(table)
    cur = conn.cursor(dictionary=True)
    rows_by_value = {}
    for value in values:
        cur.execute(
            f"SELECT * FROM `{table}` WHERE `{column}` = %s "
            f"ORDER BY {order} LIMIT {SIMILAR_ROWS_PER_VALUE}",
            (value,),
        )
        rows_by_value[value] = [
            {key: _json_safe(val) for key, val in row.items()}
            for row in cur.fetchall()
        ]
    cur.close()
    return rows_by_value


@app.post("/api/similar")
def similar():
    """Similarity matching for ONE column of this source.

    Request : {"column": "reg_plate", "value": "UPo9AI88@5",
               "limit": 5, "with_rows": true}
    Response: {"matches": [{"value": "UP09AI8815", "score": 0.94,
                            "rows": [...]}, ...], "exact": false,
               "low_confidence": false, "candidates_scanned": 100000, ...}
    """
    body = request.get_json(silent=True) or {}
    t0 = time.perf_counter()

    if fuzzy_match is None:
        return jsonify(error="Similarity matching is unavailable on this source: "
                             f"fuzzy_match.py could not be imported "
                             f"({_FUZZY_IMPORT_ERROR}). Copy fuzzy_match.py to "
                             "the project root and restart.",
                       code="similarity_unavailable"), 503

    table = str(body.get("table") or TABLE).strip().lower()
    allowed = _similar_kinds(table)
    column = str(body.get("column") or "").strip().lower()
    if column not in allowed:
        served = {t: list(c) for t, c in SIMILAR_COLUMNS.get(SOURCE_NAME, {}).items()
                  if t in _allowed_tables()}
        return jsonify(error=f"Column '{table}.{column}' cannot be similarity-matched on the "
                             f"{SOURCE_NAME} source (allowed: {served}).",
                       code="rejected"), 400

    value = body.get("value")
    if not isinstance(value, str) or not value.strip():
        return jsonify(error="Provide a non-empty string 'value'.",
                       code="rejected"), 400
    value = value.strip()
    if len(value) > SIMILAR_MAX_VALUE_CHARS:
        return jsonify(error=f"'value' must be {SIMILAR_MAX_VALUE_CHARS} "
                             "characters or fewer.", code="rejected"), 400

    try:
        limit = int(body.get("limit", 5))
    except (TypeError, ValueError):
        return jsonify(error="'limit' must be an integer.", code="rejected"), 400
    limit = max(1, min(limit, SIMILAR_MAX_LIMIT))
    with_rows = bool(body.get("with_rows", False))
    kind = allowed[column]

    conn = None
    try:
        conn = _connect()
        stored = _distinct_values(conn, column, table)
        result = fuzzy_match.match_value(
            kind, value, stored,
            min_score=SIMILAR_MIN_SCORE,
            max_matches=limit,
            fallback_n=limit,
            floor=SIMILAR_FLOOR,
        )
        matches = [{"value": v, "score": score} for v, score in result["matches"]]
        if with_rows and matches:
            rows = _rows_for_values(conn, column, [m["value"] for m in matches], table)
            for match in matches:
                match["rows"] = rows.get(match["value"], [])

        ms = round((time.perf_counter() - t0) * 1000, 1)
        _log("SIMILAR", f"{table}.{column} ~ {value!r}",
             f"-> {len(matches)} matches of {result['scanned']}, {ms} ms")
        return jsonify(
            source=SOURCE_NAME, database=DATABASE, table=table,
            column=column, kind=kind, query=value,
            exact=result["exact"], low_confidence=result["low_confidence"],
            candidates_scanned=result["scanned"], matches=matches,
            elapsed_ms=ms,
        )
    except mysql.connector.Error as exc:
        _log("SIMILAR DB-ERROR", f"{column} ~ {value!r}", f"-> {exc}")
        return jsonify(error=str(exc), code="db_error", mysql_errno=exc.errno), 400
    except Exception as exc:  # never leak a traceback
        _log("SIMILAR FAILED", f"{column} ~ {value!r}", f"-> {exc!r}")
        return jsonify(error="Internal error in the source API.", code="internal"), 500
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


# --------------------------------------------------------------------------
# Phase 3: POST /api/context — THIS database discovers its own context
# --------------------------------------------------------------------------
CONTEXT_MAX_DEPTH = 3
CONTEXT_MAX_SEEDS = 5
CONTEXT_MAX_SEED_VALUES = 20
CONTEXT_MAX_NODES = int(os.getenv("SOURCE_API_CONTEXT_MAX_NODES", "200"))
CONTEXT_MAX_ROWS_PER_EDGE = 50
HOP_DECAY = [1.00, 0.70, 0.45, 0.30]
INTENT_BOOST = 1.30
OFF_INTENT = 0.85
RECENT_YEARS = 3

PLATE_COLUMNS = {"reg_plate", "vehicle_number", "car_id", "plate_no", "vehicle_plate"}
PERSON_NAME_COLUMNS = {"full_name", "customer_name", "complainant_name", "owner_name"}
ID_COLUMNS = {"fir_no": "fir_nos", "policy_no": "policy_nos", "chassis_no": "chassis",
              "engine_no": "engines", "certificate_no": "certificates",
              "claim_no": "claim_nos"}
# Phones / names are only followed for the people a question is about: owners,
# policy holders and FIR complainants, not agents, dealers, branches or stations.
PERSON_TABLES = {"owners", "customers", "firs", "vehicles"}
CITY_COLUMNS = {"city"}
PLACE_COLUMNS = {"location", "address", "rto_office"}


def _norm_plate_key(value) -> str:
    return re.sub(r"[^A-Z0-9?@#*]", "", str(value or "").upper())


def _phone_digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))[-10:]


def _detect_intents(terms: list[str]) -> list[str]:
    words = {w for t in terms for w in re.findall(r"[a-z]+", t.lower())}
    return [intent for intent, lexicon in INTENT_LEXICON.items() if words & set(lexicon)]


def _expand_terms(terms: list[str], intents: list[str]) -> set:
    words = {w for t in terms for w in re.findall(r"[a-z0-9]+", t.lower()) if len(w) >= 3}
    for intent in intents:
        words |= set(INTENT_LEXICON.get(intent, []))
    return words


def _row_tokens(row: dict) -> set:
    return {w for v in row.values() if v is not None
            for w in re.findall(r"[a-z0-9]+", str(v).lower())}


def _relevance(table, row, hop, seed_score, terms, intents, schema) -> tuple[float, dict]:
    """relevance = hop_decay x intent_boost x (0.7 + 0.3 x term_overlap) x recency x seed."""
    decay = HOP_DECAY[min(hop, len(HOP_DECAY) - 1)]
    boost = 1.0
    if intents:
        mapping = INTENT_TABLES.get(SOURCE_NAME, {})
        wanted = set().union(*(mapping.get(i, set()) for i in intents))
        mapped = set().union(*mapping.values()) if mapping else set()
        if table in wanted:
            boost = INTENT_BOOST
        elif table in mapped:
            boost = OFF_INTENT
    hits = len(terms & _row_tokens(row)) if terms else 0
    overlap = min(1.0, hits / 2)
    recency = 1.0
    date_column = schema["date_col"].get(table)
    if date_column and row.get(date_column):
        try:
            when = date.fromisoformat(str(row[date_column])[:10])
            if (date.today() - when).days > 365 * RECENT_YEARS:
                recency = 0.85
        except ValueError:
            pass
    score = min(1.0, decay * boost * (0.7 + 0.3 * overlap) * recency * seed_score)
    return round(score, 4), {"hop_decay": decay, "intent_boost": boost,
                             "term_hits": hits, "recency": recency}


def _fetch(cur, table, column, value, limit, schema):
    order = schema["date_col"].get(table) or schema["pks"].get(table)
    cur.execute(f"SELECT * FROM `{table}` WHERE `{column}` = %s "
                f"{f'ORDER BY `{order}` DESC' if order else ''} LIMIT {int(limit)}", (value,))
    return [{k: _json_safe(v) for k, v in row.items()} for row in cur.fetchall()]


def _find_seeds(conn, cur, seed, match, min_score, schema):
    """Rows matching one seed: [(row, match_score)]."""
    table = str(seed.get("table") or TABLE).strip().lower()
    column = str(seed.get("column") or "").strip().lower()
    values = seed.get("values")
    if table not in schema["tables"]:
        raise Rejected(f"Table '{table}' is not served by this source "
                       f"(served: {', '.join(schema['tables'])}).")
    if column not in schema["columns"].get(table, []):
        raise Rejected(f"Column '{table}.{column}' does not exist.")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        raise Rejected("Each seed needs a non-empty 'values' list.")
    values = [str(v).strip() for v in values[:CONTEXT_MAX_SEED_VALUES]
              if str(v).strip() and len(str(v)) <= SIMILAR_MAX_VALUE_CHARS]
    kind = _similar_kinds(table).get(column)
    limit = CONTEXT_MAX_ROWS_PER_EDGE
    found = []
    if match == "similar":
        if fuzzy_match is None or kind is None:
            raise Rejected(f"'{table}.{column}' cannot be similarity-matched "
                           "(use match=exact).")
        stored = _distinct_values(conn, column, table)
        best = {}
        for value in values:
            result = fuzzy_match.match_value(kind, value, stored, min_score=min_score,
                                             max_matches=5, fallback_n=0, floor=1.01)
            for stored_value, score in result["matches"]:
                best[stored_value] = max(best.get(stored_value, 0.0), score)
        for stored_value, score in best.items():
            found += [(row, score) for row in _fetch(cur, table, column, stored_value,
                                                     limit, schema)]
        return table, found
    if column in PLATE_COLUMNS or kind == "plate":
        expr = f"REPLACE(REPLACE(UPPER(COALESCE(`{column}`, '')), ' ', ''), '-', '')"
        params = [_norm_plate_key(v) for v in values]
    elif "phone" in column:
        expr = f"RIGHT(REGEXP_REPLACE(COALESCE(`{column}`, ''), '[^0-9]', ''), 10)"
        params = [_phone_digits(v) for v in values]
    else:
        expr, params = f"`{column}`", values
    placeholders = ", ".join(["%s"] * len(params))
    cur.execute(f"SELECT * FROM `{table}` WHERE {expr} IN ({placeholders}) LIMIT {limit}",
                params)
    found = [({k: _json_safe(v) for k, v in row.items()}, 1.0) for row in cur.fetchall()]
    return table, found


def _identifiers(nodes: list[dict], schema) -> dict:
    ids = {"plates": [], "phones": [], "names": [], "fir_nos": [], "policy_nos": [],
           "claim_nos": [], "chassis": [], "engines": [], "certificates": [], "cities": [],
           "places": [], "dates": []}

    def add(key, value):
        if value and value not in ids[key]:
            ids[key].append(value)

    for node in nodes:
        table, row = node["table"], node["row"]
        types = schema["types"].get(table, {})
        for column, value in row.items():
            if value in (None, ""):
                continue
            if column in PLATE_COLUMNS:
                add("plates", _norm_plate_key(value))
            elif "phone" in column:
                if table in PERSON_TABLES:
                    add("phones", _phone_digits(value))
            elif column in PERSON_NAME_COLUMNS:
                if table in PERSON_TABLES:
                    add("names", str(value).strip())
            elif column in ID_COLUMNS:
                add(ID_COLUMNS[column], str(value).strip())
            elif column in CITY_COLUMNS:
                add("cities", str(value).strip())
            elif column in PLACE_COLUMNS:
                add("places", str(value).strip())
            elif types.get(column) in ("date", "datetime", "timestamp"):
                entry = {"table": table, "column": column, "value": str(value)[:10]}
                if entry not in ids["dates"]:
                    ids["dates"].append(entry)
    return {k: v for k, v in ids.items() if v}


@app.post("/api/context")
def context():
    """Context discovery on THIS database by walking its FK->PK graph from seed rows."""
    body = request.get_json(silent=True) or {}
    t0 = time.perf_counter()
    try:
        seeds = body.get("seeds")
        if not isinstance(seeds, list) or not seeds:
            raise Rejected("Provide 'seeds': [{\"table\", \"column\", \"values\"}].")
        seeds = seeds[:CONTEXT_MAX_SEEDS]
        match = str(body.get("match") or "exact").lower()
        if match not in ("exact", "similar"):
            raise Rejected("'match' must be 'exact' or 'similar'.")
        terms = [str(t)[:60] for t in (body.get("query_terms") or [])][:30]
        intents = [str(i).lower() for i in (body.get("intents") or [])][:10] \
            or _detect_intents(terms)
        max_depth = max(0, min(int(body.get("max_depth", 2)), CONTEXT_MAX_DEPTH))
        per_edge = max(1, min(int(body.get("max_rows_per_edge", 20)), CONTEXT_MAX_ROWS_PER_EDGE))
        min_rel = max(0.0, min(float(body.get("min_relevance", 0.30)), 1.0))
        min_seed = max(0.5, min(float(body.get("min_seed_score", 0.85)), 1.0))
    except (TypeError, ValueError):
        return jsonify(error="Invalid numeric parameter.", code="rejected"), 400
    except Rejected as exc:
        return jsonify(error=str(exc), code="rejected"), 400

    schema = _schema(force=False)
    expanded = _expand_terms(terms, intents)
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor(dictionary=True)
        _read_only_session(cur)
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        edge_keys = set()
        frontier = []
        examined = pruned = 0
        for seed in seeds:
            table, found = _find_seeds(conn, cur, seed, match, min_seed, schema)
            pk = schema["pks"].get(table)
            for row, score in found:
                examined += 1
                node_id = f"{table}:{row.get(pk)}"
                if node_id in nodes:
                    continue
                node = {"id": node_id, "table": table, "hop": 0, "relevance": round(score, 4),
                        "seed_score": score, "via": None, "row": row,
                        "why": {"seed_match": round(score, 4)}}
                nodes[node_id] = node
                frontier.append(node)

        for hop in range(1, max_depth + 1):
            next_frontier = []
            for node in frontier:
                table, row = node["table"], node["row"]
                steps = []
                for fk in schema["fks"]:                      # UP: child -> parent
                    if fk["child"] == table and row.get(fk["child_col"]) is not None:
                        steps.append((fk, fk["parent"], fk["parent_col"],
                                      row[fk["child_col"]], 1, "up"))
                if table not in NO_DOWNWARD.get(SOURCE_NAME, set()):
                    for fk in schema["fks"]:                  # DOWN: parent -> children
                        if fk["parent"] == table and row.get(fk["parent_col"]) is not None:
                            steps.append((fk, fk["child"], fk["child_col"],
                                          row[fk["parent_col"]], per_edge, "down"))
                for fk, target, column, value, limit, direction in steps:
                    via = (f"{fk['child']}.{fk['child_col']} -> "
                           f"{fk['parent']}.{fk['parent_col']} ({direction})")
                    pk = schema["pks"].get(target)
                    for found in _fetch(cur, target, column, value, limit, schema):
                        examined += 1
                        node_id = f"{target}:{found.get(pk)}"
                        edge_key = (node["id"], node_id, fk["name"])
                        if node_id in nodes:
                            if edge_key not in edge_keys and node_id != node["id"]:
                                edge_keys.add(edge_key)
                                edges.append({"from": node["id"], "to": node_id,
                                              "fk": fk["name"], "via": via})
                            continue
                        score, why = _relevance(target, found, hop, node["seed_score"],
                                                expanded, intents, schema)
                        if score < min_rel or len(nodes) >= CONTEXT_MAX_NODES:
                            pruned += 1
                            continue
                        new = {"id": node_id, "table": target, "hop": hop, "relevance": score,
                               "seed_score": node["seed_score"], "via": via, "row": found,
                               "why": why}
                        nodes[node_id] = new
                        edge_keys.add(edge_key)
                        edges.append({"from": node["id"], "to": node_id, "fk": fk["name"],
                                      "via": via})
                        next_frontier.append(new)
            frontier = next_frontier
            if not frontier:
                break
        cur.close()

        ordered = sorted(nodes.values(), key=lambda n: (-n["relevance"], n["hop"], n["id"]))
        for n in ordered:
            n.pop("seed_score", None)
        per_table = {}
        for n in ordered:
            per_table[n["table"]] = per_table.get(n["table"], 0) + 1
        ms = round((time.perf_counter() - t0) * 1000, 1)
        _log("CONTEXT", json.dumps(seeds)[:120],
             f"-> {len(ordered)} rows from {len(per_table)} tables, {ms} ms")
        return jsonify(
            source=SOURCE_NAME, database=DATABASE, intents=intents,
            fk_graph=[{"child": f"{f['child']}.{f['child_col']}",
                       "parent": f"{f['parent']}.{f['parent_col']}", "name": f["name"]}
                      for f in schema["fks"]],
            nodes=ordered, edges=edges, identifiers=_identifiers(ordered, schema),
            stats={"rows_examined": examined, "rows_returned": len(ordered),
                   "pruned": pruned, "per_table": per_table, "elapsed_ms": ms},
        )
    except Rejected as exc:
        return jsonify(error=str(exc), code="rejected"), 400
    except mysql.connector.Error as exc:
        _log("CONTEXT DB-ERROR", json.dumps(seeds)[:120], f"-> {exc}")
        return jsonify(error=str(exc), code="db_error", mysql_errno=exc.errno), 400
    except Exception as exc:
        _log("CONTEXT FAILED", json.dumps(seeds)[:120], f"-> {exc!r}")
        return jsonify(error="Internal error in the source API.", code="internal"), 500
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


# --------------------------------------------------------------------------
# Phase 3: POST /api/docsearch — context-driven search of THIS machine's documents
# --------------------------------------------------------------------------
DOC_INDEX_DIR = Path(os.getenv("DOC_INDEX_DIR", "unstructured/index"))
DOC_WEIGHTS = {"entity": 0.45, "bm25": 0.20, "semantic": 0.25, "date_place": 0.10}
DOC_ACCEPT_ENTITY = 0.80
DOC_ACCEPT_SEMANTIC = 0.75
DOC_MIN_SCORE = float(os.getenv("SOURCE_API_DOC_MIN_SCORE", "0.35"))
DOC_MAX_K = 20
NAME_MAX_EVIDENCE = 0.70   # a person name alone never qualifies a document (names repeat)
_doc_index = {"mtime": None, "chunks": [], "bm25": None, "emb": None, "model": None,
              "model_name": None}
_doc_lock = threading.Lock()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


class _BM25:
    """Okapi BM25 over the chunk texts (k1=1.5, b=0.75)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [dict() for _ in docs]
        self.lengths = [len(d) for d in docs]
        self.avg = (sum(self.lengths) / len(docs)) if docs else 0.0
        df = {}
        for i, doc in enumerate(docs):
            for token in doc:
                self.docs[i][token] = self.docs[i].get(token, 0) + 1
            for token in set(doc):
                df[token] = df.get(token, 0) + 1
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, length in zip(self.docs, self.lengths):
            s = 0.0
            for token in query:
                f = tf.get(token)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * length / (self.avg or 1))
                    s += self.idf.get(token, 0.0) * f * (self.k1 + 1) / denom
            out.append(s)
        return out


def _load_doc_index():
    """Load (or reload after a rebuild) unstructured/index/ built by build_doc_index.py."""
    chunks_path = DOC_INDEX_DIR / "chunks.jsonl"
    if not chunks_path.is_file():
        return None
    mtime = chunks_path.stat().st_mtime
    with _doc_lock:
        if _doc_index["mtime"] == mtime:
            return _doc_index
        chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8")
                  .splitlines() if line.strip()]
        _doc_index.update(mtime=mtime, chunks=chunks,
                          bm25=_BM25([_tokens(c["text"]) for c in chunks]),
                          emb=None, model=None, model_name=None)
        meta_path = DOC_INDEX_DIR / "meta.json"
        emb_path = DOC_INDEX_DIR / "embeddings.npy"
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        if emb_path.is_file() and meta.get("model"):
            try:
                import numpy
                _doc_index["emb"] = numpy.load(emb_path)
                _doc_index["model_name"] = meta["model"]
            except Exception as exc:
                print(f"[docsearch] embeddings not loaded ({exc!r}); semantic score off",
                      flush=True)
        print(f"[docsearch] index loaded: {len(chunks)} chunks, semantic="
              f"{'on' if _doc_index['emb'] is not None else 'off'}", flush=True)
        return _doc_index


def _embed_query(text: str):
    """Embedding of the query text, or None when semantic search is unavailable."""
    index = _doc_index
    if index["emb"] is None or not text.strip():
        return None
    try:
        if index["model"] is None:
            from sentence_transformers import SentenceTransformer
            index["model"] = SentenceTransformer(index["model_name"])
        return index["model"].encode([text], normalize_embeddings=True)[0]
    except Exception as exc:
        print(f"[docsearch] semantic disabled: {exc!r}", flush=True)
        index["emb"] = None
        return None


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _entity_match(chunk, ids) -> tuple[float, list[str]]:
    """Best identifier agreement between the query context and one chunk."""
    tags = chunk.get("tags", {})
    best, reasons = 0.0, []

    def consider(score, reason):
        nonlocal best
        if score >= 0.6:
            reasons.append(f"{reason} ({score:.2f})")
        best = max(best, score)

    # A document plate counts only if it is the SAME plate, allowing look-alike
    # characters (0/O 1/I 8/B 5/S 2/Z). Real plates are dense (hundreds share 'DL01AA'),
    # so "similar" plates such as DL01AA9880 vs DL01AA9358 are different vehicles.
    for plate in ids.get("plates", []):
        wanted = _norm_plate_key(plate)
        for tag in tags.get("plates", []):
            if fuzzy_match is None:
                score = float(wanted == tag["norm"])
            elif fuzzy_match.fold_lookalikes(wanted) == fuzzy_match.fold_lookalikes(tag["norm"]):
                score = 1.0 if wanted == tag["norm"] else 0.99
            else:
                # e.g. DL05AE1104 vs DL05AE1704 (1 vs 7) are two registered cars:
                # a near-identical plate is a DIFFERENT vehicle, not evidence.
                continue
            consider(score, f"plate '{tag['raw']}' ~ {plate}")
    phones = {_phone_digits(p) for p in ids.get("phones", [])}
    for phone in tags.get("phones", []):
        if phone in phones:
            consider(1.0, f"phone {phone}")
    for key in ("fir_nos", "policy_nos", "claim_nos", "challan_nos", "certificates"):
        wanted = {re.sub(r"[^A-Z0-9]", "", str(v).upper()) for v in ids.get(key, [])}
        for tag in tags.get("ids", {}).get(key, []):
            if re.sub(r"[^A-Z0-9]", "", tag.upper()) in wanted:
                consider(1.0, f"{key[:-1].replace('_', ' ')} {tag}")
    # Identifiers: one different digit is a different vehicle, so only OCR look-alikes
    # (0/O, 1/I, 8/B, 5/S ...) may differ.
    def fold(value):
        text = re.sub(r"[^A-Z0-9]", "", str(value).upper())
        return fuzzy_match.fold_lookalikes(text) if fuzzy_match else text

    for key in ("chassis", "engines"):
        wanted = {fold(v) for v in ids.get(key, [])}
        for tag in tags.get("ids", {}).get(key, []):
            if fold(tag) in wanted:
                consider(1.0, f"{key.rstrip('s')} {tag}")
    if fuzzy_match is not None:
        words = re.findall(r"[A-Za-z]+", chunk["text"])
        lower = [w.lower() for w in words]
        for name in ids.get("names", [])[:10]:
            parts = re.findall(r"[a-z]+", name.lower())
            if not parts or not any(p in lower for p in parts):
                continue
            n = len(parts)
            # the name must appear as consecutive words ("Rajat Sharma" or "Sharma, Rajat")
            score = max((fuzzy_match.value_similarity("name", name, " ".join(words[i:i + n]))
                         for i in range(len(words) - n + 1)), default=0.0)
            if score >= 0.85:
                consider(min(NAME_MAX_EVIDENCE, score), f"name '{name}'")
    return round(best, 4), reasons


def _snippet(text: str, needles: list[str], width: int = 320) -> str:
    low = text.lower()
    for needle in needles:
        i = low.find(str(needle).lower())
        if i >= 0:
            start = max(0, i - width // 3)
            return ("…" if start else "") + text[start:start + width].strip() + \
                ("…" if start + width < len(text) else "")
    return text[:width].strip() + ("…" if len(text) > width else "")


@app.post("/api/docsearch")
def docsearch():
    """Search this machine's documents using the query CONTEXT (not just the query text)."""
    body = request.get_json(silent=True) or {}
    t0 = time.perf_counter()
    index = _load_doc_index()
    if index is None or not index["chunks"]:
        return jsonify(error=f"No document index on the {SOURCE_NAME} source. Run "
                             "phase3/build_doc_index.py on this laptop.",
                       code="no_index"), 503
    raw_ids = body.get("identifiers") or {}
    if not isinstance(raw_ids, dict):
        return jsonify(error="'identifiers' must be an object.", code="rejected"), 400
    ids = {k: [str(v)[:100] for v in (vals if isinstance(vals, list) else [vals])][:30]
           for k, vals in raw_ids.items()}
    keywords = [str(k)[:60] for k in (body.get("keywords") or [])][:30]
    places = [str(p)[:60] for p in (body.get("places") or [])][:10]
    description = str(body.get("description") or "")[:300]
    window = body.get("date_window") or []
    start = _iso(window[0]) if len(window) == 2 else None
    end = _iso(window[1]) if len(window) == 2 else None
    try:
        k = max(1, min(int(body.get("k", 5)), DOC_MAX_K))
        min_score = float(body.get("min_score", DOC_MIN_SCORE))
    except (TypeError, ValueError):
        return jsonify(error="Invalid k / min_score.", code="rejected"), 400

    chunks = index["chunks"]
    id_tokens = [t for vals in ids.values() for v in vals for t in _tokens(v)]
    id_tokens += [_norm_plate_key(p).lower() for p in ids.get("plates", [])]
    query_tokens = _tokens(" ".join(keywords + places + [description])) + id_tokens
    bm25 = index["bm25"].scores(query_tokens) if query_tokens else [0.0] * len(chunks)
    bm25_max = max(bm25) or 1.0
    query_vec = _embed_query(" ".join([description] + keywords))
    semantic = (index["emb"] @ query_vec).tolist() if query_vec is not None else None
    use_date_place = bool(places or (start and end))
    weights = dict(DOC_WEIGHTS)
    if semantic is None:
        weights.pop("semantic")
    if not use_date_place:
        weights.pop("date_place")
    total_weight = sum(weights.values())

    best_by_doc = {}
    for i, chunk in enumerate(chunks):
        entity, reasons = _entity_match(chunk, ids)
        parts = {"entity": entity, "bm25": round(bm25[i] / bm25_max, 4)}
        if semantic is not None:
            parts["semantic"] = round(max(0.0, semantic[i]), 4)
        if use_date_place:
            date_hit = any(start <= d <= end for d in
                           (_iso(x) for x in chunk.get("tags", {}).get("dates", [])) if d) \
                if start and end else False
            place_hit = any(p.lower() in chunk["text"].lower() for p in places)
            parts["date_place"] = 0.5 * date_hit + 0.5 * place_hit
            if date_hit:
                reasons.append("date inside the context window")
            if place_hit:
                reasons.append("mentions a context place")
        score = sum(weights[name] * parts.get(name, 0.0) for name in weights) / total_weight
        accepted = (entity >= DOC_ACCEPT_ENTITY
                    or parts.get("semantic", 0.0) >= DOC_ACCEPT_SEMANTIC) and score >= min_score
        doc = chunk["doc_id"]
        if accepted and (doc not in best_by_doc or score > best_by_doc[doc]["score"]):
            needles = [r.split("'")[1] for r in reasons if "'" in r] + \
                [v for vals in ids.values() for v in vals]
            best_by_doc[doc] = {"doc_id": doc, "doc_type": chunk.get("doc_type"),
                                "chunk": chunk.get("chunk_no", 0), "score": round(score, 4),
                                "dates": chunk.get("tags", {}).get("dates", [])[:10],
                                "breakdown": parts, "matched_on": reasons,
                                "snippet": _snippet(chunk["text"], needles)}
    docs = sorted(best_by_doc.values(), key=lambda d: -d["score"])[:k]
    ms = round((time.perf_counter() - t0) * 1000, 1)
    _log("DOCSEARCH", json.dumps(ids)[:120], f"-> {len(docs)} docs of {len(chunks)} chunks, {ms} ms")
    return jsonify(source=SOURCE_NAME, docs=docs,
                   stats={"chunks": len(chunks), "accepted": len(best_by_doc),
                          "returned": len(docs), "semantic": semantic is not None,
                          "weights": weights, "elapsed_ms": ms})


# --------------------------------------------------------------------------
# Optional source-specific browser UI on the SAME host/port as the REST API.
# Only theft and MoT have a human-facing add/search interface.
# --------------------------------------------------------------------------
UI_TEMPLATE = r"""
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title><style>
body{font:16px system-ui,sans-serif;background:#f4f6f8;color:#18212b;margin:0;padding:28px}
main{max-width:1100px;margin:auto}h1{margin:0 0 8px}.muted{color:#596575}
section{background:white;border:1px solid #dce2e8;border-radius:12px;padding:20px;margin:18px 0}
form{display:flex;flex-wrap:wrap;gap:12px;align-items:end}label{display:flex;flex-direction:column;gap:5px;font-size:14px}
input{padding:10px;border:1px solid #bbc5d0;border-radius:7px;min-width:180px}
button{padding:10px 16px;border:0;border-radius:7px;background:#174ea6;color:white;cursor:pointer}
table{width:100%;border-collapse:collapse;overflow-wrap:anywhere}th,td{text-align:left;padding:10px;border-bottom:1px solid #e3e7eb}
th{background:#f7f9fb} .msg{padding:10px;background:#eef6ff;border-radius:7px;margin:10px 0}
</style></head><body><main>
<h1>{{ title }}</h1><p class="muted">Source API and UI share this server. API health: <a href="/api/health">/api/health</a></p>
{% for category,message in get_flashed_messages(with_categories=true) %}<div class="msg">{{ message }}</div>{% endfor %}
{% if error %}<div class="msg">{{ error }}</div>{% endif %}
<section><h2>Search records</h2><form method="get" action="/">
<label>Vehicle plate<input name="plate" value="{{ plate }}" placeholder="e.g. DL01AB1234"></label><button type="submit">Search</button><a href="/">Clear</a>
</form><p class="muted">{{ total }} total records; showing {{ records|length }} rows.</p>
<div style="overflow:auto"><table><thead><tr>{% for col in columns %}<th>{{ col }}</th>{% endfor %}</tr></thead><tbody>
{% for row in records %}<tr>{% for col in columns %}<td>{{ row[col] if row[col] is not none else '—' }}</td>{% endfor %}</tr>
{% else %}<tr><td colspan="{{ columns|length or 1 }}">No records found.</td></tr>{% endfor %}
</tbody></table></div></section>
{% if write_enabled %}<section><h2>Add record</h2><form method="post" action="/add">
{% for col in insert_columns %}<label>{{ col }}{% if col in date_columns %}<input type="date" name="{{ col }}">{% else %}<input name="{{ col }}" {% if col in required_columns %}required{% endif %}>{% endif %}</label>{% endfor %}
<button type="submit">Add record</button></form></section>
{% else %}<p class="muted">Adding records is disabled. Set SOURCE_API_ALLOW_WRITES=true to enable it.</p>{% endif %}
</main></body></html>
"""


def _ui_columns(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name, data_type, is_nullable, column_default, extra "
        "FROM information_schema.columns WHERE table_schema=%s AND table_name=%s "
        "ORDER BY ordinal_position", (DATABASE, TABLE))
    meta = cur.fetchall()
    cur.close()
    return meta


def _ui_is_date(data_type):
    return data_type.lower() in {"date", "datetime", "timestamp"}


@app.get("/")
def source_ui():
    if SOURCE_NAME not in {"theft", "mot"}:
        return jsonify(service="source-api", source=SOURCE_NAME,
                       endpoints=["/api/health", "/api/schema", "/api/query", "/api/execute",
                                  "/api/similar", "/api/context", "/api/docsearch"])
    plate = request.args.get("plate", "").strip()
    conn = None
    try:
        conn = _connect()
        meta = _ui_columns(conn)
        columns = [m[0] for m in meta]
        cur = conn.cursor(dictionary=True)
        cur.execute(f"SELECT COUNT(*) AS total FROM `{TABLE}`")
        total = cur.fetchone()["total"]
        if plate and "vehicle_plate" in columns:
            key = re.sub(r"[\\s-]+", "", plate).upper()
            cur.execute(f"SELECT * FROM `{TABLE}` WHERE REPLACE(REPLACE(UPPER(`vehicle_plate`),' ',''),'-','')=%s ORDER BY 1 DESC LIMIT 200", (key,))
        else:
            cur.execute(f"SELECT * FROM `{TABLE}` ORDER BY 1 DESC LIMIT 100")
        records = cur.fetchall()
        cur.close()
        insert_meta = [m for m in meta if "auto_increment" not in str(m[4]).lower()
                       and m[0].lower() not in {"id"} and m[3] is None]
        insert_columns = [m[0] for m in insert_meta]
        required_columns = [m[0] for m in insert_meta if m[2] == "NO" and m[3] is None]
        date_columns = [m[0] for m in insert_meta if _ui_is_date(m[1])]
        return render_template_string(UI_TEMPLATE,
            title="Theft Records" if SOURCE_NAME == "theft" else "MoT Reports",
            plate=plate, columns=columns, records=records, total=total,
            insert_columns=insert_columns, required_columns=required_columns,
            date_columns=date_columns, write_enabled=ALLOW_WRITES, error=None)
    except Exception as exc:
        app.logger.exception("Source UI failed")
        return render_template_string(UI_TEMPLATE,
            title="Theft Records" if SOURCE_NAME == "theft" else "MoT Reports",
            plate=plate, columns=[], records=[], total=0, insert_columns=[],
            required_columns=[], date_columns=[], write_enabled=ALLOW_WRITES,
            error=f"Could not load records: {exc}"), 500
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


@app.post("/add")
def source_ui_add():
    if SOURCE_NAME not in {"theft", "mot"}:
        return jsonify(error="This source has no add-record UI."), 404
    if not ALLOW_WRITES:
        return "Adding records is disabled. Set SOURCE_API_ALLOW_WRITES=true on this source and restart.", 403
    conn = None
    try:
        conn = _connect()
        meta = _ui_columns(conn)
        insert_meta = [m for m in meta if "auto_increment" not in str(m[4]).lower()
                       and m[0].lower() != "id" and m[3] is None]
        allowed = {m[0] for m in insert_meta}
        values = {m[0]: request.form.get(m[0], "").strip() for m in insert_meta}
        required = {m[0] for m in insert_meta if m[2] == "NO" and m[3] is None}
        missing = [name for name in required if not values.get(name)]
        if missing:
            flash("Required fields missing: " + ", ".join(missing), "error")
            return redirect(url_for("source_ui"))
        selected = [name for name, value in values.items() if value != ""]
        if not selected:
            flash("Enter at least one field.", "error")
            return redirect(url_for("source_ui"))
        quoted_cols = ", ".join(f"`{name}`" for name in selected)
        placeholders = ", ".join(["%s"] * len(selected))
        cur = conn.cursor()
        cur.execute(f"INSERT INTO `{TABLE}` ({quoted_cols}) VALUES ({placeholders})",
                    tuple(values[name] for name in selected))
        conn.commit()
        cur.close()
        _clear_similar_cache()
        flash("Record added successfully.", "success")
        return redirect(url_for("source_ui", plate=values.get("vehicle_plate", "")))
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        app.logger.exception("Source UI insert failed")
        flash(f"Could not add record: {exc}", "error")
        return redirect(url_for("source_ui"))
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


# --------------------------------------------------------------------------
# Use the actual source UI Flask app as the server, and attach this source API
# to it. This preserves its routing, static files, url_for(), templates and
# request handlers instead of trying to transplant UI routes into another app.
# --------------------------------------------------------------------------
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path

UI_APP_PATHS = {
    "vehicles": Path("laptop1_registration/app.py"),
    "insurance": Path("laptop2_insurance_new/app.py"),
    "rto": Path("laptop3_rto/app.py"),
    # Theft and MoT keep the built-in UI that is already working.
    "theft": None,
    "mot": None,
}


def _attach_existing_ui():
    global app
    configured = os.getenv("SOURCE_UI_APP")
    candidate = Path(configured).expanduser() if configured else UI_APP_PATHS.get(SOURCE_NAME)
    if candidate is None:
        return
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    if not candidate.is_file():
        raise FileNotFoundError(
            f"UI app for source '{SOURCE_NAME}' was not found at {candidate}. "
            "Run this command from the project root or set SOURCE_UI_APP to the "
            "absolute path of that source's app.py."
        )

    spec = spec_from_file_location(f"source_ui_module_{SOURCE_NAME}", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load source UI app from {candidate}")
    module = module_from_spec(spec)
    # Make the project root available to imports used by the uploaded apps.
    project_root = str(Path.cwd())
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    spec.loader.exec_module(module)

    ui_app = getattr(module, "app", None)
    if ui_app is None or not isinstance(ui_app, Flask):
        raise RuntimeError(f"{candidate} must expose a Flask instance named 'app'")

    # Reuse the exact local MySQL settings already used by the working UI.
    # This prevents /api/health and /api/query from failing just because this
    # API's generic SOURCE_DB_* variables are not present in the UI's .env.
    global DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DATABASE
    if SOURCE_NAME == "vehicles":
        db_cfg = getattr(getattr(module, "registration_app", None), "DB_CONFIG", None)
        if db_cfg:
            DB_HOST = db_cfg.get("host", DB_HOST)
            DB_PORT = int(db_cfg.get("port", DB_PORT))
            DB_USER = db_cfg.get("user", DB_USER)
            DB_PASSWORD = db_cfg.get("password", DB_PASSWORD)
            DATABASE = db_cfg.get("database", DATABASE)
    elif SOURCE_NAME == "rto":
        db_cfg = getattr(module, "DB_CONFIG", None)
        if db_cfg:
            DB_HOST = db_cfg.get("host", DB_HOST)
            DB_PORT = int(db_cfg.get("port", DB_PORT))
            DB_USER = db_cfg.get("user", DB_USER)
            DB_PASSWORD = db_cfg.get("password", DB_PASSWORD)
            DATABASE = db_cfg.get("database", DATABASE)
    elif SOURCE_NAME == "insurance":
        DB_HOST = getattr(module, "HOST", DB_HOST)
        DB_PORT = int(os.getenv("MYSQL_PORT", DB_PORT))
        DB_USER = getattr(module, "USER", DB_USER)
        DB_PASSWORD = getattr(module, "PASSWORD", DB_PASSWORD)
        DATABASE = getattr(module, "DATABASE", DATABASE)

    api_app = app
    # Attach only REST API routes. The source UI's own routes (including
    # /, /add, /find, /static and any source-specific API) remain untouched.
    for rule in list(api_app.url_map.iter_rules()):
        if not rule.rule.startswith("/api/"):
            continue
        view = api_app.view_functions.get(rule.endpoint)
        if view is None:
            continue
        if rule.rule in {r.rule for r in ui_app.url_map.iter_rules()}:
            raise RuntimeError(
                f"Route conflict while attaching API endpoint {rule.rule!r} "
                f"to {candidate}. Rename the conflicting route before starting."
            )
        ui_app.add_url_rule(
            rule.rule,
            endpoint=rule.endpoint,
            view_func=view,
            defaults=rule.defaults,
            methods=rule.methods,
            strict_slashes=rule.strict_slashes,
        )

    # API auth middleware must run on the UI app too. UI routes themselves are
    # unaffected; API endpoints still enforce Bearer-token auth except health
    # and the public /api/search route used by the existing browser UI.
    ui_app.before_request(_start_timer)
    ui_app.before_request(_gate)
    ui_app.after_request(_log_response)
    ui_app.json.sort_keys = False
    app = ui_app
    app.logger.info(
        "Using existing %s UI from %s with REST API on port %s",
        SOURCE_NAME, candidate, API_PORT
    )


_attach_existing_ui()


if __name__ == "__main__":
    print(f"Source REST API for '{SOURCE_NAME}' ({DATABASE}.{TABLE}) "
          f"on http://{API_HOST}:{API_PORT}   writes={'ON' if ALLOW_WRITES else 'off'}   "
          f"similarity={'ON' if fuzzy_match else 'OFF (' + str(_FUZZY_IMPORT_ERROR) + ')'}   "
          f"response-log={'ON' if VERBOSE_LOG else 'off'}",
          flush=True)
    app.run(host=API_HOST, port=API_PORT, debug=False, threaded=True)