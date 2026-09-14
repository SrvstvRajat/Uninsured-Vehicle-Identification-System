# import os
# import mysql.connector
# from flask import Flask, request, render_template_string, redirect, url_for, flash
# from dotenv import load_dotenv

# load_dotenv()

# app = Flask(__name__)
# app.secret_key = os.getenv("FLASK_SECRET_KEY", "mot-db-ui")

# DB_CONFIG = {
#     "host": os.getenv("MOT_HOST", "localhost"),
#     "port": int(os.getenv("DB_PORT", "3306")),
#     "user": os.getenv("COORDINATOR_USER", "coordinator"),
#     "password": os.getenv("COORDINATOR_PASSWORD", "ChooseAStrongPassword123!"),
#     "database": "mot_db",
# }


# def connect_db():
#     return mysql.connector.connect(**DB_CONFIG)


# def normalize_plate(value):
#     return value.strip().replace(" ", "").replace("-", "").upper()


# @app.route("/", methods=["GET"])
# def index():
#     plate = request.args.get("plate", "").strip()
#     records = []
#     error = None

#     if plate:
#         try:
#             conn = connect_db()
#             cur = conn.cursor(dictionary=True)
#             key = normalize_plate(plate)

#             cur.execute("""
#                 SELECT id, vehicle_plate, report_date, flag_reason, reported_by
#                 FROM mot_reports
#                 WHERE REPLACE(REPLACE(UPPER(vehicle_plate), ' ', ''), '-', '') = %s
#                 ORDER BY report_date DESC, id DESC
#             """, (key,))

#             records = cur.fetchall()
#             cur.close()
#             conn.close()
#         except Exception as exc:
#             error = str(exc)

#     return render_template_string(
#         TEMPLATE,
#         plate=plate,
#         records=records,
#         error=error,
#     )


# @app.route("/add", methods=["POST"])
# def add_report():
#     vehicle_plate = request.form.get("vehicle_plate", "").strip()
#     report_date = request.form.get("report_date") or None
#     flag_reason = request.form.get("flag_reason", "").strip()
#     reported_by = request.form.get("reported_by", "").strip()

#     if not vehicle_plate or not flag_reason:
#         flash("Vehicle plate and flag reason are required.", "error")
#         return redirect(url_for("index"))

#     try:
#         conn = connect_db()
#         cur = conn.cursor()

#         cur.execute("""
#             INSERT INTO mot_reports
#             (vehicle_plate, report_date, flag_reason, reported_by)
#             VALUES (%s, %s, %s, %s)
#         """, (
#             vehicle_plate,
#             report_date,
#             flag_reason,
#             reported_by or "coordinator"
#         ))

#         conn.commit()
#         cur.close()
#         conn.close()

#         flash("Ministry report added successfully.", "success")
#         return redirect(url_for("index", plate=vehicle_plate))

#     except Exception as exc:
#         flash(f"Could not add report: {exc}", "error")
#         return redirect(url_for("index", plate=vehicle_plate))


# TEMPLATE = r"""
# <!DOCTYPE html>
# <html>
# <head>
#     <title>Ministry of Transportation</title>
#     <meta name="viewport" content="width=device-width, initial-scale=1">
#     <style>
#         * { box-sizing: border-box; }
#         body {
#             margin:0; font-family:Segoe UI,Arial,sans-serif;
#             background:#f4f7fb; color:#172033;
#         }
#         .container { max-width:1100px; margin:35px auto; padding:20px; }
#         h1 { margin-bottom:5px; }
#         .subtitle { color:#667085; margin-bottom:25px; }
#         .card {
#             background:white; padding:25px; margin-bottom:20px;
#             border-radius:14px; box-shadow:0 5px 20px rgba(0,0,0,.08);
#         }
#         .grid {
#             display:grid; grid-template-columns:1fr 1fr; gap:15px;
#         }
#         label { display:block; font-weight:600; margin-bottom:6px; }
#         input, textarea {
#             width:100%; padding:11px; border:1px solid #d5dce6;
#             border-radius:8px; font-size:15px;
#         }
#         textarea { min-height:90px; resize:vertical; }
#         button {
#             padding:11px 18px; border:0; border-radius:8px;
#             background:#17365d; color:white; font-weight:600; cursor:pointer;
#         }
#         .full { grid-column:1 / -1; }
#         .search { display:flex; gap:10px; }
#         .search input { flex:1; }
#         table { width:100%; border-collapse:collapse; margin-top:18px; }
#         th, td { padding:12px; border-bottom:1px solid #e8edf3; text-align:left; }
#         th { background:#f6f8fb; }
#         .success, .error { padding:12px; border-radius:8px; margin-bottom:15px; }
#         .success { background:#e8f7ee; color:#176b3a; }
#         .error { background:#fdecec; color:#a32d2d; }
#         @media(max-width:700px) {
#             .grid { grid-template-columns:1fr; }
#             .full { grid-column:auto; }
#             .search { flex-direction:column; }
#         }
#     </style>
# </head>
# <body>
# <div class="container">
#     <h1>🏛️ Ministry of Transportation</h1>
#     <div class="subtitle">
#         Independent MOT DB — Add and search ministry reports.
#     </div>

#     {% with messages = get_flashed_messages(with_categories=true) %}
#         {% for category, message in messages %}
#             <div class="{{ category }}">{{ message }}</div>
#         {% endfor %}
#     {% endwith %}

#     <div class="card">
#         <h2>Add Ministry Report</h2>
#         <form method="post" action="/add">
#             <div class="grid">
#                 <div>
#                     <label>Vehicle Plate *</label>
#                     <input name="vehicle_plate" placeholder="DL01AB1002" required>
#                 </div>
#                 <div>
#                     <label>Report Date</label>
#                     <input type="date" name="report_date">
#                 </div>
#                 <div class="full">
#                     <label>Flag Reason *</label>
#                     <textarea name="flag_reason"
#                         placeholder="UNINSURED — no policy on record"
#                         required></textarea>
#                 </div>
#                 <div class="full">
#                     <label>Reported By</label>
#                     <input name="reported_by"
#                         placeholder="federated-integration-engine">
#                 </div>
#                 <div class="full">
#                     <button type="submit">Submit Ministry Report</button>
#                 </div>
#             </div>
#         </form>
#     </div>

#     <div class="card">
#         <h2>Search Ministry Reports</h2>
#         <form class="search" method="get">
#             <input name="plate" value="{{ plate }}"
#                    placeholder="Enter vehicle plate">
#             <button type="submit">Search</button>
#         </form>

#         {% if plate %}
#             <table>
#                 <thead>
#                     <tr>
#                         <th>ID</th><th>Vehicle Plate</th><th>Report Date</th>
#                         <th>Flag Reason</th><th>Reported By</th>
#                     </tr>
#                 </thead>
#                 <tbody>
#                 {% for r in records %}
#                     <tr>
#                         <td>{{ r.id }}</td>
#                         <td>{{ r.vehicle_plate }}</td>
#                         <td>{{ r.report_date or "—" }}</td>
#                         <td>{{ r.flag_reason or "—" }}</td>
#                         <td>{{ r.reported_by or "—" }}</td>
#                     </tr>
#                 {% else %}
#                     <tr><td colspan="5">No report found.</td></tr>
#                 {% endfor %}
#                 </tbody>
#             </table>
#         {% endif %}
#     </div>
# </div>
# </body>
# </html>
# """


# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.getenv("MOT_UI_PORT", "5003")), debug=False)



import os
import mysql.connector
from flask import Flask, request, render_template_string, redirect, url_for, flash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "mot-db-ui")

DB_CONFIG = {
    "host": os.getenv("MOT_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("COORDINATOR_USER", "coordinator"),
    "password": os.getenv(
        "COORDINATOR_PASSWORD",
        "ChooseAStrongPassword123!"
    ),
    "database": "mot_db",
}


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def normalize_plate(value):
    return value.strip().replace(" ", "").replace("-", "").upper()


@app.route("/", methods=["GET"])
def index():

    plate = request.args.get("plate", "").strip()

    records = []
    total_records = 0
    error = None

    try:
        conn = connect_db()
        cur = conn.cursor(dictionary=True)

        # Total number of records
        cur.execute("SELECT COUNT(*) AS total FROM mot_reports")
        total_records = cur.fetchone()["total"]

        if plate:
            # Search specific vehicle
            key = normalize_plate(plate)

            cur.execute("""
                SELECT
                    id,
                    vehicle_plate,
                    report_date,
                    flag_reason,
                    reported_by
                FROM mot_reports
                WHERE REPLACE(
                    REPLACE(UPPER(vehicle_plate), ' ', ''),
                    '-',
                    ''
                ) = %s
                ORDER BY report_date DESC, id DESC
            """, (key,))

        else:
            # Show latest 100 records
            cur.execute("""
                SELECT
                    id,
                    vehicle_plate,
                    report_date,
                    flag_reason,
                    reported_by
                FROM mot_reports
                ORDER BY report_date DESC, id DESC
                LIMIT 100
            """)

        records = cur.fetchall()

        cur.close()
        conn.close()

    except Exception as exc:
        error = str(exc)

    return render_template_string(
        TEMPLATE,
        plate=plate,
        records=records,
        total_records=total_records,
        error=error,
    )


@app.route("/add", methods=["POST"])
def add_report():

    vehicle_plate = request.form.get("vehicle_plate", "").strip()
    report_date = request.form.get("report_date") or None
    flag_reason = request.form.get("flag_reason", "").strip()
    reported_by = request.form.get("reported_by", "").strip()

    if not vehicle_plate or not flag_reason:
        flash(
            "Vehicle plate and flag reason are required.",
            "error"
        )
        return redirect(url_for("index"))

    try:

        conn = connect_db()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO mot_reports
            (
                vehicle_plate,
                report_date,
                flag_reason,
                reported_by
            )
            VALUES (%s, %s, %s, %s)
        """, (
            vehicle_plate,
            report_date,
            flag_reason,
            reported_by or "coordinator"
        ))

        conn.commit()

        cur.close()
        conn.close()

        flash(
            "Ministry report added successfully.",
            "success"
        )

        return redirect(
            url_for("index", plate=vehicle_plate)
        )

    except Exception as exc:

        flash(
            f"Could not add report: {exc}",
            "error"
        )

        return redirect(
            url_for("index", plate=vehicle_plate)
        )


TEMPLATE = r"""
<!DOCTYPE html>

<html>

<head>

    <title>Ministry of Transportation</title>

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <style>

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Segoe UI, Arial, sans-serif;
            background: #f4f7fb;
            color: #172033;
        }

        .container {
            max-width: 1200px;
            margin: 35px auto;
            padding: 20px;
        }

        h1 {
            margin-bottom: 5px;
        }

        .subtitle {
            color: #667085;
            margin-bottom: 25px;
        }

        .card {
            background: white;
            padding: 25px;
            margin-bottom: 20px;
            border-radius: 14px;
            box-shadow: 0 5px 20px rgba(0,0,0,.08);
        }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        label {
            display: block;
            font-weight: 600;
            margin-bottom: 6px;
        }

        input,
        textarea {
            width: 100%;
            padding: 11px;
            border: 1px solid #d5dce6;
            border-radius: 8px;
            font-size: 15px;
        }

        textarea {
            min-height: 90px;
            resize: vertical;
        }

        button {
            padding: 11px 18px;
            border: 0;
            border-radius: 8px;
            background: #17365d;
            color: white;
            font-weight: 600;
            cursor: pointer;
        }

        button:hover {
            opacity: .9;
        }

        .clear-button {
            background: #667085;
            text-decoration: none;
            padding: 11px 18px;
            border-radius: 8px;
            color: white;
            font-weight: 600;
        }

        .full {
            grid-column: 1 / -1;
        }

        .search {
            display: flex;
            gap: 10px;
        }

        .search input {
            flex: 1;
        }

        .stats {
            display: flex;
            gap: 15px;
            margin-top: 20px;
        }

        .stat {
            background: #f6f8fb;
            padding: 15px 20px;
            border-radius: 10px;
        }

        .stat-number {
            font-size: 24px;
            font-weight: 700;
        }

        .stat-label {
            color: #667085;
            font-size: 13px;
        }

        .table-container {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 18px;
        }

        th,
        td {
            padding: 12px;
            border-bottom: 1px solid #e8edf3;
            text-align: left;
        }

        th {
            background: #f6f8fb;
            position: sticky;
            top: 0;
        }

        .success,
        .error {
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 15px;
        }

        .success {
            background: #e8f7ee;
            color: #176b3a;
        }

        .error {
            background: #fdecec;
            color: #a32d2d;
        }

        .showing {
            margin-top: 15px;
            color: #667085;
            font-size: 14px;
        }

        @media(max-width:700px) {

            .grid {
                grid-template-columns: 1fr;
            }

            .full {
                grid-column: auto;
            }

            .search {
                flex-direction: column;
            }

            .stats {
                flex-direction: column;
            }
        }

    </style>

</head>


<body>

<div class="container">

    <h1>🏛️ Ministry of Transportation</h1>

    <div class="subtitle">
        Independent MOT DB — Add, view and search ministry reports.
    </div>


    {% with messages = get_flashed_messages(with_categories=true) %}

        {% for category, message in messages %}

            <div class="{{ category }}">
                {{ message }}
            </div>

        {% endfor %}

    {% endwith %}


    <!-- ADD REPORT -->

    <div class="card">

        <h2>Add Ministry Report</h2>

        <form method="post" action="/add">

            <div class="grid">

                <div>

                    <label>
                        Vehicle Plate *
                    </label>

                    <input
                        name="vehicle_plate"
                        placeholder="DL01AB1002"
                        required
                    >

                </div>


                <div>

                    <label>
                        Report Date
                    </label>

                    <input
                        type="date"
                        name="report_date"
                    >

                </div>


                <div class="full">

                    <label>
                        Flag Reason *
                    </label>

                    <textarea
                        name="flag_reason"
                        placeholder="UNINSURED — no policy on record"
                        required
                    ></textarea>

                </div>


                <div class="full">

                    <label>
                        Reported By
                    </label>

                    <input
                        name="reported_by"
                        placeholder="federated-integration-engine"
                    >

                </div>


                <div class="full">

                    <button type="submit">
                        Submit Ministry Report
                    </button>

                </div>

            </div>

        </form>

    </div>


    <!-- SEARCH -->

    <div class="card">

        <h2>Search Ministry Reports</h2>

        <form class="search" method="get">

            <input
                name="plate"
                value="{{ plate }}"
                placeholder="Enter vehicle plate, e.g. DL01AB1002"
            >

            <button type="submit">
                Search
            </button>

            {% if plate %}

                <a
                    href="/"
                    class="clear-button"
                >
                    Show All
                </a>

            {% endif %}

        </form>


        <!-- STATISTICS -->

        <div class="stats">

            <div class="stat">

                <div class="stat-number">
                    {{ total_records }}
                </div>

                <div class="stat-label">
                    Total Reports in Database
                </div>

            </div>


            <div class="stat">

                <div class="stat-number">
                    {{ records|length }}
                </div>

                <div class="stat-label">

                    {% if plate %}
                        Reports for {{ plate }}
                    {% else %}
                        Latest Reports Shown
                    {% endif %}

                </div>

            </div>

        </div>


        <!-- DATA TABLE -->

        <div class="table-container">

            <table>

                <thead>

                    <tr>

                        <th>ID</th>

                        <th>Vehicle Plate</th>

                        <th>Report Date</th>

                        <th>Flag Reason</th>

                        <th>Reported By</th>

                    </tr>

                </thead>


                <tbody>

                {% for r in records %}

                    <tr>

                        <td>
                            {{ r.id }}
                        </td>

                        <td>
                            <strong>
                                {{ r.vehicle_plate }}
                            </strong>
                        </td>

                        <td>
                            {{ r.report_date or "—" }}
                        </td>

                        <td>
                            {{ r.flag_reason or "—" }}
                        </td>

                        <td>
                            {{ r.reported_by or "—" }}
                        </td>

                    </tr>

                {% else %}

                    <tr>

                        <td colspan="5">
                            No ministry reports found.
                        </td>

                    </tr>

                {% endfor %}

                </tbody>

            </table>

        </div>


        {% if not plate and total_records > 100 %}

            <div class="showing">

                Showing the latest 100 reports out of
                {{ total_records }} total reports.

                Use the search box above to find a
                specific vehicle.

            </div>

        {% endif %}

    </div>

</div>

</body>

</html>
"""


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("MOT_UI_PORT", "5003")),
        debug=False
    )