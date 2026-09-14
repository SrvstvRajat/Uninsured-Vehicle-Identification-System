import os
import mysql.connector
from flask import Flask, request, render_template_string, redirect, url_for, flash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "theft-db-ui")

DB_CONFIG = {
    "host": os.getenv("THEFT_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("COORDINATOR_USER", "coordinator"),
    "password": os.getenv("COORDINATOR_PASSWORD", "ChooseAStrongPassword123!"),
    "database": "theft_db",
}


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def normalize_plate(value):
    return value.strip().replace(" ", "").replace("-", "").upper()


@app.route("/", methods=["GET"])
def index():
    plate = request.args.get("plate", "").strip()
    records = []
    error = None

    if plate:
        try:
            conn = connect_db()
            cur = conn.cursor(dictionary=True)
            key = normalize_plate(plate)

            cur.execute("""
                SELECT id, plate_no, theft_date, status, shredded_date
                FROM theft_records
                WHERE REPLACE(REPLACE(UPPER(plate_no), ' ', ''), '-', '') = %s
                ORDER BY theft_date DESC, id DESC
            """, (key,))

            records = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as exc:
            error = str(exc)

    return render_template_string(
        TEMPLATE,
        plate=plate,
        records=records,
        error=error,
    )


@app.route("/add", methods=["POST"])
def add_record():
    plate_no = request.form.get("plate_no", "").strip()
    theft_date = request.form.get("theft_date") or None
    status = request.form.get("status", "stolen")
    shredded_date = request.form.get("shredded_date") or None

    if not plate_no:
        flash("Plate number is required.", "error")
        return redirect(url_for("index"))

    try:
        conn = connect_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO theft_records
            (plate_no, theft_date, status, shredded_date)
            VALUES (%s, %s, %s, %s)
        """, (plate_no, theft_date, status, shredded_date))

        conn.commit()
        cur.close()
        conn.close()

        flash("Theft record added successfully.", "success")
        return redirect(url_for("index", plate=plate_no))

    except Exception as exc:
        flash(f"Could not add record: {exc}", "error")
        return redirect(url_for("index", plate=plate_no))


TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
    <title>Theft Database</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0; font-family: Segoe UI, Arial, sans-serif;
            background: #f4f7fb; color: #172033;
        }
        .container { max-width: 1100px; margin: 35px auto; padding: 20px; }
        h1 { margin-bottom: 5px; }
        .subtitle { color: #667085; margin-bottom: 25px; }
        .card {
            background: white; padding: 25px; margin-bottom: 20px;
            border-radius: 14px; box-shadow: 0 5px 20px rgba(0,0,0,.08);
        }
        .grid {
            display: grid; grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        label { display:block; font-weight:600; margin-bottom:6px; }
        input, select {
            width:100%; padding:11px; border:1px solid #d5dce6;
            border-radius:8px; font-size:15px;
        }
        button {
            padding:11px 18px; border:0; border-radius:8px;
            background:#17365d; color:white; font-weight:600; cursor:pointer;
        }
        .full { grid-column: 1 / -1; }
        .search { display:flex; gap:10px; }
        .search input { flex:1; }
        table { width:100%; border-collapse:collapse; margin-top:18px; }
        th, td { padding:12px; border-bottom:1px solid #e8edf3; text-align:left; }
        th { background:#f6f8fb; }
        .success, .error { padding:12px; border-radius:8px; margin-bottom:15px; }
        .success { background:#e8f7ee; color:#176b3a; }
        .error { background:#fdecec; color:#a32d2d; }
        .status { font-weight:700; text-transform:uppercase; }
        @media(max-width:700px) {
            .grid { grid-template-columns:1fr; }
            .full { grid-column:auto; }
            .search { flex-direction:column; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🚨 Theft & Shredding Database</h1>
    <div class="subtitle">
        Independent Theft DB — Add and search theft records.
    </div>

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
            <div class="{{ category }}">{{ message }}</div>
        {% endfor %}
    {% endwith %}

    <div class="card">
        <h2>Add Theft Record</h2>
        <form method="post" action="/add">
            <div class="grid">
                <div>
                    <label>Plate Number *</label>
                    <input name="plate_no" placeholder="DL01AB1003" required>
                </div>
                <div>
                    <label>Theft Date</label>
                    <input type="date" name="theft_date">
                </div>
                <div>
                    <label>Status *</label>
                    <select name="status">
                        <option value="stolen">Stolen</option>
                        <option value="recovered">Recovered</option>
                        <option value="shredded">Shredded</option>
                    </select>
                </div>
                <div>
                    <label>Shredded Date</label>
                    <input type="date" name="shredded_date">
                </div>
                <div class="full">
                    <button type="submit">Add Theft Record</button>
                </div>
            </div>
        </form>
    </div>

    <div class="card">
        <h2>Search Theft Record</h2>
        <form class="search" method="get">
            <input name="plate" value="{{ plate }}" placeholder="Enter vehicle plate">
            <button type="submit">Search</button>
        </form>

        {% if plate %}
            <table>
                <thead>
                    <tr>
                        <th>ID</th><th>Plate</th><th>Theft Date</th>
                        <th>Status</th><th>Shredded Date</th>
                    </tr>
                </thead>
                <tbody>
                {% for r in records %}
                    <tr>
                        <td>{{ r.id }}</td>
                        <td>{{ r.plate_no }}</td>
                        <td>{{ r.theft_date or "—" }}</td>
                        <td class="status">{{ r.status }}</td>
                        <td>{{ r.shredded_date or "—" }}</td>
                    </tr>
                {% else %}
                    <tr><td colspan="5">No record found.</td></tr>
                {% endfor %}
                </tbody>
            </table>
        {% endif %}
    </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("THEFT_UI_PORT", "5002")), debug=False)
