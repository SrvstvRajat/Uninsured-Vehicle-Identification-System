import os
import mysql.connector
from flask import Flask, request, render_template_string, redirect, url_for, flash, jsonify
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

RECENT_LIMIT = 50


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def normalize_plate(value):
    return value.strip().replace(" ", "").replace("-", "").upper()


def fetch_recent(limit=RECENT_LIMIT):
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, plate_no, theft_date, status, shredded_date
        FROM theft_records
        ORDER BY id DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_by_plate(plate):
    conn = connect_db()
    cur = conn.cursor(dictionary=True)
    key = normalize_plate(plate)
    cur.execute("""
        SELECT id, plate_no, theft_date, status, shredded_date
        FROM theft_records
        WHERE REPLACE(REPLACE(UPPER(plate_no), ' ', ''), '-', '') = %s
        ORDER BY theft_date DESC, id DESC
    """, (key,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def serialize_records(rows):
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "plate_no": r["plate_no"],
            "theft_date": r["theft_date"].isoformat() if r["theft_date"] else None,
            "status": r["status"],
            "shredded_date": r["shredded_date"].isoformat() if r["shredded_date"] else None,
        })
    return out


@app.route("/", methods=["GET"])
def index():
    error = None
    try:
        records = fetch_recent()
    except Exception as exc:
        records = []
        error = str(exc)

    return render_template_string(
        TEMPLATE,
        records=records,
        error=error,
        recent_limit=RECENT_LIMIT,
    )


@app.route("/api/search", methods=["GET"])
def api_search():
    plate = request.args.get("plate", "").strip()
    if not plate:
        return jsonify({"error": "Please enter a plate number."}), 400

    try:
        rows = fetch_by_plate(plate)
        return jsonify({"plate": plate, "records": serialize_records(rows)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


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
        return redirect(url_for("index"))

    except Exception as exc:
        flash(f"Could not add record: {exc}", "error")
        return redirect(url_for("index"))


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
        .card-header {
            display: flex; align-items: baseline; justify-content: space-between;
            flex-wrap: wrap; gap: 8px;
        }
        .card-header .hint { color: #667085; font-size: 13px; }
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
        button:hover { background:#0f2745; }
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
        .status-stolen { color:#a32d2d; }
        .status-recovered { color:#176b3a; }
        .status-shredded { color:#5b5f6e; }
        .empty-row td { text-align:center; color:#8a93a6; padding:24px; }

        /* Modal */
        .modal-overlay {
            display:none; position:fixed; inset:0; background:rgba(15,23,42,.5);
            align-items:flex-start; justify-content:center; padding:60px 20px;
            z-index: 1000;
        }
        .modal-overlay.open { display:flex; }
        .modal-box {
            background:white; border-radius:14px; max-width:720px; width:100%;
            box-shadow: 0 20px 60px rgba(0,0,0,.25); max-height: 80vh;
            display:flex; flex-direction:column; overflow:hidden;
        }
        .modal-head {
            display:flex; justify-content:space-between; align-items:center;
            padding:18px 22px; border-bottom:1px solid #e8edf3;
        }
        .modal-head h3 { margin:0; }
        .modal-close {
            background:none; border:none; color:#667085; font-size:22px;
            cursor:pointer; padding:0 4px; line-height:1;
        }
        .modal-close:hover { color:#172033; background:none; }
        .modal-body { padding: 10px 22px 22px; overflow-y:auto; }
        .modal-loading { color:#667085; padding: 20px 0; }
        .modal-error { background:#fdecec; color:#a32d2d; padding:12px; border-radius:8px; }

        @media(max-width:700px) {
            .grid { grid-template-columns:1fr; }
            .full { grid-column:auto; }
            .search { flex-direction:column; }
            .modal-overlay { padding: 20px 12px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>🚨 Theft &amp; Shredding Database</h1>
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
        <form class="search" id="searchForm">
            <input name="plate" id="plateInput" placeholder="Enter vehicle plate" autocomplete="off">
            <button type="submit">Search</button>
        </form>
    </div>

    <div class="card">
        <div class="card-header">
            <h2>Recent Theft Records</h2>
            <span class="hint">Showing latest {{ recent_limit }} records</span>
        </div>

        {% if error %}
            <div class="error">{{ error }}</div>
        {% endif %}

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
                    <td class="status status-{{ r.status }}">{{ r.status }}</td>
                    <td>{{ r.shredded_date or "—" }}</td>
                </tr>
            {% else %}
                <tr class="empty-row"><td colspan="5">No records yet.</td></tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
</div>

<div class="modal-overlay" id="modalOverlay">
    <div class="modal-box">
        <div class="modal-head">
            <h3 id="modalTitle">Search Results</h3>
            <button class="modal-close" id="modalClose" aria-label="Close">&times;</button>
        </div>
        <div class="modal-body" id="modalBody">
            <div class="modal-loading">Searching…</div>
        </div>
    </div>
</div>

<script>
const overlay = document.getElementById('modalOverlay');
const modalBody = document.getElementById('modalBody');
const modalTitle = document.getElementById('modalTitle');
const searchForm = document.getElementById('searchForm');
const plateInput = document.getElementById('plateInput');

function openModal() {
    overlay.classList.add('open');
}
function closeModal() {
    overlay.classList.remove('open');
}

document.getElementById('modalClose').addEventListener('click', closeModal);
overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function renderResults(data) {
    modalTitle.textContent = 'Results for "' + data.plate + '"';
    if (!data.records || data.records.length === 0) {
        modalBody.innerHTML = '<p style="color:#667085;">No record found for this plate.</p>';
        return;
    }
    let rows = data.records.map(r => `
        <tr>
            <td>${escapeHtml(r.id)}</td>
            <td>${escapeHtml(r.plate_no)}</td>
            <td>${escapeHtml(r.theft_date || "—")}</td>
            <td class="status status-${escapeHtml(r.status)}">${escapeHtml(r.status)}</td>
            <td>${escapeHtml(r.shredded_date || "—")}</td>
        </tr>
    `).join('');
    modalBody.innerHTML = `
        <table>
            <thead>
                <tr><th>ID</th><th>Plate</th><th>Theft Date</th><th>Status</th><th>Shredded Date</th></tr>
            </thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const plate = plateInput.value.trim();
    if (!plate) return;

    modalTitle.textContent = 'Search Results';
    modalBody.innerHTML = '<div class="modal-loading">Searching…</div>';
    openModal();

    try {
        const res = await fetch('/api/search?plate=' + encodeURIComponent(plate));
        const data = await res.json();
        if (!res.ok) {
            modalBody.innerHTML = '<div class="modal-error">' + escapeHtml(data.error || 'Search failed.') + '</div>';
            return;
        }
        renderResults(data);
    } catch (err) {
        modalBody.innerHTML = '<div class="modal-error">Could not reach the server. Please try again.</div>';
    }
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("THEFT_UI_PORT", "5002")), debug=False)