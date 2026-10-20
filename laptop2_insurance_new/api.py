"""
api.py - REST API for the insurance node (Laptop 2).

Run on the insurance laptop:
    pip install flask mysql-connector-python python-dotenv
    python3 api.py

.env needs:
    MYSQL_HOST=localhost
    MYSQL_USER=api_user            # a limited MySQL user, NOT root
    MYSQL_PASSWORD=...
    MYSQL_DATABASE=insurance_db
    API_KEY=some-long-random-string

Endpoints (all need header  X-API-Key: <API_KEY>):
    GET    /policies?vehicle_number=DL01AB1004   search (also q=, active_only=1)
    GET    /policies/<id>                        one policy
    POST   /policies                             create (JSON body)
    PUT    /policies/<id>                        update (JSON, partial allowed)
    DELETE /policies/<id>                        delete
"""
import hmac
import os
from datetime import date
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

app = Flask(__name__)
API_KEY = os.getenv("API_KEY", "")

FIELDS = ["vehicle_number", "insurer_name", "policy_no",
          "policy_start_date", "policy_end_date", "premium_amount"]


def get_conn():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE", "insurance_db"),
    )


def require_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        sent = request.headers.get("X-API-Key", "")
        if not API_KEY or not hmac.compare_digest(sent, API_KEY):
            return jsonify(error="unauthorized"), 401
        return fn(*args, **kwargs)
    return wrapper


def normalize_plate(p):
    return p.replace(" ", "").replace("-", "").upper()


def serialize(row):
    out = dict(row)
    for k in ("policy_start_date", "policy_end_date"):
        if out.get(k):
            out[k] = out[k].isoformat()
    if out.get("premium_amount") is not None:
        out["premium_amount"] = float(out["premium_amount"])
    out["status"] = ("Expired" if row["policy_end_date"] < date.today()
                     else "Active")
    return out


def run(sql, params=(), fetch=None, commit=False):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        data = None
        if fetch == "all":
            data = cur.fetchall()
        elif fetch == "one":
            data = cur.fetchone()
        if commit:
            conn.commit()
        return data, cur.lastrowid, cur.rowcount
    finally:
        conn.close()


@app.get("/policies")
@require_key
def search():
    where, params = [], []
    plate = request.args.get("vehicle_number")
    q = request.args.get("q")
    if plate:
        where.append("REPLACE(REPLACE(UPPER(vehicle_number),' ',''),'-','') = %s")
        params.append(normalize_plate(plate))
    if q:
        like = f"%{q}%"
        where.append("(vehicle_number LIKE %s OR insurer_name LIKE %s OR policy_no LIKE %s)")
        params += [like, like, like]
    if request.args.get("active_only") == "1":
        where.append("policy_end_date >= %s")
        params.append(date.today())

    sql = "SELECT * FROM insurance_policies"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY policy_end_date DESC LIMIT 100"
    rows, _, _ = run(sql, params, fetch="all")
    return jsonify([serialize(r) for r in rows])


@app.get("/policies/<int:pid>")
@require_key
def get_one(pid):
    row, _, _ = run("SELECT * FROM insurance_policies WHERE id=%s", (pid,), fetch="one")
    if not row:
        return jsonify(error="not found"), 404
    return jsonify(serialize(row))


@app.post("/policies")
@require_key
def create():
    body = request.get_json(silent=True) or {}
    missing = [f for f in FIELDS if f not in body]
    if missing:
        return jsonify(error="missing fields", fields=missing), 400
    vals = [body[f] for f in FIELDS]
    try:
        _, new_id, _ = run(
            f"INSERT INTO insurance_policies ({', '.join(FIELDS)}) "
            f"VALUES ({', '.join(['%s'] * len(FIELDS))})",
            vals, commit=True)
    except mysql.connector.Error as e:
        return jsonify(error=str(e)), 400
    return jsonify(id=new_id), 201


@app.put("/policies/<int:pid>")
@require_key
def update(pid):
    body = request.get_json(silent=True) or {}
    changes = {k: v for k, v in body.items() if k in FIELDS}   # whitelist
    if not changes:
        return jsonify(error="no valid fields to update"), 400
    sets = ", ".join(f"{k}=%s" for k in changes)
    try:
        _, _, n = run(f"UPDATE insurance_policies SET {sets} WHERE id=%s",
                      list(changes.values()) + [pid], commit=True)
    except mysql.connector.Error as e:
        return jsonify(error=str(e)), 400
    # note: MySQL reports 0 rows if values were unchanged, so check existence
    row, _, _ = run("SELECT * FROM insurance_policies WHERE id=%s", (pid,), fetch="one")
    if not row:
        return jsonify(error="not found"), 404
    return jsonify(serialize(row))


@app.delete("/policies/<int:pid>")
@require_key
def delete(pid):
    _, _, n = run("DELETE FROM insurance_policies WHERE id=%s", (pid,), commit=True)
    if n == 0:
        return jsonify(error="not found"), 404
    return "", 204


if __name__ == "__main__":
    # host 0.0.0.0 so the Coordinator laptop can reach it over the network
    app.run(host="0.0.0.0", port=5001)
