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
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)
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

# Cosmetic only: badge each MoT report by violation category.
FLAG_CATEGORIES = (
    ("insurance", ("insur", "uninsured", "no policy")),
    ("emissions", ("emission", "pollution", "puc")),
    ("registration", ("registration", "rc ", "ownership", "mismatch")),
    ("safety", ("safety", "brake", "tyre", "tire", "fitness")),
    ("licensing", ("licence", "license", "permit")),
)


def classify_flag(reason):
    text = (reason or "").lower()
    for category, keywords in FLAG_CATEGORIES:
        if any(kw in text for kw in keywords):
            return category
    return "general"


UI_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }} · {{ brand_name }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
:root{
  --navy:#0D1B2E;--navy-2:#14283F;--paper:#F4F5F7;--surface:#fff;
  --ink:#14202F;--ink-2:#55637A;--ink-3:#8592A6;--line:#E3E7EE;--line-strong:#CDD4DF;
  --brass:#B8914A;--brass-deep:#96722F;
  --b-insurance:#A33A3A;--b-insurance-bg:#FBEBEA;--b-emissions:#8A6212;--b-emissions-bg:#FAF1DC;
  --b-registration:#285E8E;--b-registration-bg:#E6F0F9;--b-safety:#6B3F8C;--b-safety-bg:#F1E8F7;
  --b-licensing:#1F6B50;--b-licensing-bg:#E3F3EC;--b-general:#46536B;--b-general-bg:#EAEDF2;
  --ok:#1F6B50;--ok-bg:#E3F3EC;--err:#A33A3A;--err-bg:#FBEBEA;
}
*{box-sizing:border-box}
body{margin:0;font-family:"Manrope",system-ui,sans-serif;font-size:15px;line-height:1.55;color:var(--ink);background:var(--paper);-webkit-font-smoothing:antialiased}
:focus-visible{outline:2px solid var(--brass);outline-offset:2px}
.wrap{max-width:1120px;margin:0 auto;padding:0 28px}
.masthead{background:radial-gradient(900px 380px at 85% -20%,rgba(184,145,74,.22),transparent 60%),linear-gradient(180deg,var(--navy),var(--navy-2));color:#fff;padding:34px 0 120px;border-bottom:3px solid var(--brass)}
.brand{display:flex;align-items:center;gap:16px}
.seal{flex:none;width:48px;height:48px;border-radius:50%;border:1.5px solid var(--brass);display:grid;place-items:center;font-family:"Newsreader",serif;font-weight:600;font-size:15px;letter-spacing:.06em;color:var(--brass);box-shadow:inset 0 0 0 4px var(--navy),inset 0 0 0 5px rgba(184,145,74,.5)}
.brand-name{font-size:14px;font-weight:600}
.brand-sub{font-size:12.5px;color:rgba(255,255,255,.58)}
.source-chip{display:inline-flex;align-items:center;gap:7px;margin-top:20px;padding:6px 11px;
  border:1px solid rgba(255,255,255,.22);border-radius:999px;background:rgba(255,255,255,.08);
  color:rgba(255,255,255,.88);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
.source-chip::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--brass)}
.hero{margin-top:56px;max-width:640px}
.hero h1{font-family:"Newsreader",serif;font-weight:500;font-size:clamp(34px,5vw,50px);line-height:1.08;letter-spacing:-.015em;margin:0 0 14px}
.hero p{margin:0;color:rgba(255,255,255,.68);font-size:16px;max-width:52ch}
.search-shell{margin-top:-44px;position:relative;z-index:2}
.search-card{background:var(--surface);border-radius:14px;padding:22px 24px;box-shadow:0 24px 48px -16px rgba(13,27,46,.35),0 2px 6px rgba(13,27,46,.08);display:flex;align-items:center;gap:28px;flex-wrap:wrap}
.search-form{flex:1 1 420px;display:flex;gap:10px;align-items:center}
.search-field{flex:1;position:relative}
.search-field svg{position:absolute;left:15px;top:50%;transform:translateY(-50%);color:var(--ink-3);pointer-events:none}
.search-field input{padding-left:44px;height:50px;font-family:"JetBrains Mono",monospace;letter-spacing:.06em}
.search-field input::placeholder{font-family:"Manrope",sans-serif;letter-spacing:0}
.tally{display:flex;gap:28px;padding-left:28px;border-left:1px solid var(--line)}
.tally-num{font-family:"Newsreader",serif;font-size:30px;font-weight:500;line-height:1;font-variant-numeric:tabular-nums;color:var(--navy)}
.tally-label{font-size:12.5px;color:var(--ink-2);margin-top:6px;max-width:15ch;line-height:1.35}
.main{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:28px;align-items:start;margin-top:28px;padding-bottom:90px}
.main.no-form{grid-template-columns:minmax(0,1fr)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px rgba(13,27,46,.04),0 12px 32px -18px rgba(13,27,46,.18);transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.card:hover{transform:translateY(-2px);border-color:var(--line-strong);box-shadow:0 18px 36px -22px rgba(13,27,46,.3)}
.card-head{padding:22px 26px 18px;border-bottom:1px solid var(--line);display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap}
.card-head h2{font-family:"Newsreader",serif;font-weight:500;font-size:22px;margin:0}
.card-head .meta{font-size:13px;color:var(--ink-2)}
.card-head p{margin:4px 0 0;font-size:13px;color:var(--ink-2);flex-basis:100%}
.alerts{margin-top:24px}
.success,.error{padding:13px 16px;border-radius:10px;margin-bottom:10px;font-size:14px;font-weight:500;border:1px solid}
.success{background:var(--ok-bg);color:var(--ok);border-color:rgba(31,107,80,.25)}
.error{background:var(--err-bg);color:var(--err);border-color:rgba(163,58,58,.25)}
.table-container{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);padding:13px 20px;background:#F5F7FA;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:15px 20px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14.5px;overflow-wrap:anywhere}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:#FAFBFD}
.col-id{color:var(--ink-3);font-variant-numeric:tabular-nums;font-size:13px}
.plate{display:inline-flex;align-items:stretch;border:1.5px solid var(--navy);border-radius:6px;overflow:hidden;background:#fff;font-family:"JetBrains Mono",monospace;font-weight:600;font-size:14px;letter-spacing:.1em;color:var(--navy);white-space:nowrap}
.plate::before{content:"IND";display:grid;place-items:center;padding:0 6px;background:var(--navy);color:#fff;font-size:8.5px;letter-spacing:.08em}
.plate span{padding:4px 10px}
.badge{display:inline-flex;align-items:center;padding:4px 10px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:.02em;margin:0 0 6px;border:1px solid transparent}
.badge-insurance{background:var(--b-insurance-bg);color:var(--b-insurance)}
.badge-emissions{background:var(--b-emissions-bg);color:var(--b-emissions)}
.badge-registration{background:var(--b-registration-bg);color:var(--b-registration)}
.badge-safety{background:var(--b-safety-bg);color:var(--b-safety)}
.badge-licensing{background:var(--b-licensing-bg);color:var(--b-licensing)}
.badge-general{background:var(--b-general-bg);color:var(--b-general)}
.badge-stolen{background:var(--err-bg);color:var(--err);border-color:rgba(163,58,58,.16)}
.badge-recovered{background:var(--ok-bg);color:var(--ok);border-color:rgba(31,107,80,.16)}
.badge-shredded{background:var(--b-general-bg);color:var(--b-general);border-color:rgba(70,83,107,.12)}
.badge-other{background:var(--b-registration-bg);color:var(--b-registration);border-color:rgba(40,94,142,.12)}
.source-theft{--brass:#E87972;--brass-deep:#B74643;--navy:#17243A;--navy-2:#24354F}
.source-theft .masthead{
  background:radial-gradient(800px 350px at 88% -20%,rgba(232,121,114,.24),transparent 62%),
  linear-gradient(145deg,#17243A 0%,#26364F 65%,#34415B 100%);
  border-bottom-color:#E87972}
.source-theft .seal{border-color:#E87972;color:#FFB5A9;
  box-shadow:inset 0 0 0 4px #17243A,inset 0 0 0 5px rgba(232,121,114,.5)}
.source-theft .source-chip::before{background:#FF9D8E}
.source-theft button{background:linear-gradient(135deg,#A94442,#873838)}
.source-theft button:hover{background:linear-gradient(135deg,#B84D49,#963D3A)}
.source-theft input:focus,.source-theft textarea:focus{
  border-color:#D97068;box-shadow:0 0 0 4px rgba(217,112,104,.16)}
.source-theft .clear-button:hover{border-color:#D97068;color:#A94442}
.flag-text{display:block;max-width:46ch}
.empty{text-align:center;padding:56px 26px;color:var(--ink-2)}
.empty strong{display:block;font-family:"Newsreader",serif;font-weight:500;font-size:20px;color:var(--ink);margin-bottom:4px}
.side{position:sticky;top:24px}
form.report{padding:22px 26px 26px}
.field{margin-bottom:18px}
label{display:block;font-size:13px;font-weight:600;margin-bottom:7px}
.req{color:var(--brass-deep)}
input,textarea{width:100%;padding:11px 14px;border:1px solid var(--line-strong);border-radius:10px;background:#FBFCFD;font-family:inherit;font-size:14.5px;color:var(--ink);transition:border-color .15s,box-shadow .15s,background .15s}
input::placeholder,textarea::placeholder{color:#9AA6B8}
input:focus,textarea:focus{outline:none;background:#fff;border-color:var(--brass);box-shadow:0 0 0 4px rgba(184,145,74,.16)}
input.plate-input{font-family:"JetBrains Mono",monospace;letter-spacing:.08em;text-transform:uppercase}
textarea{min-height:96px;resize:vertical}
button{height:50px;padding:0 24px;border:0;border-radius:10px;background:var(--navy);color:#fff;font-family:inherit;font-size:14.5px;font-weight:600;cursor:pointer;box-shadow:0 8px 18px -8px rgba(13,27,46,.6);transition:background .15s}
button:hover{background:#1B3556}
button.brass{width:100%;background:linear-gradient(180deg,#C4A15C,var(--brass-deep));box-shadow:0 10px 20px -10px rgba(150,114,47,.8)}
button.brass:hover{background:linear-gradient(180deg,#CCAA66,#9F7A35)}
.clear-button{flex:none;height:50px;display:inline-flex;align-items:center;padding:0 18px;border:1px solid var(--line-strong);border-radius:10px;color:var(--ink-2);text-decoration:none;font-weight:600;font-size:14px}
.clear-button:hover{border-color:var(--brass);color:var(--brass-deep)}
.note{padding:18px 26px;color:var(--ink-2);font-size:13.5px}
@media(max-width:960px){.main{grid-template-columns:1fr}.side{position:static;order:-1}}
@media(max-width:680px){
  .wrap{padding:0 18px}.masthead{padding-bottom:104px}.hero{margin-top:38px}
  .search-card{padding:18px;gap:18px}.search-form{flex-direction:column;align-items:stretch;flex-basis:100%}
  .search-form button,.clear-button{width:100%;justify-content:center}
  .tally{padding-left:0;border-left:0;border-top:1px solid var(--line);padding-top:16px;width:100%}
  th,td{padding-left:14px;padding-right:14px}
}
</style>
</head>
<body class="source-{{ source_key }}">

<header class="masthead"><div class="wrap">
  <div class="brand">
    <div class="seal" aria-hidden="true">{{ brand_mark }}</div>
    <div>
      <div class="brand-name">{{ brand_name }}</div>
      <div class="brand-sub">{{ subtitle }}</div>
    </div>
  </div>
  <div class="hero">
    <span class="source-chip">{{ source_label }}</span>
    <h1>{{ headline }}</h1>
    <p>{{ tagline }}</p>
  </div>
</div></header>

<div class="wrap">

  <div class="search-shell"><div class="search-card">
    <form class="search-form" method="get" action="/" role="search">
      <div class="search-field">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
        <input name="plate" value="{{ plate }}" placeholder="Search by vehicle plate, e.g. DL01AB1002" aria-label="Vehicle plate">
      </div>
      <button type="submit">Search</button>
      {% if plate %}<a href="/" class="clear-button">Show all</a>{% endif %}
    </form>
    <div class="tally">
      <div><div class="tally-num">{{ total }}</div><div class="tally-label">Total {{ record_plural }} in database</div></div>
      <div><div class="tally-num">{{ records|length }}</div>
        <div class="tally-label">{% if plate %}{{ record_plural|title }} for {{ plate }}{% else %}Latest {{ record_plural }} shown{% endif %}</div></div>
    </div>
  </div></div>

  {% set msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs or error %}
  <div class="alerts">
    {% for category, message in msgs %}<div class="{{ 'success' if category == 'success' else 'error' }}" role="status">{{ message }}</div>{% endfor %}
    {% if error %}<div class="error" role="alert">{{ error }}</div>{% endif %}
  </div>
  {% endif %}

  <div class="main {% if not write_enabled %}no-form{% endif %}">

    <section class="card" aria-labelledby="ledger-title">
      <div class="card-head">
        <h2 id="ledger-title">{% if plate %}{{ record_plural|title }} for {{ plate }}{% else %}Latest {{ record_plural }}{% endif %}</h2>
        <span class="meta">{{ records|length }} {{ record_singular if records|length == 1 else record_plural }}</span>
      </div>
      <div class="table-container"><table>
        <thead><tr>{% for col in columns %}<th>{{ col.replace('_', ' ')|capitalize }}</th>{% endfor %}</tr></thead>
        <tbody>
        {% for row in records %}
          <tr>
          {% for col in columns %}
            <td{% if loop.first and col == 'id' %} class="col-id"{% endif %}>
              {%- if col == 'vehicle_plate' and row[col] -%}
                <span class="plate"><span>{{ row[col] }}</span></span>
              {%- elif col == 'flag_reason' -%}
                {% if row['_badge'] %}<span class="badge badge-{{ row['_badge'] }}">{{ row['_badge']|capitalize }}</span>{% endif %}
                <span class="flag-text">{{ row[col] if row[col] is not none else '—' }}</span>
              {%- elif col == 'status' -%}
                {% set status_value = (row[col] or '')|lower %}
                {% if status_value == 'stolen' %}<span class="badge badge-stolen">{{ row[col] }}</span>
                {% elif status_value == 'recovered' %}<span class="badge badge-recovered">{{ row[col] }}</span>
                {% elif status_value == 'shredded' %}<span class="badge badge-shredded">{{ row[col] }}</span>
                {% else %}<span class="badge badge-other">{{ row[col] if row[col] else '—' }}</span>{% endif %}
              {%- else -%}
                {{ row[col] if row[col] is not none else '—' }}
              {%- endif -%}
            </td>
          {% endfor %}
          </tr>
        {% else %}
          <tr><td colspan="{{ columns|length or 1 }}" class="empty">
            <strong>No records found</strong>
            {% if plate %}Check the plate for typos{% if write_enabled %}, or add a record using the form{% endif %}.{% else %}Nothing has been filed yet.{% endif %}
          </td></tr>
        {% endfor %}
        </tbody>
      </table></div>
    </section>

    {% if write_enabled %}
    <aside class="card side" aria-labelledby="form-title">
      <div class="card-head"><h2 id="form-title">{{ form_heading }}</h2><p>{{ form_description }}</p></div>
      <form class="report" method="post" action="/add">
        {% for col in insert_columns %}
        <div class="field">
          <label for="f_{{ col }}">{{ col.replace('_', ' ')|capitalize }}{% if col in required_columns %} <span class="req">*</span>{% endif %}</label>
          {% if col in date_columns %}
            <input id="f_{{ col }}" type="date" name="{{ col }}" {% if col in required_columns %}required{% endif %}>
          {% elif col == 'flag_reason' %}
            <textarea id="f_{{ col }}" name="{{ col }}" placeholder="UNINSURED — no policy on record" {% if col in required_columns %}required{% endif %}></textarea>
          {% else %}
            <input id="f_{{ col }}" name="{{ col }}" {% if col == 'vehicle_plate' %}class="plate-input" placeholder="DL01AB1002"{% endif %} {% if col in required_columns %}required{% endif %}>
          {% endif %}
        </div>
        {% endfor %}
        <button type="submit" class="brass">{{ submit_label }}</button>
      </form>
    </aside>
    {% else %}
    <p class="note">Adding records is disabled. Set SOURCE_API_ALLOW_WRITES=true to enable it.</p>
    {% endif %}

  </div>
</div>
</body>
</html>
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


def _ui_copy():
    if SOURCE_NAME == "mot":
        return dict(source_key="mot", title="MoT Reports",
                    brand_name="Ministry of Transportation", brand_mark="MOT",
                    source_label="Compliance reporting",
                    subtitle="Vehicle Compliance Registry",
                    headline="Every flag on file, one plate at a time.",
                    tagline="Search a vehicle to see its full compliance history, "
                            "or file a new report against a plate.",
                    record_singular="report", record_plural="reports",
                    form_heading="File a compliance report",
                    form_description="Record a vehicle compliance issue for review.",
                    submit_label="Submit report")
    return dict(source_key="theft", title="Theft & Shredding Records",
                brand_name="Theft & Shredding Registry", brand_mark="TS",
                source_label="Theft and recovery records",
                subtitle="Vehicle Safety Register",
                headline="A clear view of every theft and recovery record.",
                tagline="Search a plate to see every theft record on file, "
                        "or add a new record when reporting is enabled.",
                record_singular="record", record_plural="theft records",
                form_heading="Add a theft record",
                form_description="Record a theft, recovery, or shredding update.",
                submit_label="Add theft record")


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
            key = re.sub(r"[\s-]+", "", plate).upper()
            cur.execute(f"SELECT * FROM `{TABLE}` WHERE REPLACE(REPLACE(UPPER(`vehicle_plate`),' ',''),'-','')=%s ORDER BY 1 DESC LIMIT 200", (key,))
        else:
            cur.execute(f"SELECT * FROM `{TABLE}` ORDER BY 1 DESC LIMIT 100")
        records = cur.fetchall()
        cur.close()
        for r in records:
            r["_badge"] = classify_flag(r.get("flag_reason")) if SOURCE_NAME == "mot" else None
        insert_meta = [m for m in meta if "auto_increment" not in str(m[4]).lower()
                       and m[0].lower() not in {"id"} and m[3] is None]
        insert_columns = [m[0] for m in insert_meta]
        required_columns = [m[0] for m in insert_meta if m[2] == "NO" and m[3] is None]
        date_columns = [m[0] for m in insert_meta if _ui_is_date(m[1])]
        return render_template_string(UI_TEMPLATE, **_ui_copy(),
            plate=plate, columns=columns, records=records, total=total,
            insert_columns=insert_columns, required_columns=required_columns,
            date_columns=date_columns, write_enabled=ALLOW_WRITES, error=None)
    except Exception as exc:
        app.logger.exception("Source UI failed")
        return render_template_string(UI_TEMPLATE, **_ui_copy(),
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

UI_APP_PATHS = {
    "vehicles": Path("laptop1_registration/app.py"),
    "insurance": Path("laptop2_insurance_new/app.py"),
    "rto": Path("laptop3_rto/app.py"),
    # Theft and MoT use the built-in UI above (MoT carries the redesigned
    # premium layout). Set SOURCE_UI_APP to override with a separate app.py.
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