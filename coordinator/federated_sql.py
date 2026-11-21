"""
Federated SQL engine for the Coordinator.

The user types ONE SQL statement written against the *global schema*
(vehicles, insurance_policies, rto_records, theft_records, mot_reports).
This module:

  1. PARSES it (sqlglot, MySQL dialect)
  2. DECOMPOSES it: finds which table lives in which source database
  3. PUSHES DOWN projections + single-table WHERE filters, so each source
     DB only sends the columns/rows that are needed
  4. FETCHES from every source in parallel, live, at query time, by sending
     each sub-query to that source laptop's REST API (source_api/source_api.py).
     The Coordinator holds no MySQL connection to any other laptop.
  5. INTEGRATES: joins / aggregates / sub-queries / UNIONs / window
     functions run in a throw-away in-memory engine over the fetched
     fragments (nothing is stored; it is discarded after every query)

Fuzzy predicates (`plate_col = 'NOISY'`) are resolved by SIMILARITY MATCHING
on the owning source (POST /api/similar): the source scores its own stored
values and returns only the best ones, which replace the literal.

No vehicle_master table is built, so the architecture stays
"federated / mediated", the same as mediator.py.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Optional

import sqlglot
from sqlglot import exp

from config import SOURCE_API_TOKENS, SOURCE_API_URLS

# All REST calls to the source laptops go through source_client.py.
from source_client import TABLE_KINDS, api_call as _api_call, similar as _similar

# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
# How long to wait for a source REST API to answer (seconds)
API_TIMEOUT_SEC = int(os.getenv("SOURCE_API_TIMEOUT_SEC", "30"))
HEALTH_TIMEOUT_SEC = 3
MAX_FETCH_ROWS = int(os.getenv("SQL_CONSOLE_MAX_FETCH_ROWS", "200000"))
MAX_DISPLAY_ROWS = int(os.getenv("SQL_CONSOLE_MAX_DISPLAY_ROWS", "1000"))
INTEGRATION_TIMEOUT_SEC = int(os.getenv("SQL_CONSOLE_TIMEOUT_SEC", "20"))
# INSERT/UPDATE/DELETE are routed to the owning source DB only if enabled.
# The source DB's own GRANTs still have the final say.
ALLOW_WRITES = os.getenv("SQL_CONSOLE_ALLOW_WRITES", "false").lower() == "true"

# Fuzzy matching: `col = 'NOISY'` / `col IN (...)` on a fuzzy-capable column is
# sent to the owning source's /api/similar, which scores its stored values
# (thresholds are configured on the source: SOURCE_API_SIMILAR_MIN / _FLOOR).
FUZZY_DEFAULT = os.getenv("SQL_CONSOLE_FUZZY", "true").lower() == "true"
FUZZY_MAX_MATCHES = int(os.getenv("SQL_CONSOLE_FUZZY_TOP", "25"))
# When the best match is strong, keep only matches close to it ('Kumr, Sunita' ->
# 'Sunita Kumar' 0.94, not every 'X Kumar' at 0.70). Equal-score ties (e.g. an
# unreadable '@' character in a plate) are still all kept.
FUZZY_STRONG = 0.85
FUZZY_RELATIVE_MARGIN = 0.15


# --------------------------------------------------------------------------
# Global schema: which table lives in which source database
# --------------------------------------------------------------------------
# type codes: I = integer, R = real/decimal, T = text/date
TABLES: dict[str, dict] = {
    "vehicles": {
        "source": "vehicles",
        "database": "vehicle_registration_db",
        "plate_column": "reg_plate",
        "columns": {
            "id": "I", "reg_plate": "T", "make": "T", "model": "T",
            "color": "T", "owner_name": "T", "engine_no": "T",
            "chassis_no": "T",
        },
    },
    "insurance_policies": {
        "source": "insurance",
        "database": "insurance_db",
        "plate_column": "vehicle_number",
        "columns": {
            "id": "I", "vehicle_number": "T", "insurer_name": "T",
            "policy_no": "T", "policy_start_date": "T",
            "policy_end_date": "T", "premium_amount": "R",
        },
    },
    "rto_records": {
        "source": "rto",
        "database": "rto_db",
        "plate_column": "car_id",
        "columns": {
            "id": "I", "car_id": "T", "registration_date": "T",
            "renewal_date": "T", "rto_office": "T",
        },
    },
    "theft_records": {
        "source": "theft",
        "database": "theft_db",
        "plate_column": "plate_no",
        "columns": {
            "id": "I", "plate_no": "T", "theft_date": "T",
            "status": "T", "shredded_date": "T",
        },
    },
    "mot_reports": {
        "source": "mot",
        "database": "mot_db",
        "plate_column": "vehicle_plate",
        "columns": {
            "id": "I", "vehicle_plate": "T", "report_date": "T",
            "flag_reason": "T", "reported_by": "T",
        },
    },
}


# Phase 3: tables added on each source (entity information split out of the hub
# table, joined by FK -> PK inside each source database). They have no plate
# column, so plate_key is not available on them; join them to their hub table
# with the FK columns (e.g. vehicles.owner_id = owners.owner_id).
# A table that a laptop has not created yet simply returns a source error.
_P3 = {
    # registration (M2)
    "owners": ("vehicles", "vehicle_registration_db", {
        "owner_id": "I", "full_name": "T", "phone": "T", "email": "T", "address": "T",
        "city": "T", "date_of_birth": "T"}),
    "vehicle_models": ("vehicles", "vehicle_registration_db", {
        "model_id": "I", "make": "T", "model": "T", "fuel_type": "T", "body_type": "T",
        "seating": "I"}),
    "dealers": ("vehicles", "vehicle_registration_db", {
        "dealer_id": "I", "dealer_name": "T", "city": "T", "gstin": "T"}),
    "ownership_transfers": ("vehicles", "vehicle_registration_db", {
        "transfer_id": "I", "vehicle_id": "I", "from_owner_id": "I", "to_owner_id": "I",
        "transfer_date": "T", "remarks": "T"}),
    # insurance (M3)
    "customers": ("insurance", "insurance_db", {
        "customer_id": "I", "customer_name": "T", "phone": "T", "email": "T", "city": "T"}),
    "agents": ("insurance", "insurance_db", {
        "agent_id": "I", "agent_name": "T", "phone": "T", "branch_id": "I"}),
    "branches": ("insurance", "insurance_db", {
        "branch_id": "I", "insurer_name": "T", "city": "T", "phone": "T"}),
    "claims": ("insurance", "insurance_db", {
        "claim_id": "I", "claim_no": "T", "policy_id": "I", "claim_date": "T", "claim_type": "T",
        "amount": "R", "status": "T", "summary": "T"}),
    # RTO (M4)
    "rto_offices": ("rto", "rto_db", {
        "office_id": "I", "office_code": "T", "office_name": "T", "city": "T", "state": "T"}),
    "fitness_certificates": ("rto", "rto_db", {
        "cert_id": "I", "rto_record_id": "I", "issue_date": "T", "expiry_date": "T",
        "result": "T", "inspector": "T"}),
    "challans": ("rto", "rto_db", {
        "challan_id": "I", "rto_record_id": "I", "challan_date": "T", "offence": "T",
        "location": "T", "fine_amount": "R", "paid": "I"}),
    "puc_certificates": ("rto", "rto_db", {
        "puc_id": "I", "rto_record_id": "I", "test_date": "T", "valid_till": "T",
        "co_level": "R", "result": "T"}),
    # theft (M5)
    "police_stations": ("theft", "theft_db", {
        "station_id": "I", "station_code": "T", "station_name": "T", "city": "T",
        "phone": "T"}),
    "firs": ("theft", "theft_db", {
        "fir_id": "I", "fir_no": "T", "station_id": "I", "filed_on": "T",
        "complainant_name": "T", "complainant_phone": "T"}),
    "recoveries": ("theft", "theft_db", {
        "recovery_id": "I", "theft_id": "I", "recovery_date": "T", "location": "T",
        "vehicle_condition": "T"}),
    "shredding_certificates": ("theft", "theft_db", {
        "cert_id": "I", "theft_id": "I", "scrap_yard": "T", "shred_date": "T",
        "certificate_no": "T"}),
}
for _name, (_source, _db, _cols) in _P3.items():
    TABLES[_name] = {"source": _source, "database": _db, "plate_column": None,
                     "columns": _cols}
# FK columns added to the Phase 2 hub tables
TABLES["vehicles"]["columns"].update({"owner_id": "I", "model_id": "I", "dealer_id": "I"})
TABLES["insurance_policies"]["columns"].update({"customer_id": "I", "agent_id": "I"})
TABLES["rto_records"]["columns"].update({"office_id": "I"})
TABLES["theft_records"]["columns"].update({"station_id": "I", "fir_id": "I"})

# Which columns get fuzzy matching, and how (same map the sources use):
#   plate = OCR-aware plate matcher     code = OCR-aware edit distance
#   name  = token-based (any word order, partial names)    text = general text
# Dates, ids and amounts are always matched exactly.
FUZZY_COLUMNS: dict[str, dict[str, str]] = {
    table: TABLE_KINDS.get(table, {}) for table in TABLES
}

PLATE_KEY = "plate_key"  # virtual column: normalised plate, same rule as mediator.py


class QueryError(Exception):
    """A user-facing problem with the submitted SQL."""

    def __init__(self, message: str, plan: Optional[dict] = None):
        super().__init__(message)
        self.plan = plan


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _normalized_sql(column: str) -> str:
    """Same normalisation as mediator._normalized_sql (MySQL side)."""
    return f"REPLACE(REPLACE(UPPER(COALESCE({column}, '')), ' ', ''), '-', '')"


def _normalize_plate(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip()
    return re.sub(r"[\s\-]", "", value).upper() if value else None


def _py_value(v: Any) -> Any:
    """Convert MySQL values into things SQLite can store / JSON can show."""
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
    return v


def _known_table(node: exp.Table) -> Optional[str]:
    name = node.name.lower()
    return name if name in TABLES else None


def _parse(sql: str) -> exp.Expression:
    sql = (sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Please enter a SQL query.")
    try:
        trees = [t for t in sqlglot.parse(sql, read="mysql") if t is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise QueryError("SQL syntax error. Please check the statement. "
                         f"(parser: {str(exc).splitlines()[0]})")
    if len(trees) != 1:
        raise QueryError("Please submit exactly one SQL statement at a time.")
    return trees[0]


def _strip_db_qualifiers(tree: exp.Expression) -> exp.Expression:
    tree = tree.copy()
    for t in tree.find_all(exp.Table):
        if t.args.get("db"):
            t.set("db", None)
        if t.args.get("catalog"):
            t.set("catalog", None)
    return tree


def _validate_tables(tree: exp.Expression) -> list[exp.Table]:
    """Return every real (non-CTE) table reference; reject unknown ones."""
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    refs = []
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        if not name:
            continue
        if name in cte_names and not t.args.get("db"):
            continue
        if name not in TABLES:
            raise QueryError(
                f"Unknown table '{t.name}'. Tables in the global schema: "
                + ", ".join(TABLES)
            )
        db = t.args.get("db")
        if db and db.name.lower() != TABLES[name]["database"].lower():
            raise QueryError(
                f"Table '{name}' lives in database "
                f"'{TABLES[name]['database']}', not '{db.name}'."
            )
        refs.append(t)
    return refs


# --------------------------------------------------------------------------
# Fuzzy resolution (noisy value -> values really stored, scored ON THE SOURCE)
# --------------------------------------------------------------------------
def _apply_fuzzy(tree: exp.Expression, refs: list[exp.Table],
                 similar_fn: Optional[Callable] = None,
                 notes: Optional[list] = None) -> list[dict]:
    """
    Rewrite  column = 'typed'  /  column IN ('typed',..)  for any fuzzy-capable
    column into  column IN (<stored values that best match>)  in place, and
    return a description of what was done for the plan view.

    The matching itself runs on the owning source (POST /api/similar);
    `similar_fn` is injectable so this can be unit-tested without the APIs.
    """
    similar_fn = similar_fn or _similar

    alias_map: dict[str, str] = {}
    names = set()
    for t in refs:
        n = _known_table(t)
        if n:
            names.add(n)
            alias_map[t.alias_or_name.lower()] = n
            alias_map[n] = n

    def target(col: exp.Column) -> Optional[tuple[str, str, str]]:
        """(table, real column, kind) or None."""
        cn = col.name.lower()
        if col.table:
            tn = alias_map.get(col.table.lower())
            cands = [tn] if tn else []
        else:
            cands = [n for n in names
                     if cn in TABLES[n]["columns"]
                     or (cn == PLATE_KEY and TABLES[n]["plate_column"])]
        if len(cands) != 1:
            return None
        tn = cands[0]
        if cn == PLATE_KEY:
            if not TABLES[tn]["plate_column"]:
                return None
            return tn, TABLES[tn]["plate_column"], "plate"
        kind = FUZZY_COLUMNS.get(tn, {}).get(cn)
        return (tn, cn, kind) if kind else None

    sites = []  # (node, column, [literals])
    for node in list(tree.find_all(exp.EQ, exp.In)):
        if isinstance(node, exp.EQ):
            l, r = node.left, node.right
            if isinstance(l, exp.Column) and isinstance(r, exp.Literal) and r.is_string:
                sites.append((node, l, [r.this]))
            elif isinstance(r, exp.Column) and isinstance(l, exp.Literal) and l.is_string:
                sites.append((node, r, [l.this]))
        else:
            col = node.this
            exprs = node.expressions
            if (isinstance(col, exp.Column) and exprs and not node.args.get("query")
                    and all(isinstance(e, exp.Literal) and e.is_string for e in exprs)):
                sites.append((node, col, [e.this for e in exprs]))

    steps: list[dict] = []
    for node, col, literals in sites:
        # A '%' inside a literal means the user wants a wildcard pattern
        # ("DL01%" = every plate starting with DL01). Treat `= 'x%'` as LIKE and
        # skip fuzzy matching, which would otherwise read '%' as a garbled character.
        if any("%" in lit for lit in literals):
            if isinstance(node, exp.EQ):
                node.replace(exp.Like(this=col.copy(),
                                      expression=exp.Literal.string(literals[0])))
                if notes is not None:
                    notes.append(f"{col.name} = '{literals[0]}' contains %, so it was "
                                 "run as a LIKE pattern (all values that fit the "
                                 "pattern), not as a fuzzy match.")
            continue
        tgt = target(col)
        if tgt is None:
            continue
        tn, real_col, kind = tgt
        spec = TABLES[tn]
        t0 = time.perf_counter()
        per_literal, matched, scanned, via = [], [], 0, None
        for lit in literals:
            try:
                res = similar_fn(spec["source"], real_col, lit,
                                 limit=FUZZY_MAX_MATCHES, table=tn)
            except Exception as exc:
                raise QueryError(
                    f"Fuzzy matching needs {spec['source']} "
                    f"({spec['database']}), which failed: {exc}")
            scanned = max(scanned, int(res.get("candidates_scanned") or 0))
            via = res.get("via") or via
            found = res.get("matches") or []
            best = max((m["score"] for m in found), default=0.0)
            if best >= FUZZY_STRONG:
                found = [m for m in found if m["score"] >= best - FUZZY_RELATIVE_MARGIN]
            res = dict(res, matches=found)
            per_literal.append({
                "query": lit, "exact": bool(res.get("exact")),
                "low_confidence": bool(res.get("low_confidence")),
                "matches": [{"plate": m["value"], "score": m["score"]}
                            for m in res.get("matches") or []]})
            matched += [m["value"] for m in res.get("matches") or []]

        is_key = col.name.lower() == PLATE_KEY
        values = sorted({_normalize_plate(v) if is_key else v for v in matched if v})
        original_pred = node.sql(dialect="mysql")
        if values:  # nothing close at all -> leave predicate alone (empty result)
            node.replace(exp.In(this=col.copy(),
                                expressions=[exp.Literal.string(v) for v in values]))
        steps.append({
            "table": tn, "source": spec["source"], "database": spec["database"],
            "column": real_col, "kind": kind, "original": original_pred,
            "literals": per_literal, "candidates_scanned": scanned,
            "matched_on": "coordinator (fallback)" if via == "coordinator-fallback"
                          else "source",
            "rewritten": bool(values),
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        })
    return steps


# --------------------------------------------------------------------------
# Decomposition: pushdown analysis
# --------------------------------------------------------------------------
def _null_supplied_aliases(select: exp.Select) -> set[str]:
    """Aliases on the null-extended side of an outer join (unsafe to pre-filter)."""
    from_ = select.args.get("from") or select.args.get("from_")
    order: list[str] = []
    if from_ is not None and from_.this is not None:
        order.append(from_.this.alias_or_name.lower())
    unsafe: set[str] = set()
    for j in select.args.get("joins") or []:
        side = (j.side or "").upper()
        name = j.this.alias_or_name.lower() if j.this is not None else ""
        if side in ("RIGHT", "FULL"):
            unsafe.update(order)
        if side in ("LEFT", "FULL"):
            unsafe.add(name)
        order.append(name)
    return unsafe


def _build_fragments(tree: exp.Expression, refs: list[exp.Table]) -> dict[str, dict]:
    """
    For each global table used, decide which columns to fetch and which
    WHERE conjuncts can be pushed down to its source database.
    """
    names = sorted({_known_table(t) for t in refs if _known_table(t)})
    occurrences: dict[str, list[exp.Table]] = {n: [] for n in names}
    for t in refs:
        occurrences[_known_table(t)].append(t)

    # ---- projection pushdown -------------------------------------------
    all_cols_needed = any(
        isinstance(s, exp.Star) and not isinstance(s.parent, exp.Count)
        for s in tree.find_all(exp.Star)
    )
    mentioned = {c.name.lower() for c in tree.find_all(exp.Column)}

    # ---- selection pushdown (only for a plain top-level SELECT) ----------
    pushable: dict[str, list[exp.Expression]] = {n: [] for n in names}
    if isinstance(tree, exp.Select) and not tree.args.get("with") and not tree.args.get("with_"):
        unsafe = _null_supplied_aliases(tree)
        where = tree.args.get("where")
        conjuncts: list[exp.Expression] = []
        if where is not None:
            cond = where.this
            conjuncts = list(cond.flatten()) if isinstance(cond, exp.And) else [cond]

        for name in names:
            occ = occurrences[name]
            if len(occ) != 1:
                continue
            t = occ[0]
            if t.find_ancestor(exp.Select) is not tree:
                continue
            alias = t.alias_or_name.lower()
            if alias in unsafe:
                continue
            my_cols = set(TABLES[name]["columns"]) | (
                {PLATE_KEY} if TABLES[name]["plate_column"] else set())
            other_cols: set[str] = set()
            for other in names:
                if other != name:
                    other_cols |= set(TABLES[other]["columns"]) | (
                        {PLATE_KEY} if TABLES[other]["plate_column"] else set())

            for c in conjuncts:
                if any(isinstance(n, (exp.Subquery, exp.Select, exp.Exists))
                       for n in c.walk()):
                    continue
                cols = list(c.find_all(exp.Column))
                if not cols:
                    continue
                ok = True
                for col in cols:
                    q = col.table.lower() if col.table else ""
                    cn = col.name.lower()
                    if q:
                        if q not in (alias, name) or cn not in my_cols:
                            ok = False
                    else:
                        if cn not in my_cols or cn in other_cols:
                            ok = False
                if ok:
                    pushable[name].append(c)

    fragments: dict[str, dict] = {}
    for name in names:
        spec = TABLES[name]
        if all_cols_needed:
            cols = list(spec["columns"])
        else:
            cols = [c for c in spec["columns"] if c in mentioned]
            if (PLATE_KEY in mentioned and spec["plate_column"]
                    and spec["plate_column"] not in cols):
                cols.append(spec["plate_column"])
            if not cols:
                cols = ["id"]  # e.g. COUNT(*): still need one column per row

        # build pushed filter fragments in MySQL dialect
        filters_sql = []
        for c in pushable[name]:
            c = c.copy()
            for col in list(c.find_all(exp.Column)):
                if col.name.lower() == PLATE_KEY:
                    # placeholder, swapped for the normalising expression below
                    col.replace(exp.column("__PLATE_KEY__"))
                else:
                    col.set("table", None)
            filters_sql.append(c.sql(dialect="mysql").replace(
                "__PLATE_KEY__", _normalized_sql(spec["plate_column"])))

        sql = f"SELECT {', '.join(cols)} FROM {name}"
        if filters_sql:
            sql += " WHERE " + " AND ".join(f"({f})" for f in filters_sql)
        sql += f" LIMIT {MAX_FETCH_ROWS + 1}"

        fragments[name] = {
            "table": name,
            "source": spec["source"],
            "database": spec["database"],
            "columns": cols,
            "pushed_filters": filters_sql,
            "sql": sql,
            "needs_plate_key": PLATE_KEY in mentioned,
        }
    return fragments


# --------------------------------------------------------------------------
# Live fetch from one source database
# --------------------------------------------------------------------------
# LAN calls to the source laptops must not go through a system HTTP proxy.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HEALTH_SOURCES = {
    "vehicles": ("Registration", "vehicle_registration_db"),
    "insurance": ("Insurance", "insurance_db"),
    "rto": ("RTO", "rto_db"),
    "theft": ("Theft", "theft_db"),
}


def _endpoint(source: str, path: str = "/api/query") -> str:
    base = SOURCE_API_URLS.get(source, "")
    return f"{base}{path}" if base else ""


def check_source_health() -> list[dict]:
    """Check database reachability for each of the four federated source APIs."""
    def check_one(source: str, label: str, database: str) -> dict:
        base = SOURCE_API_URLS.get(source, "")
        if not base:
            return {
                "source": label, "database": database, "available": False,
                "error": f"No REST API URL configured for '{source}'.",
            }

        req = urllib.request.Request(base + "/api/health", method="GET")
        try:
            with _OPENER.open(req, timeout=HEALTH_TIMEOUT_SEC) as resp:
                health = json.loads(resp.read().decode("utf-8"))
            available = health.get("database_reachable") is True
            return {
                "source": label, "database": database, "available": available,
                "error": None if available else f"{label} database is not reachable.",
            }
        except Exception as exc:
            return {
                "source": label, "database": database, "available": False,
                "error": str(exc),
            }

    with ThreadPoolExecutor(max_workers=len(HEALTH_SOURCES)) as pool:
        checks = [
            pool.submit(check_one, source, label, database)
            for source, (label, database) in HEALTH_SOURCES.items()
        ]
        return [check.result() for check in checks]


def _api_fetch(source: str, sql: str) -> tuple[list[str], list[tuple]]:
    """Run one sub-query on a source via its REST API; same contract as the old DB fetch."""
    data = _api_call(source, "/api/query", {"sql": sql})
    return data["columns"], [tuple(r) for r in data["rows"]]


def _fetch_fragment(frag: dict, fetcher: Callable) -> dict:
    t0 = time.perf_counter()
    out = dict(frag)
    try:
        cols, rows = fetcher(frag["source"], frag["sql"])
        out.update(
            status="ok", error=None, rows=rows, fetched_columns=cols,
            rows_fetched=min(len(rows), MAX_FETCH_ROWS),
            truncated=len(rows) > MAX_FETCH_ROWS,
        )
        if out["truncated"]:
            out["rows"] = rows[:MAX_FETCH_ROWS]
    except Exception as exc:  # network down, permission denied, ...
        out.update(status="error", error=str(exc), rows=[], fetched_columns=[],
                   rows_fetched=0, truncated=False)
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out


# --------------------------------------------------------------------------
# Integration engine (in-memory, per query)
# --------------------------------------------------------------------------
def _load_into_engine(conn: sqlite3.Connection, name: str, frag: dict) -> None:
    spec = TABLES[name]
    cols = frag["fetched_columns"]
    sqltype = {"I": "INTEGER", "R": "REAL", "T": "TEXT COLLATE NOCASE"}
    # NOCASE mimics MySQL's default case-insensitive comparison
    defs = [f'"{c}" {sqltype[spec["columns"][c]]}' for c in cols]
    add_key = frag["needs_plate_key"] and spec["plate_column"] in cols
    if add_key:
        defs.append(f'"{PLATE_KEY}" TEXT COLLATE NOCASE')
    conn.execute(f'CREATE TABLE "{name}" ({", ".join(defs)})')

    pidx = cols.index(spec["plate_column"]) if add_key else None
    data = []
    for row in frag["rows"]:
        vals = [_py_value(v) for v in row]
        if add_key:
            vals.append(_normalize_plate(row[pidx]))
        data.append(vals)
    marks = ",".join("?" * len(defs))
    conn.executemany(f'INSERT INTO "{name}" VALUES ({marks})', data)


def _make_engine() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.create_function("now", 0, lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.create_function("curdate", 0, lambda: date.today().isoformat())
    conn.create_function("concat", -1,
                         lambda *a: None if any(x is None for x in a)
                         else "".join(str(x) for x in a))
    return conn


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def _plan_view(original: str, final_sql: Optional[str], frags: dict,
               fuzzy: Optional[list] = None) -> dict:
    return {
        "fuzzy": fuzzy or [],
        "original_sql": original,
        "integration_sql": final_sql,
        "subqueries": [
            {
                "table": f["table"], "source": f["source"],
                "database": f["database"], "sql": f["sql"],
                "endpoint": _endpoint(f["source"]),
                "columns": f["columns"], "pushed_filters": f["pushed_filters"],
                "status": f.get("status", "planned"),
                "error": f.get("error"),
                "rows_fetched": f.get("rows_fetched"),
                "ms": f.get("ms"), "truncated": f.get("truncated", False),
            }
            for f in frags.values()
        ],
    }


def _meta_command(sql: str) -> Optional[dict]:
    s = sql.strip().rstrip(";").strip()
    if re.fullmatch(r"(?i)show\s+tables", s):
        rows = [[n, spec["database"], spec["source"]] for n, spec in TABLES.items()]
        return {"columns": ["table", "database", "source"], "rows": rows}
    m = re.fullmatch(r"(?i)(?:describe|desc|show\s+columns\s+from)\s+`?(\w+)`?", s)
    if m:
        name = m.group(1).lower()
        if name not in TABLES:
            raise QueryError(f"Unknown table '{m.group(1)}'. Tables: " + ", ".join(TABLES))
        tmap = {"I": "int", "R": "decimal", "T": "text/date"}
        rows = [[c, tmap[t]] for c, t in TABLES[name]["columns"].items()]
        if TABLES[name]["plate_column"]:
            rows.append([PLATE_KEY + " (virtual)", "normalised plate, joins across sources"])
        return {"columns": ["column", "type"], "rows": rows}
    return None


def run_federated(sql: str, explain_only: bool = False,
                  fetcher: Optional[Callable] = None,
                  fuzzy: Optional[bool] = None) -> dict:
    """
    Execute one SQL statement across the source databases.
    `fetcher` is injectable so the engine can be unit-tested without MySQL.
    """
    t_start = time.perf_counter()
    fetcher = fetcher or _api_fetch
    try:
        meta = _meta_command(sql)
        if meta:
            return {"ok": True, "kind": "meta", "row_count": len(meta["rows"]),
                    "truncated": False, "warnings": [], "plan": None, **meta}

        tree = _parse(sql)

        # ---- writes -----------------------------------------------------
        if isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
            return _run_write(tree, sql, fetcher)
        if not isinstance(tree, exp.Query):
            raise QueryError(
                "Only SELECT (incl. JOIN, GROUP BY, sub-queries, CTEs, UNION), "
                "SHOW TABLES, DESCRIBE and single-table INSERT/UPDATE/DELETE "
                "are supported. DDL is not allowed through the coordinator."
            )

        # ---- decompose ----------------------------------------------------
        refs = _validate_tables(tree)
        use_fuzzy = FUZZY_DEFAULT if fuzzy is None else bool(fuzzy)
        pattern_notes: list[str] = []
        fuzzy_steps = (_apply_fuzzy(tree, refs, notes=pattern_notes)
                       if use_fuzzy else [])
        frags = _build_fragments(tree, refs)
        engine_tree = _strip_db_qualifiers(tree)
        try:
            integration_sql = engine_tree.sql(dialect="sqlite")
        except sqlglot.errors.SqlglotError as exc:
            raise QueryError(f"Cannot translate this query: {exc}")

        if explain_only or not frags:
            if not frags:  # e.g. SELECT 1+1 : no source needed
                eng = _make_engine()
                cur = eng.execute(integration_sql)
                cols = [d[0] for d in cur.description]
                rows = [[_py_value(v) for v in r] for r in cur.fetchall()]
                eng.close()
                return {"ok": True, "kind": "select", "columns": cols, "rows": rows,
                        "row_count": len(rows), "truncated": False, "warnings": [],
                        "plan": _plan_view(sql, integration_sql, frags, fuzzy_steps)}
            return {"ok": True, "kind": "explain", "columns": [], "rows": [],
                    "row_count": 0, "truncated": False, "warnings": [],
                    "plan": _plan_view(sql, integration_sql, frags, fuzzy_steps)}

        # ---- fetch all fragments in parallel, live ------------------------
        with ThreadPoolExecutor(max_workers=len(frags)) as pool:
            futures = {n: pool.submit(_fetch_fragment, f, fetcher)
                       for n, f in frags.items()}
            fetched = {n: fu.result() for n, fu in futures.items()}

        failed = [f for f in fetched.values() if f["status"] != "ok"]
        if failed:
            msg = "; ".join(f"{f['source']} ({f['database']}): {f['error']}"
                            for f in failed)
            raise QueryError(
                "Cannot answer correctly because a source database failed: " + msg,
                plan=_plan_view(sql, integration_sql, fetched, fuzzy_steps),
            )

        warnings = pattern_notes + [
            f"{f['table']}: fetch hit the {MAX_FETCH_ROWS:,}-row cap, "
            "result may be incomplete. Add a WHERE filter."
            for f in fetched.values() if f["truncated"]
        ]

        # ---- integrate -----------------------------------------------------
        t_int = time.perf_counter()
        eng = _make_engine()
        try:
            for name, f in fetched.items():
                _load_into_engine(eng, name, f)
            deadline = time.perf_counter() + INTEGRATION_TIMEOUT_SEC
            eng.set_progress_handler(
                lambda: 1 if time.perf_counter() > deadline else 0, 100000)
            try:
                cur = eng.execute(integration_sql)
                cols = [d[0] for d in cur.description]
                raw = cur.fetchmany(MAX_DISPLAY_ROWS + 1)
                total_known = len(raw)
                if len(raw) > MAX_DISPLAY_ROWS:
                    total_known = MAX_DISPLAY_ROWS + len(cur.fetchall())
            except sqlite3.OperationalError as exc:
                if "interrupted" in str(exc).lower():
                    raise QueryError(
                        f"Query exceeded {INTEGRATION_TIMEOUT_SEC}s while joining "
                        "the fetched data. Add join conditions or filters.",
                        plan=_plan_view(sql, integration_sql, fetched, fuzzy_steps))
                raise QueryError(f"Query error: {exc}",
                                 plan=_plan_view(sql, integration_sql, fetched, fuzzy_steps))
        finally:
            eng.close()

        rows = [[_py_value(v) for v in r] for r in raw[:MAX_DISPLAY_ROWS]]
        truncated = total_known > MAX_DISPLAY_ROWS
        if truncated:
            warnings.append(f"Showing the first {MAX_DISPLAY_ROWS:,} of "
                            f"{total_known:,} rows.")
        plan = _plan_view(sql, integration_sql, fetched, fuzzy_steps)
        plan["integration_ms"] = round((time.perf_counter() - t_int) * 1000, 1)
        plan["total_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
        return {"ok": True, "kind": "select", "columns": cols, "rows": rows,
                "row_count": total_known, "truncated": truncated,
                "warnings": warnings, "plan": plan}

    except QueryError as exc:
        return {"ok": False, "error": str(exc), "plan": exc.plan}
    except Exception as exc:  # never let the console crash the app
        return {"ok": False, "error": f"Unexpected error: {exc}", "plan": None}


def _run_write(tree: exp.Expression, original: str, fetcher: Callable) -> dict:
    refs = _validate_tables(tree)
    targets = {_known_table(t) for t in refs}
    if len(targets) != 1:
        raise QueryError(
            "A write may touch exactly one source table. Cross-database writes "
            "need distributed transactions, which this system does not provide.")
    name = next(iter(targets))
    spec = TABLES[name]
    if not ALLOW_WRITES:
        raise QueryError(
            "Write statements are disabled. Set SQL_CONSOLE_ALLOW_WRITES=true in "
            ".env to route INSERT/UPDATE/DELETE to the owning source database.")
    sql = _strip_db_qualifiers(tree).sql(dialect="mysql")
    t0 = time.perf_counter()
    try:
        result = _api_call(spec["source"], "/api/execute", {"sql": sql})
        affected = result.get("rows_affected", 0)
    except Exception as exc:
        hint = ""
        if "denied" in str(exc).lower():
            verb = sql.split(None, 1)[0].upper()
            m = re.search(r"user '([^']+)'@'([^']+)'", str(exc))
            acct = f"'{m.group(1)}'@'{m.group(2)}'" if m else "'coordinator'@'%'"
            hint = (f"\n\nThe {spec['source']} REST API connected to its MySQL as {acct} "
                    f"and that account has no {verb} right on {spec['database']}.{name}. "
                    f"On the {spec['source']} laptop run:\n"
                    f"GRANT {verb} ON {spec['database']}.{name} TO {acct}; "
                    f"FLUSH PRIVILEGES;")
        raise QueryError(f"{spec['source']} ({spec['database']}) rejected the "
                         f"statement: {exc}{hint}")
    ms = round((time.perf_counter() - t0) * 1000, 1)
    plan = {"original_sql": original, "integration_sql": None, "subqueries": [{
        "table": name, "source": spec["source"], "database": spec["database"],
        "endpoint": _endpoint(spec["source"], "/api/execute"),
        "sql": sql, "columns": [], "pushed_filters": [], "status": "ok",
        "error": None, "rows_fetched": affected, "ms": ms, "truncated": False}]}
    return {"ok": True, "kind": "write", "columns": ["rows_affected"],
            "rows": [[affected]], "row_count": 1, "truncated": False,
            "warnings": [], "plan": plan}