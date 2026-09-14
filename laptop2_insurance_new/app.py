"""
app.py — tiny demo web app for insurance_db

Lets you:
  - ADD a new insurance policy row (inserts into insurance_policies)
  - SEARCH existing policies (by vehicle number / insurer / policy no,
    with optional "active only" filter)

Uses the same connection pattern as generate_data.py / import_real_data.py:
reads MYSQL_ROOT_PASSWORD from a .env file and connects to localhost.

Run:
    pip install flask mysql-connector-python python-dotenv
    python3 app.py

Then open http://localhost:5000
"""

import os
from datetime import date

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, redirect, render_template_string, request

load_dotenv()

HOST = os.getenv("MYSQL_HOST", "localhost")
USER = os.getenv("MYSQL_USER", "root")
PASSWORD = os.getenv("MYSQL_PASSWORD") or os.getenv("MYSQL_ROOT_PASSWORD")
DATABASE = os.getenv("MYSQL_DATABASE", "insurance_db")

app = Flask(__name__)


def get_conn():
    if not PASSWORD:
        raise RuntimeError(
            "Missing MySQL password. Create a .env file with MYSQL_PASSWORD or "
            "MYSQL_ROOT_PASSWORD matching your local MySQL root account."
        )
    return mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
    )


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Insurance Policies — Demo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.3/css/bootstrap.min.css">
  <style>
    body { background:#f6f7f9; padding-bottom: 3rem; }
    .card { margin-top: 1.5rem; }
    .flash { margin-top: 1rem; }
    tr.expired td { color: #b02a37; }
    tr.no-policy td { color: #997404; }
  </style>
</head>
<body>
<div class="container">
  <h2 class="mt-4">Insurance Policies — Demo</h2>
  <p class="text-muted">insurance_db.insurance_policies</p>

  {% if message %}
    <div class="alert alert-{{ message_type }} flash">{{ message }}</div>
  {% endif %}

  <div class="row">
    <!-- ADD FORM -->
    <div class="col-lg-5">
      <div class="card">
        <div class="card-body">
          <h5 class="card-title">Add a policy</h5>
          <form method="post" action="/add">
            <div class="mb-2">
              <label class="form-label">Vehicle number</label>
              <input class="form-control" name="vehicle_number" required
                     placeholder="DL01AB1234">
            </div>
            <div class="mb-2">
              <label class="form-label">Insurer</label>
              <input class="form-control" name="insurer_name" required
                     placeholder="ICICI Lombard">
            </div>
            <div class="mb-2">
              <label class="form-label">Policy no.</label>
              <input class="form-control" name="policy_no" required
                     placeholder="POL-0099999">
            </div>
            <div class="row">
              <div class="col mb-2">
                <label class="form-label">Start date</label>
                <input class="form-control" type="date" name="policy_start_date" required>
              </div>
              <div class="col mb-2">
                <label class="form-label">End date</label>
                <input class="form-control" type="date" name="policy_end_date" required>
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">Premium amount</label>
              <input class="form-control" type="number" step="0.01" name="premium_amount"
                     placeholder="12500.00" required>
            </div>
            <button class="btn btn-primary w-100" type="submit">Add policy</button>
          </form>
        </div>
      </div>
    </div>

    <!-- SEARCH FORM + RESULTS -->
    <div class="col-lg-7">
      <div class="card">
        <div class="card-body">
          <h5 class="card-title">Search policies</h5>
          <form method="get" action="/">
            <div class="input-group mb-2">
              <input class="form-control" name="q" value="{{ q or '' }}"
                     placeholder="Vehicle number, insurer, or policy no.">
              <button class="btn btn-outline-secondary" type="submit">Search</button>
            </div>
            <div class="form-check">
              <input class="form-check-input" type="checkbox" name="active_only"
                     value="1" id="activeOnly" {{ 'checked' if active_only else '' }}
                     onchange="this.form.submit()">
              <label class="form-check-label" for="activeOnly">Active policies only</label>
            </div>
          </form>

          <table class="table table-sm table-hover mt-3">
            <thead>
              <tr>
                <th>Vehicle</th><th>Insurer</th><th>Policy No.</th>
                <th>Start</th><th>End</th><th>Premium</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {% for row in results %}
              <tr class="{{ 'expired' if row.status == 'Expired' else '' }}">
                <td>{{ row.vehicle_number }}</td>
                <td>{{ row.insurer_name }}</td>
                <td>{{ row.policy_no }}</td>
                <td>{{ row.policy_start_date }}</td>
                <td>{{ row.policy_end_date }}</td>
                <td>{{ "%.2f"|format(row.premium_amount) }}</td>
                <td>{{ row.status }}</td>
              </tr>
              {% else %}
              <tr><td colspan="7" class="text-muted text-center">No results</td></tr>
              {% endfor %}
            </tbody>
          </table>
          <p class="text-muted small">{{ results|length }} row(s) shown (max 100).</p>
        </div>
      </div>
    </div>
  </div>
</div>
</body>
</html>
"""


def run_search(q, active_only):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    where = []
    params = []
    if q:
        # normalize like a plate lookup: also try the value with spaces stripped
        like = f"%{q}%"
        where.append(
            "(vehicle_number LIKE %s OR insurer_name LIKE %s OR policy_no LIKE %s "
            "OR REPLACE(vehicle_number, ' ', '') LIKE %s)"
        )
        params.extend([like, like, like, f"%{q.replace(' ', '')}%"])
    if active_only:
        where.append("policy_end_date >= %s")
        params.append(date.today())

    sql = "SELECT * FROM insurance_policies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY policy_end_date DESC LIMIT 100"

    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    today = date.today()
    for r in rows:
        r["status"] = "Expired" if r["policy_end_date"] and r["policy_end_date"] < today else "Active"
    return rows


@app.route("/", methods=["GET"])
def index():
    q = request.args.get("q", "").strip()
    active_only = request.args.get("active_only") == "1"
    message = request.args.get("message")
    message_type = request.args.get("message_type", "success")

    try:
        results = run_search(q, active_only) if (q or active_only) else run_search("", False)
    except (mysql.connector.Error, RuntimeError) as e:
        results = []
        message, message_type = f"Database error: {e}", "danger"

    return render_template_string(
        PAGE, results=results, q=q, active_only=active_only,
        message=message, message_type=message_type,
    )


@app.route("/add", methods=["POST"])
def add():
    vehicle_number = request.form["vehicle_number"].strip()
    insurer_name = request.form["insurer_name"].strip()
    policy_no = request.form["policy_no"].strip()
    start = request.form["policy_start_date"]
    end = request.form["policy_end_date"]
    premium = request.form["premium_amount"]

    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO insurance_policies
            (vehicle_number, insurer_name, policy_no, policy_start_date,
             policy_end_date, premium_amount)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (vehicle_number, insurer_name, policy_no, start, end, premium),
        )
        conn.commit()
        cur.close()
        conn.close()
        msg, msg_type = f"Added policy {policy_no} for {vehicle_number}.", "success"
    except (mysql.connector.Error, RuntimeError) as e:
        msg, msg_type = f"Insert failed: {e}", "danger"

    from urllib.parse import urlencode
    return redirect("/?" + urlencode({"message": msg, "message_type": msg_type}))


if __name__ == "__main__":
    app.run(debug=True, port=5000)