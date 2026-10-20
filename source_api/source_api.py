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
"""

from __future__ import annotations

import hmac
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import mysql.connector
import sqlglot
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template_string, redirect, url_for, flash
from sqlglot import exp

load_dotenv()

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
ALLOWED_TABLES = {TABLE}

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
        if name not in ALLOWED_TABLES:
            raise Rejected(f"Table '{t.name}' is not served by this source "
                           f"(allowed: {', '.join(sorted(ALLOWED_TABLES))}).")
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


def _log(kind: str, sql: str, note: str = ""):
    one_line = re.sub(r"\s+", " ", sql)[:160]
    print(f"[{datetime.now():%H:%M:%S}] {request.remote_addr} {kind} {one_line} {note}",
          flush=True)


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
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = %s ORDER BY table_name, ordinal_position", (DATABASE,))
        tables: dict[str, list] = {}
        for t, c, d in cur.fetchall():
            if t.lower() in ALLOWED_TABLES:
                tables.setdefault(t, []).append({"name": c, "type": d})
        return jsonify(source=SOURCE_NAME, database=DATABASE, tables=tables)
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
                       endpoints=["/api/health", "/api/schema", "/api/query", "/api/execute"])
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent

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
        candidate = (Path.cwd() if configured else PROJECT_ROOT) / candidate
    if not candidate.is_file():
        raise FileNotFoundError(
            f"UI app for source '{SOURCE_NAME}' was not found at {candidate}. "
            "Check the project layout or set SOURCE_UI_APP to the absolute path "
            "of that source's app.py."
        )

    spec = spec_from_file_location(f"source_ui_module_{SOURCE_NAME}", candidate)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load source UI app from {candidate}")
    module = module_from_spec(spec)
    # Make the project root available to imports used by the uploaded apps.
    project_root = str(PROJECT_ROOT)
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
    ui_app.before_request(_gate)
    ui_app.json.sort_keys = False
    app = ui_app
    app.logger.info(
        "Using existing %s UI from %s with REST API on port %s",
        SOURCE_NAME, candidate, API_PORT
    )


_attach_existing_ui()


if __name__ == "__main__":
    print(f"Source REST API for '{SOURCE_NAME}' ({DATABASE}.{TABLE}) "
          f"on http://{API_HOST}:{API_PORT}   writes={'ON' if ALLOW_WRITES else 'off'}",
          flush=True)
    app.run(host=API_HOST, port=API_PORT, debug=False, threaded=True)