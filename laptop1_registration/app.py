"""
laptop1_registration/app.py

Standalone management app for Laptop 1's own database
(vehicle_registration_db). Runs locally on this laptop only — it does
not know about the coordinator, the other laptops, or the federated
lookup. Its job is: let whoever operates this laptop Find, Append, or
Edit rows in the `vehicles` table, with real validation so bad data
never gets a chance to flow downstream into the coordinator's merge.

Uses the SAME root .env as the rest of the project (config.py,
import_real_data.py, etc). python-dotenv's load_dotenv() walks up
parent directories automatically, so this file finds the repo-root
.env even though it lives one folder deeper — no separate .env needed.
Reads: VEHICLES_HOST, DB_PORT, COORDINATOR_USER, COORDINATOR_PASSWORD.
The 'coordinator' user's existing SELECT/INSERT/UPDATE grant on
vehicle_registration_db (see coordinator_user.sql) is all this app
needs — it never deletes rows.
"""

import os
import re

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, redirect, url_for

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("VEHICLES_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("COORDINATOR_USER"),
    "password": os.getenv("COORDINATOR_PASSWORD"),
    "database": "vehicle_registration_db",
}

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# Same normalization the coordinator's integration_engine.py uses, kept in
# sync here on purpose: this laptop should reject plates in whatever raw
# shape they're typed, but store/display the canonical form so downstream
# entity resolution never has to guess.
PLATE_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}$")
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,99}$")
ALNUM_ID_RE = re.compile(r"^[A-Za-z0-9]{5,30}$")


def normalize_plate(raw):
    if raw is None:
        return ""
    return re.sub(r"[\s\-]", "", raw.strip().upper())


def validate_vehicle(form, editing_plate=None):
    """
    Returns (errors: list[str], cleaned: dict).
    cleaned only contains keys worth trusting if errors is empty.
    """
    errors = []
    cleaned = {}

    raw_plate = form.get("reg_plate", "")
    plate = normalize_plate(raw_plate)
    if not plate:
        errors.append("Registration plate is required.")
    elif not PLATE_RE.match(plate):
        errors.append(
            f"'{raw_plate}' doesn't look like a valid plate "
            "(expected pattern like DL01AB1234)."
        )
    cleaned["reg_plate"] = plate

    make = form.get("make", "").strip()
    if not make:
        errors.append("Make is required.")
    elif not NAME_RE.match(make):
        errors.append("Make should be letters only (e.g. 'Maruti').")
    cleaned["make"] = make

    model = form.get("model", "").strip()
    if not model:
        errors.append("Model is required.")
    elif len(model) < 1 or len(model) > 50:
        errors.append("Model must be under 50 characters.")
    cleaned["model"] = model

    color = form.get("color", "").strip()
    if color and not NAME_RE.match(color):
        errors.append("Color should be letters only if provided.")
    cleaned["color"] = color or None

    owner_name = form.get("owner_name", "").strip()
    if not owner_name:
        errors.append("Owner name is required.")
    elif not NAME_RE.match(owner_name):
        errors.append("Owner name should contain letters only (no digits/symbols).")
    cleaned["owner_name"] = owner_name

    engine_no = form.get("engine_no", "").strip().upper()
    if engine_no and not ALNUM_ID_RE.match(engine_no):
        errors.append("Engine No. must be 5-30 alphanumeric characters if provided.")
    cleaned["engine_no"] = engine_no or None

    chassis_no = form.get("chassis_no", "").strip().upper()
    if chassis_no and not ALNUM_ID_RE.match(chassis_no):
        errors.append("Chassis No. must be 5-30 alphanumeric characters if provided.")
    cleaned["chassis_no"] = chassis_no or None

    # Duplicate check only matters if the plate itself is valid.
    if cleaned["reg_plate"] and not errors:
        existing = find_by_plate(cleaned["reg_plate"])
        if existing and editing_plate != cleaned["reg_plate"]:
            errors.append(
                f"Plate '{cleaned['reg_plate']}' already exists in this database. "
                "Use Edit instead of Add, or check for a typo."
            )

    return errors, cleaned


# ---------------------------------------------------------------------------
# Data access — this laptop only ever touches its own local table
# ---------------------------------------------------------------------------

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


# Rows loaded from the real 100k-row CSV were inserted as-is by
# import_real_data.py (no normalization applied at import time), so the
# DB can genuinely contain "DL 01 AB 1004" style values. Every lookup
# here therefore normalizes BOTH sides in SQL — strip spaces/dashes,
# uppercase — so a search or update never silently misses a row just
# because of its stored formatting.
NORMALIZED_MATCH_SQL = (
    "UPPER(REPLACE(REPLACE(reg_plate, ' ', ''), '-', '')) = %s"
)


def find_by_plate(plate):
    plate = normalize_plate(plate)
    if not plate:
        return None
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT * FROM vehicles WHERE {NORMALIZED_MATCH_SQL} LIMIT 1",
            (plate,),
        )
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()


def search_vehicles(term):
    """Partial match on plate, make, model, or owner — for the Find tab."""
    term = (term or "").strip()
    if not term:
        return []
    like = f"%{term}%"
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT * FROM vehicles
            WHERE reg_plate LIKE %s OR make LIKE %s
               OR model LIKE %s OR owner_name LIKE %s
            ORDER BY id DESC
            LIMIT 50
            """,
            (like, like, like, like),
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def insert_vehicle(cleaned):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO vehicles
                (reg_plate, make, model, color, owner_name, engine_no, chassis_no)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cleaned["reg_plate"], cleaned["make"], cleaned["model"],
                cleaned["color"], cleaned["owner_name"],
                cleaned["engine_no"], cleaned["chassis_no"],
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def update_vehicle(original_plate, cleaned):
    """
    Returns the number of rows actually updated, so the caller can tell
    a genuine "0 rows matched" apart from a silent no-op.
    """
    original_plate = normalize_plate(original_plate)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE vehicles
            SET reg_plate = %s, make = %s, model = %s, color = %s,
                owner_name = %s, engine_no = %s, chassis_no = %s
            WHERE {NORMALIZED_MATCH_SQL}
            """,
            (
                cleaned["reg_plate"], cleaned["make"], cleaned["model"],
                cleaned["color"], cleaned["owner_name"],
                cleaned["engine_no"], cleaned["chassis_no"],
                original_plate,
            ),
        )
        conn.commit()
        affected = cur.rowcount
        cur.close()
        return affected
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Laptop 1 — Vehicle Registration DB</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #1e3a5f 0%, #4a6fa5 100%);
            min-height: 100vh;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
        }
        .card {
            background: #fff;
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            padding: 36px;
            max-width: 820px;
            width: 100%;
        }
        h2 { margin-top: 0; color: #1e3a5f; }
        .subtitle { color: #667085; font-size: 0.85rem; margin-top: -8px; margin-bottom: 24px; }
        .tabs { display: flex; border-bottom: 2px solid #eef1f4; margin-bottom: 22px; }
        .tab-link {
            padding: 10px 18px;
            text-decoration: none;
            color: #667085;
            font-weight: 600;
            font-size: 0.92rem;
            border-bottom: 3px solid transparent;
        }
        .tab-link.active { color: #1e3a5f; border-bottom: 3px solid #1e3a5f; }
        form.inline { display: flex; gap: 10px; margin-bottom: 20px; }
        input, select {
            padding: 11px 13px;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            font-size: 0.95rem;
            width: 100%;
        }
        button {
            padding: 11px 22px;
            background: #1e3a5f;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
        }
        button.secondary { background: #eef1f4; color: #1e3a5f; }
        .field-row { margin-bottom: 14px; }
        .field-row label { display: block; font-size: 0.8rem; color: #667085; margin-bottom: 4px; }
        .errors {
            background: #fdecea; border: 1px solid #f5c2c0; color: #a33;
            padding: 14px 18px; border-radius: 8px; margin-bottom: 18px;
        }
        .errors ul { margin: 4px 0 0 18px; padding: 0; }
        .success {
            background: #eafaf0; border: 1px solid #b7e4c7; color: #1e8449;
            padding: 12px 18px; border-radius: 8px; margin-bottom: 18px;
        }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.88rem; }
        th, td { text-align: left; padding: 9px 8px; border-bottom: 1px solid #eef1f4; }
        th { color: #667085; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.04em; }
        .edit-link { color: #1e3a5f; font-weight: 600; text-decoration: none; }
        .empty { color: #8a94a3; padding: 20px 0; text-align: center; }
    </style>
</head>
<body>
<div class="card">
    <h2>🚙 Laptop 1 — Vehicle Registration</h2>
    <div class="subtitle">Local database: {{ db_name }} — independent of the coordinator</div>

    <div class="tabs">
        <a class="tab-link {{ 'active' if mode=='find' else '' }}" href="{{ url_for('find') }}">Find</a>
        <a class="tab-link {{ 'active' if mode=='add' else '' }}" href="{{ url_for('add') }}">Append</a>
    </div>

    {% if success %}
        <div class="success">{{ success }}</div>
    {% endif %}
    {% if errors %}
        <div class="errors">
            <strong>Please fix the following:</strong>
            <ul>{% for e in errors %}<li>{{ e }}</li>{% endfor %}</ul>
        </div>
    {% endif %}

    {% if mode == 'find' %}
        <form class="inline" method="get" action="{{ url_for('find') }}">
            <input name="q" placeholder="Search plate, make, model or owner" value="{{ query or '' }}">
            <button type="submit">Search</button>
        </form>

        {% if query %}
            {% if rows %}
                <table>
                    <tr><th>Plate</th><th>Make</th><th>Model</th><th>Color</th><th>Owner</th><th></th></tr>
                    {% for r in rows %}
                        <tr>
                            <td>{{ r.reg_plate }}</td>
                            <td>{{ r.make }}</td>
                            <td>{{ r.model }}</td>
                            <td>{{ r.color or '—' }}</td>
                            <td>{{ r.owner_name }}</td>
                            <td><a class="edit-link" href="{{ url_for('edit', plate=r.reg_plate) }}">Edit</a></td>
                        </tr>
                    {% endfor %}
                </table>
            {% else %}
                <div class="empty">No matching vehicles found.</div>
            {% endif %}
        {% endif %}
    {% endif %}

    {% if mode in ('add', 'edit') %}
        <form method="post" action="{{ url_for('edit', plate=editing_plate) if mode == 'edit' else url_for('add') }}">
            <div class="field-row">
                <label>Reg. Plate *</label>
                <input name="reg_plate" value="{{ form_values.reg_plate if form_values else (editing_plate or '') }}" required>
            </div>
            <div class="field-row">
                <label>Make *</label>
                <input name="make" value="{{ form_values.make if form_values else '' }}" required>
            </div>
            <div class="field-row">
                <label>Model *</label>
                <input name="model" value="{{ form_values.model if form_values else '' }}" required>
            </div>
            <div class="field-row">
                <label>Color</label>
                <input name="color" value="{{ form_values.color if form_values else '' }}">
            </div>
            <div class="field-row">
                <label>Owner Name *</label>
                <input name="owner_name" value="{{ form_values.owner_name if form_values else '' }}" required>
            </div>
            <div class="field-row">
                <label>Engine No.</label>
                <input name="engine_no" value="{{ form_values.engine_no if form_values else '' }}">
            </div>
            <div class="field-row">
                <label>Chassis No.</label>
                <input name="chassis_no" value="{{ form_values.chassis_no if form_values else '' }}">
            </div>
            <button type="submit">{{ 'Save Changes' if mode == 'edit' else 'Add Vehicle' }}</button>
            {% if mode == 'edit' %}
                <a class="tab-link" style="margin-left:12px;" href="{{ url_for('find') }}">Cancel</a>
            {% endif %}
        </form>
    {% endif %}
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return redirect(url_for("find"))


@app.route("/find")
def find():
    query = request.args.get("q", "").strip()
    msg = request.args.get("msg")
    success = None
    if msg == "added":
        success = f"Vehicle '{query}' added successfully."
    elif msg == "saved":
        success = f"Changes to '{query}' saved successfully."

    rows = search_vehicles(query) if query else []
    return render_template_string(
        TEMPLATE, mode="find", db_name=DB_CONFIG["database"],
        query=query, rows=rows, errors=None, success=success,
        form_values=None, editing_plate=None,
    )


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return render_template_string(
            TEMPLATE, mode="add", db_name=DB_CONFIG["database"],
            query=None, rows=None, errors=None, success=None,
            form_values=None, editing_plate=None,
        )

    errors, cleaned = validate_vehicle(request.form)
    if errors:
        return render_template_string(
            TEMPLATE, mode="add", db_name=DB_CONFIG["database"],
            query=None, rows=None, errors=errors, success=None,
            form_values=request.form, editing_plate=None,
        )

    insert_vehicle(cleaned)
    # Redirect (not re-render) after a successful POST — this is the
    # standard Post/Redirect/Get pattern: it sends the browser back to
    # the Find/home page instead of leaving it sitting on the POST, and
    # a refresh on the results page can't accidentally resubmit the form.
    return redirect(url_for("find", q=cleaned["reg_plate"], msg="added"))


@app.route("/edit/<plate>", methods=["GET", "POST"])
def edit(plate):
    plate = normalize_plate(plate)

    if request.method == "GET":
        existing = find_by_plate(plate)
        if not existing:
            return render_template_string(
                TEMPLATE, mode="find", db_name=DB_CONFIG["database"],
                query=plate, rows=[], errors=[f"No vehicle found for plate '{plate}'."],
                success=None, form_values=None, editing_plate=None,
            )
        return render_template_string(
            TEMPLATE, mode="edit", db_name=DB_CONFIG["database"],
            query=None, rows=None, errors=None, success=None,
            form_values=existing, editing_plate=plate,
        )

    errors, cleaned = validate_vehicle(request.form, editing_plate=plate)
    if errors:
        return render_template_string(
            TEMPLATE, mode="edit", db_name=DB_CONFIG["database"],
            query=None, rows=None, errors=errors, success=None,
            form_values=request.form, editing_plate=plate,
        )

    affected = update_vehicle(plate, cleaned)
    if affected == 0:
        # The row existed when we loaded the edit form but the WHERE
        # matched nothing on save (e.g. someone deleted it in between,
        # or it moved out from under us) — tell the user plainly
        # instead of pretending it worked.
        return render_template_string(
            TEMPLATE, mode="edit", db_name=DB_CONFIG["database"],
            query=None, rows=None,
            errors=[f"No matching row for plate '{plate}' — it may have been changed or removed by someone else. Please search again."],
            success=None, form_values=request.form, editing_plate=plate,
        )

    return redirect(url_for("find", q=cleaned["reg_plate"], msg="saved"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=False)