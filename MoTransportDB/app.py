# # import os
# # import mysql.connector
# # from flask import Flask, request, render_template_string, redirect, url_for, flash
# # from dotenv import load_dotenv

# # load_dotenv()

# # app = Flask(__name__)
# # app.secret_key = os.getenv("FLASK_SECRET_KEY", "mot-db-ui")

# # DB_CONFIG = {
# #     "host": os.getenv("MOT_HOST", "localhost"),
# #     "port": int(os.getenv("DB_PORT", "3306")),
# #     "user": os.getenv("COORDINATOR_USER", "coordinator"),
# #     "password": os.getenv(
# #         "COORDINATOR_PASSWORD",
# #         "ChooseAStrongPassword123!"
# #     ),
# #     "database": "mot_db",
# # }


# # def connect_db():
# #     return mysql.connector.connect(**DB_CONFIG)


# # def normalize_plate(value):
# #     return value.strip().replace(" ", "").replace("-", "").upper()


# # @app.route("/", methods=["GET"])
# # def index():

# #     plate = request.args.get("plate", "").strip()

# #     records = []
# #     total_records = 0
# #     error = None

# #     try:
# #         conn = connect_db()
# #         cur = conn.cursor(dictionary=True)

# #         # Total number of records
# #         cur.execute("SELECT COUNT(*) AS total FROM mot_reports")
# #         total_records = cur.fetchone()["total"]

# #         if plate:
# #             # Search specific vehicle
# #             key = normalize_plate(plate)

# #             cur.execute("""
# #                 SELECT
# #                     id,
# #                     vehicle_plate,
# #                     report_date,
# #                     flag_reason,
# #                     reported_by
# #                 FROM mot_reports
# #                 WHERE REPLACE(
# #                     REPLACE(UPPER(vehicle_plate), ' ', ''),
# #                     '-',
# #                     ''
# #                 ) = %s
# #                 ORDER BY report_date DESC, id DESC
# #             """, (key,))

# #         else:
# #             # Show latest 100 records
# #             cur.execute("""
# #                 SELECT
# #                     id,
# #                     vehicle_plate,
# #                     report_date,
# #                     flag_reason,
# #                     reported_by
# #                 FROM mot_reports
# #                 ORDER BY report_date DESC, id DESC
# #                 LIMIT 100
# #             """)

# #         records = cur.fetchall()

# #         cur.close()
# #         conn.close()

# #     except Exception as exc:
# #         error = str(exc)

# #     return render_template_string(
# #         TEMPLATE,
# #         plate=plate,
# #         records=records,
# #         total_records=total_records,
# #         error=error,
# #     )


# # @app.route("/add", methods=["POST"])
# # def add_report():

# #     vehicle_plate = request.form.get("vehicle_plate", "").strip()
# #     report_date = request.form.get("report_date") or None
# #     flag_reason = request.form.get("flag_reason", "").strip()
# #     reported_by = request.form.get("reported_by", "").strip()

# #     if not vehicle_plate or not flag_reason:
# #         flash(
# #             "Vehicle plate and flag reason are required.",
# #             "error"
# #         )
# #         return redirect(url_for("index"))

# #     try:

# #         conn = connect_db()
# #         cur = conn.cursor()

# #         cur.execute("""
# #             INSERT INTO mot_reports
# #             (
# #                 vehicle_plate,
# #                 report_date,
# #                 flag_reason,
# #                 reported_by
# #             )
# #             VALUES (%s, %s, %s, %s)
# #         """, (
# #             vehicle_plate,
# #             report_date,
# #             flag_reason,
# #             reported_by or "coordinator"
# #         ))

# #         conn.commit()

# #         cur.close()
# #         conn.close()

# #         flash(
# #             "Ministry report added successfully.",
# #             "success"
# #         )

# #         return redirect(
# #             url_for("index", plate=vehicle_plate)
# #         )

# #     except Exception as exc:

# #         flash(
# #             f"Could not add report: {exc}",
# #             "error"
# #         )

# #         return redirect(
# #             url_for("index", plate=vehicle_plate)
# #         )


# # TEMPLATE = r"""
# # <!DOCTYPE html>

# # <html>

# # <head>

# #     <title>Ministry of Transportation</title>

# #     <meta
# #         name="viewport"
# #         content="width=device-width, initial-scale=1"
# #     >

# #     <style>

# #         * {
# #             box-sizing: border-box;
# #         }

# #         body {
# #             margin: 0;
# #             font-family: Segoe UI, Arial, sans-serif;
# #             background: #f4f7fb;
# #             color: #172033;
# #         }

# #         .container {
# #             max-width: 1200px;
# #             margin: 35px auto;
# #             padding: 20px;
# #         }

# #         h1 {
# #             margin-bottom: 5px;
# #         }

# #         .subtitle {
# #             color: #667085;
# #             margin-bottom: 25px;
# #         }

# #         .card {
# #             background: white;
# #             padding: 25px;
# #             margin-bottom: 20px;
# #             border-radius: 14px;
# #             box-shadow: 0 5px 20px rgba(0,0,0,.08);
# #         }

# #         .grid {
# #             display: grid;
# #             grid-template-columns: 1fr 1fr;
# #             gap: 15px;
# #         }

# #         label {
# #             display: block;
# #             font-weight: 600;
# #             margin-bottom: 6px;
# #         }

# #         input,
# #         textarea {
# #             width: 100%;
# #             padding: 11px;
# #             border: 1px solid #d5dce6;
# #             border-radius: 8px;
# #             font-size: 15px;
# #         }

# #         textarea {
# #             min-height: 90px;
# #             resize: vertical;
# #         }

# #         button {
# #             padding: 11px 18px;
# #             border: 0;
# #             border-radius: 8px;
# #             background: #17365d;
# #             color: white;
# #             font-weight: 600;
# #             cursor: pointer;
# #         }

# #         button:hover {
# #             opacity: .9;
# #         }

# #         .clear-button {
# #             background: #667085;
# #             text-decoration: none;
# #             padding: 11px 18px;
# #             border-radius: 8px;
# #             color: white;
# #             font-weight: 600;
# #         }

# #         .full {
# #             grid-column: 1 / -1;
# #         }

# #         .search {
# #             display: flex;
# #             gap: 10px;
# #         }

# #         .search input {
# #             flex: 1;
# #         }

# #         .stats {
# #             display: flex;
# #             gap: 15px;
# #             margin-top: 20px;
# #         }

# #         .stat {
# #             background: #f6f8fb;
# #             padding: 15px 20px;
# #             border-radius: 10px;
# #         }

# #         .stat-number {
# #             font-size: 24px;
# #             font-weight: 700;
# #         }

# #         .stat-label {
# #             color: #667085;
# #             font-size: 13px;
# #         }

# #         .table-container {
# #             overflow-x: auto;
# #         }

# #         table {
# #             width: 100%;
# #             border-collapse: collapse;
# #             margin-top: 18px;
# #         }

# #         th,
# #         td {
# #             padding: 12px;
# #             border-bottom: 1px solid #e8edf3;
# #             text-align: left;
# #         }

# #         th {
# #             background: #f6f8fb;
# #             position: sticky;
# #             top: 0;
# #         }

# #         .success,
# #         .error {
# #             padding: 12px;
# #             border-radius: 8px;
# #             margin-bottom: 15px;
# #         }

# #         .success {
# #             background: #e8f7ee;
# #             color: #176b3a;
# #         }

# #         .error {
# #             background: #fdecec;
# #             color: #a32d2d;
# #         }

# #         .showing {
# #             margin-top: 15px;
# #             color: #667085;
# #             font-size: 14px;
# #         }

# #         @media(max-width:700px) {

# #             .grid {
# #                 grid-template-columns: 1fr;
# #             }

# #             .full {
# #                 grid-column: auto;
# #             }

# #             .search {
# #                 flex-direction: column;
# #             }

# #             .stats {
# #                 flex-direction: column;
# #             }
# #         }

# #     </style>

# # </head>


# # <body>

# # <div class="container">

# #     <h1>🏛️ Ministry of Transportation</h1>

# #     <div class="subtitle">
# #         Independent MOT DB — Add, view and search ministry reports.
# #     </div>


# #     {% with messages = get_flashed_messages(with_categories=true) %}

# #         {% for category, message in messages %}

# #             <div class="{{ category }}">
# #                 {{ message }}
# #             </div>

# #         {% endfor %}

# #     {% endwith %}


# #     <!-- ADD REPORT -->

# #     <div class="card">

# #         <h2>Add Ministry Report</h2>

# #         <form method="post" action="/add">

# #             <div class="grid">

# #                 <div>

# #                     <label>
# #                         Vehicle Plate *
# #                     </label>

# #                     <input
# #                         name="vehicle_plate"
# #                         placeholder="DL01AB1002"
# #                         required
# #                     >

# #                 </div>


# #                 <div>

# #                     <label>
# #                         Report Date
# #                     </label>

# #                     <input
# #                         type="date"
# #                         name="report_date"
# #                     >

# #                 </div>


# #                 <div class="full">

# #                     <label>
# #                         Flag Reason *
# #                     </label>

# #                     <textarea
# #                         name="flag_reason"
# #                         placeholder="UNINSURED — no policy on record"
# #                         required
# #                     ></textarea>

# #                 </div>


# #                 <div class="full">

# #                     <label>
# #                         Reported By
# #                     </label>

# #                     <input
# #                         name="reported_by"
# #                         placeholder="federated-integration-engine"
# #                     >

# #                 </div>


# #                 <div class="full">

# #                     <button type="submit">
# #                         Submit Ministry Report
# #                     </button>

# #                 </div>

# #             </div>

# #         </form>

# #     </div>


# #     <!-- SEARCH -->

# #     <div class="card">

# #         <h2>Search Ministry Reports</h2>

# #         <form class="search" method="get">

# #             <input
# #                 name="plate"
# #                 value="{{ plate }}"
# #                 placeholder="Enter vehicle plate, e.g. DL01AB1002"
# #             >

# #             <button type="submit">
# #                 Search
# #             </button>

# #             {% if plate %}

# #                 <a
# #                     href="/"
# #                     class="clear-button"
# #                 >
# #                     Show All
# #                 </a>

# #             {% endif %}

# #         </form>


# #         <!-- STATISTICS -->

# #         <div class="stats">

# #             <div class="stat">

# #                 <div class="stat-number">
# #                     {{ total_records }}
# #                 </div>

# #                 <div class="stat-label">
# #                     Total Reports in Database
# #                 </div>

# #             </div>


# #             <div class="stat">

# #                 <div class="stat-number">
# #                     {{ records|length }}
# #                 </div>

# #                 <div class="stat-label">

# #                     {% if plate %}
# #                         Reports for {{ plate }}
# #                     {% else %}
# #                         Latest Reports Shown
# #                     {% endif %}

# #                 </div>

# #             </div>

# #         </div>


# #         <!-- DATA TABLE -->

# #         <div class="table-container">

# #             <table>

# #                 <thead>

# #                     <tr>

# #                         <th>ID</th>

# #                         <th>Vehicle Plate</th>

# #                         <th>Report Date</th>

# #                         <th>Flag Reason</th>

# #                         <th>Reported By</th>

# #                     </tr>

# #                 </thead>


# #                 <tbody>

# #                 {% for r in records %}

# #                     <tr>

# #                         <td>
# #                             {{ r.id }}
# #                         </td>

# #                         <td>
# #                             <strong>
# #                                 {{ r.vehicle_plate }}
# #                             </strong>
# #                         </td>

# #                         <td>
# #                             {{ r.report_date or "—" }}
# #                         </td>

# #                         <td>
# #                             {{ r.flag_reason or "—" }}
# #                         </td>

# #                         <td>
# #                             {{ r.reported_by or "—" }}
# #                         </td>

# #                     </tr>

# #                 {% else %}

# #                     <tr>

# #                         <td colspan="5">
# #                             No ministry reports found.
# #                         </td>

# #                     </tr>

# #                 {% endfor %}

# #                 </tbody>

# #             </table>

# #         </div>


# #         {% if not plate and total_records > 100 %}

# #             <div class="showing">

# #                 Showing the latest 100 reports out of
# #                 {{ total_records }} total reports.

# #                 Use the search box above to find a
# #                 specific vehicle.

# #             </div>

# #         {% endif %}

# #     </div>

# # </div>

# # </body>

# # </html>
# # """


# # if __name__ == "__main__":

# #     app.run(
# #         host="0.0.0.0",
# #         port=int(os.getenv("MOT_UI_PORT", "5003")),
# #         debug=False
# #     )

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
#     "password": os.getenv(
#         "COORDINATOR_PASSWORD",
#         "ChooseAStrongPassword123!"
#     ),
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
#     total_records = 0
#     error = None

#     try:
#         conn = connect_db()
#         cur = conn.cursor(dictionary=True)

#         # Total number of records
#         cur.execute("SELECT COUNT(*) AS total FROM mot_reports")
#         total_records = cur.fetchone()["total"]

#         if plate:
#             # Search specific vehicle
#             key = normalize_plate(plate)

#             cur.execute("""
#                 SELECT
#                     id,
#                     vehicle_plate,
#                     report_date,
#                     flag_reason,
#                     reported_by
#                 FROM mot_reports
#                 WHERE REPLACE(
#                     REPLACE(UPPER(vehicle_plate), ' ', ''),
#                     '-',
#                     ''
#                 ) = %s
#                 ORDER BY report_date DESC, id DESC
#             """, (key,))

#         else:
#             # Show latest 100 records
#             cur.execute("""
#                 SELECT
#                     id,
#                     vehicle_plate,
#                     report_date,
#                     flag_reason,
#                     reported_by
#                 FROM mot_reports
#                 ORDER BY report_date DESC, id DESC
#                 LIMIT 100
#             """)

#         records = cur.fetchall()

#         cur.close()
#         conn.close()

#     except Exception as exc:
#         error = str(exc)

#     return render_template_string(
#         TEMPLATE,
#         plate=plate,
#         records=records,
#         total_records=total_records,
#         error=error,
#     )


# @app.route("/add", methods=["POST"])
# def add_report():

#     vehicle_plate = request.form.get("vehicle_plate", "").strip()
#     report_date = request.form.get("report_date") or None
#     flag_reason = request.form.get("flag_reason", "").strip()
#     reported_by = request.form.get("reported_by", "").strip()

#     if not vehicle_plate or not flag_reason:
#         flash(
#             "Vehicle plate and flag reason are required.",
#             "error"
#         )
#         return redirect(url_for("index"))

#     try:

#         conn = connect_db()
#         cur = conn.cursor()

#         cur.execute("""
#             INSERT INTO mot_reports
#             (
#                 vehicle_plate,
#                 report_date,
#                 flag_reason,
#                 reported_by
#             )
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

#         flash(
#             "Ministry report added successfully.",
#             "success"
#         )

#         return redirect(
#             url_for("index", plate=vehicle_plate)
#         )

#     except Exception as exc:

#         flash(
#             f"Could not add report: {exc}",
#             "error"
#         )

#         return redirect(
#             url_for("index", plate=vehicle_plate)
#         )


# TEMPLATE = r"""
# <!DOCTYPE html>

# <html>

# <head>

#     <title>Ministry of Transportation</title>

#     <meta
#         name="viewport"
#         content="width=device-width, initial-scale=1"
#     >

#     <link rel="preconnect" href="https://fonts.googleapis.com">
#     <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
#     <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">

#     <style>

#         :root {
#             --paper: #F5F3ED;
#             --sheet: #FCFBF8;
#             --ink: #1C2740;
#             --ink-soft: #55617A;
#             --rule: #CBCFD8;
#             --rule-strong: #1C2740;
#             --brass: #8A6A2C;
#             --brass-tint: #EFE7D2;
#             --error: #7A322C;
#             --error-bg: #F3E5E1;
#             --success: #2C5B44;
#             --success-bg: #E4EEE7;
#         }

#         * {
#             box-sizing: border-box;
#         }

#         body {
#             margin: 0;
#             font-family: "IBM Plex Sans", Arial, sans-serif;
#             background: var(--paper);
#             color: var(--ink);
#             line-height: 1.5;
#         }

#         .container {
#             max-width: 900px;
#             margin: 0 auto;
#             padding: 48px 24px 80px;
#         }

#         /* ---- Letterhead ---- */

#         .letterhead {
#             display: flex;
#             align-items: center;
#             gap: 18px;
#             padding-bottom: 22px;
#             border-bottom: 3px double var(--rule-strong);
#             margin-bottom: 36px;
#         }

#         .seal {
#             flex: none;
#             width: 52px;
#             height: 52px;
#             border-radius: 50%;
#             border: 1.5px solid var(--ink);
#             display: flex;
#             align-items: center;
#             justify-content: center;
#             font-family: "Source Serif 4", serif;
#             font-weight: 700;
#             font-size: 18px;
#             color: var(--ink);
#             position: relative;
#         }

#         .seal::before {
#             content: "";
#             position: absolute;
#             inset: 5px;
#             border: 1px solid var(--ink);
#             border-radius: 50%;
#         }

#         h1 {
#             font-family: "Source Serif 4", serif;
#             font-weight: 600;
#             font-size: 30px;
#             letter-spacing: 0.01em;
#             margin: 0;
#             color: var(--ink);
#         }

#         .subtitle {
#             color: var(--ink-soft);
#             font-size: 14.5px;
#             margin-top: 3px;
#         }

#         /* ---- Sections (no floating cards — a document, not a dashboard) ---- */

#         .section {
#             padding: 30px 0 38px;
#             border-bottom: 1px solid var(--rule);
#         }

#         .section:last-of-type {
#             border-bottom: none;
#         }

#         .section h2 {
#             font-family: "Source Serif 4", serif;
#             font-weight: 600;
#             font-size: 20px;
#             margin: 0 0 4px;
#         }

#         .section-hint {
#             color: var(--ink-soft);
#             font-size: 13.5px;
#             margin: 0 0 22px;
#         }

#         .grid {
#             display: grid;
#             grid-template-columns: 1fr 1fr;
#             gap: 18px 20px;
#         }

#         label {
#             display: block;
#             font-weight: 500;
#             font-size: 13.5px;
#             color: var(--ink-soft);
#             margin-bottom: 6px;
#         }

#         input,
#         textarea {
#             width: 100%;
#             padding: 10px 12px;
#             border: 1px solid var(--rule);
#             border-radius: 3px;
#             background: var(--sheet);
#             font-family: inherit;
#             font-size: 15px;
#             color: var(--ink);
#         }

#         input[name="vehicle_plate"] {
#             font-family: "IBM Plex Mono", monospace;
#             letter-spacing: 0.06em;
#             text-transform: uppercase;
#         }

#         input:focus,
#         textarea:focus {
#             outline: 2px solid var(--brass);
#             outline-offset: 1px;
#             border-color: var(--brass);
#         }

#         textarea {
#             min-height: 84px;
#             resize: vertical;
#         }

#         .full {
#             grid-column: 1 / -1;
#         }

#         button {
#             padding: 10px 20px;
#             border: 1px solid var(--ink);
#             border-radius: 3px;
#             background: var(--ink);
#             color: var(--sheet);
#             font-family: inherit;
#             font-weight: 500;
#             font-size: 14.5px;
#             cursor: pointer;
#         }

#         button:hover {
#             background: #2A3A5C;
#         }

#         .clear-button {
#             border: 1px solid var(--rule);
#             background: transparent;
#             text-decoration: none;
#             padding: 10px 18px;
#             border-radius: 3px;
#             color: var(--ink-soft);
#             font-weight: 500;
#             font-size: 14.5px;
#         }

#         .clear-button:hover {
#             border-color: var(--ink-soft);
#             color: var(--ink);
#         }

#         .search {
#             display: flex;
#             gap: 10px;
#         }

#         .search input {
#             flex: 1;
#             font-family: "IBM Plex Mono", monospace;
#             letter-spacing: 0.06em;
#         }

#         /* ---- Tally (stats) ---- */

#         .stats {
#             display: flex;
#             gap: 40px;
#             margin-top: 24px;
#             padding-top: 20px;
#             border-top: 1px solid var(--rule);
#         }

#         .stat-number {
#             font-family: "Source Serif 4", serif;
#             font-size: 28px;
#             font-weight: 600;
#             color: var(--ink);
#         }

#         .stat-label {
#             color: var(--ink-soft);
#             font-size: 13px;
#             margin-top: 2px;
#         }

#         /* ---- Ledger table ---- */

#         .table-container {
#             overflow-x: auto;
#             margin-top: 24px;
#         }

#         table {
#             width: 100%;
#             border-collapse: collapse;
#             font-size: 14.5px;
#         }

#         th,
#         td {
#             padding: 11px 12px;
#             border-bottom: 1px solid var(--rule);
#             text-align: left;
#         }

#         th {
#             font-weight: 600;
#             font-size: 13px;
#             color: var(--ink-soft);
#             border-bottom: 1.5px solid var(--rule-strong);
#         }

#         tbody tr:hover {
#             background: var(--sheet);
#         }

#         td strong {
#             font-family: "IBM Plex Mono", monospace;
#             letter-spacing: 0.04em;
#             font-weight: 500;
#         }

#         .success,
#         .error {
#             padding: 12px 14px;
#             border-radius: 3px;
#             margin-bottom: 18px;
#             font-size: 14.5px;
#             border-left: 3px solid;
#         }

#         .success {
#             background: var(--success-bg);
#             color: var(--success);
#             border-color: var(--success);
#         }

#         .error {
#             background: var(--error-bg);
#             color: var(--error);
#             border-color: var(--error);
#         }

#         .showing {
#             margin-top: 16px;
#             color: var(--ink-soft);
#             font-size: 13.5px;
#         }

#         @media(max-width:700px) {

#             .grid {
#                 grid-template-columns: 1fr;
#             }

#             .full {
#                 grid-column: auto;
#             }

#             .search {
#                 flex-direction: column;
#             }

#             .stats {
#                 flex-direction: column;
#                 gap: 16px;
#             }

#             .letterhead {
#                 align-items: flex-start;
#             }
#         }

#     </style>

# </head>


# <body>

# <div class="container">

#     <div class="letterhead">

#         <div class="seal">MOT</div>

#         <div>
#             <h1>Ministry of Transportation</h1>
#             <div class="subtitle">Vehicle Compliance Registry</div>
#         </div>

#     </div>


#     {% with messages = get_flashed_messages(with_categories=true) %}

#         {% for category, message in messages %}

#             <div class="{{ category }}">
#                 {{ message }}
#             </div>

#         {% endfor %}

#     {% endwith %}


#     <!-- ADD REPORT -->

#     <div class="section">

#         <h2>Register a report</h2>
#         <p class="section-hint">
#             File a new compliance flag against a vehicle plate.
#         </p>

#         <form method="post" action="/add">

#             <div class="grid">

#                 <div>

#                     <label>
#                         Vehicle Plate *
#                     </label>

#                     <input
#                         name="vehicle_plate"
#                         placeholder="DL01AB1002"
#                         required
#                     >

#                 </div>


#                 <div>

#                     <label>
#                         Report Date
#                     </label>

#                     <input
#                         type="date"
#                         name="report_date"
#                     >

#                 </div>


#                 <div class="full">

#                     <label>
#                         Flag Reason *
#                     </label>

#                     <textarea
#                         name="flag_reason"
#                         placeholder="UNINSURED — no policy on record"
#                         required
#                     ></textarea>

#                 </div>


#                 <div class="full">

#                     <label>
#                         Reported By
#                     </label>

#                     <input
#                         name="reported_by"
#                         placeholder="federated-integration-engine"
#                     >

#                 </div>


#                 <div class="full">

#                     <button type="submit">
#                         File report
#                     </button>

#                 </div>

#             </div>

#         </form>

#     </div>


#     <!-- SEARCH -->

#     <div class="section">

#         <h2>Search the registry</h2>
#         <p class="section-hint">
#             Look up every report on file for a specific plate, or browse the latest entries.
#         </p>

#         <form class="search" method="get">

#             <input
#                 name="plate"
#                 value="{{ plate }}"
#                 placeholder="Enter vehicle plate, e.g. DL01AB1002"
#             >

#             <button type="submit">
#                 Search
#             </button>

#             {% if plate %}

#                 <a
#                     href="/"
#                     class="clear-button"
#                 >
#                     Show all
#                 </a>

#             {% endif %}

#         </form>


#         <!-- STATISTICS -->

#         <div class="stats">

#             <div class="stat">

#                 <div class="stat-number">
#                     {{ total_records }}
#                 </div>

#                 <div class="stat-label">
#                     Total Reports in Database
#                 </div>

#             </div>


#             <div class="stat">

#                 <div class="stat-number">
#                     {{ records|length }}
#                 </div>

#                 <div class="stat-label">

#                     {% if plate %}
#                         Reports for {{ plate }}
#                     {% else %}
#                         Latest reports shown
#                     {% endif %}

#                 </div>

#             </div>

#         </div>


#         <!-- DATA TABLE -->

#         <div class="table-container">

#             <table>

#                 <thead>

#                     <tr>

#                         <th>ID</th>

#                         <th>Vehicle Plate</th>

#                         <th>Report Date</th>

#                         <th>Flag Reason</th>

#                         <th>Reported By</th>

#                     </tr>

#                 </thead>


#                 <tbody>

#                 {% for r in records %}

#                     <tr>

#                         <td>
#                             {{ r.id }}
#                         </td>

#                         <td>
#                             <strong>
#                                 {{ r.vehicle_plate }}
#                             </strong>
#                         </td>

#                         <td>
#                             {{ r.report_date or "—" }}
#                         </td>

#                         <td>
#                             {{ r.flag_reason or "—" }}
#                         </td>

#                         <td>
#                             {{ r.reported_by or "—" }}
#                         </td>

#                     </tr>

#                 {% else %}

#                     <tr>

#                         <td colspan="5">
#                             No ministry reports found.
#                         </td>

#                     </tr>

#                 {% endfor %}

#                 </tbody>

#             </table>

#         </div>


#         {% if not plate and total_records > 100 %}

#             <div class="showing">

#                 Showing the latest 100 reports out of
#                 {{ total_records }} total reports.

#                 Use the search box above to find a
#                 specific vehicle.

#             </div>

#         {% endif %}

#     </div>

# </div>

# </body>

# </html>
# """


# if __name__ == "__main__":

#     app.run(
#         host="0.0.0.0",
#         port=int(os.getenv("MOT_UI_PORT", "5003")),
#         debug=False
#     )

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


# Keyword buckets used to badge each report by violation category.
# Purely cosmetic classification of existing free-text flag_reason values —
# does not change what is stored or queried.
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

        for record in records:
            record["badge"] = classify_flag(record.get("flag_reason"))

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

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet">

    <style>

        :root {
            --bg: #F1EEE4;
            --bg-deep: #FBFAF5;
            --panel: #FFFFFF;
            --panel-hover: #F6F3E9;
            --ink: #21283A;
            --ink-soft: #66708A;
            --hairline: rgba(33,40,58,0.09);
            --hairline-strong: rgba(33,40,58,0.16);
            --gold: #A3812F;
            --gold-dim: #8A6D28;
            --gold-tint: rgba(163,129,47,0.10);

            --badge-insurance-bg: #F6E2DF;
            --badge-insurance-fg: #9A3E37;
            --badge-emissions-bg: #F4ECD7;
            --badge-emissions-fg: #8A6413;
            --badge-registration-bg: #E1ECF5;
            --badge-registration-fg: #2E5A82;
            --badge-safety-bg: #EEE1F3;
            --badge-safety-fg: #6C3F84;
            --badge-licensing-bg: #DFF0E8;
            --badge-licensing-fg: #226A4D;
            --badge-general-bg: #E7E8F1;
            --badge-general-fg: #454C71;

            --success-fg: #276847;
            --success-bg: #E3F2E8;
            --error-fg: #9A3E37;
            --error-bg: #FAE7E4;
        }

        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: .001ms !important;
                animation-iteration-count: 1 !important;
                transition-duration: .001ms !important;
            }
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: "IBM Plex Sans", Arial, sans-serif;
            color: var(--ink);
            line-height: 1.55;
            background-color: var(--bg);
            background-image:
                radial-gradient(circle at 12% 8%, rgba(163,129,47,0.05), transparent 40%),
                radial-gradient(circle at 88% 92%, rgba(46,90,130,0.04), transparent 45%),
                repeating-radial-gradient(circle at 50% 50%, rgba(33,40,58,0.02) 0, rgba(33,40,58,0.02) 1px, transparent 1px, transparent 34px);
            background-attachment: fixed;
        }

        .container {
            max-width: 920px;
            margin: 0 auto;
            padding: 56px 24px 90px;
        }

        @keyframes riseIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .letterhead,
        .section {
            animation: riseIn .6s cubic-bezier(.2,.7,.3,1) both;
        }

        .letterhead { animation-delay: 0s; }
        .section:nth-of-type(1) { animation-delay: .1s; }
        .section:nth-of-type(2) { animation-delay: .2s; }

        /* ---- Letterhead ---- */

        .letterhead {
            display: flex;
            align-items: center;
            gap: 20px;
            padding-bottom: 26px;
            margin-bottom: 8px;
        }

        .seal {
            flex: none;
            width: 58px;
            height: 58px;
            border-radius: 50%;
            border: 1.5px solid var(--gold);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: "Source Serif 4", serif;
            font-weight: 600;
            font-size: 17px;
            letter-spacing: 0.04em;
            color: var(--gold);
            position: relative;
            box-shadow: 0 0 0 1px rgba(163,129,47,0.15), 0 6px 16px rgba(33,40,58,0.10);
        }

        .seal::before {
            content: "";
            position: absolute;
            inset: 6px;
            border: 1px solid rgba(210,172,71,0.45);
            border-radius: 50%;
        }

        h1 {
            font-family: "Source Serif 4", serif;
            font-weight: 600;
            font-size: 31px;
            letter-spacing: 0.01em;
            margin: 0;
            color: var(--ink);
        }

        .subtitle {
            color: var(--ink-soft);
            font-size: 13.5px;
            letter-spacing: 0.04em;
            margin-top: 4px;
        }

        .ornament {
            height: 1px;
            margin: 0 0 34px;
            background: linear-gradient(90deg, var(--gold) 0%, var(--hairline-strong) 35%, var(--hairline-strong) 65%, var(--gold) 100%);
            position: relative;
        }

        .ornament::after {
            content: "";
            position: absolute;
            left: 50%;
            top: 50%;
            width: 7px;
            height: 7px;
            background: var(--gold);
            transform: translate(-50%, -50%) rotate(45deg);
        }

        /* ---- Sections ---- */

        .section {
            background: var(--panel);
            border: 1px solid var(--hairline);
            border-radius: 10px;
            padding: 30px 32px 34px;
            margin-bottom: 22px;
            box-shadow: 0 10px 28px rgba(33,40,58,0.07);
        }

        .section h2 {
            font-family: "Source Serif 4", serif;
            font-weight: 600;
            font-size: 20px;
            margin: 0 0 4px;
            color: var(--ink);
        }

        .section-hint {
            color: var(--ink-soft);
            font-size: 13.5px;
            margin: 0 0 24px;
        }

        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px 20px;
        }

        label {
            display: block;
            font-weight: 500;
            font-size: 13px;
            color: var(--ink-soft);
            margin-bottom: 7px;
            letter-spacing: 0.01em;
        }

        input,
        textarea {
            width: 100%;
            padding: 11px 13px;
            border: 1px solid var(--hairline-strong);
            border-radius: 6px;
            background: var(--bg-deep);
            font-family: inherit;
            font-size: 15px;
            color: var(--ink);
            transition: border-color .15s ease, box-shadow .15s ease;
        }

        input::placeholder,
        textarea::placeholder {
            color: #99A0B4;
        }

        input[name="vehicle_plate"] {
            font-family: "IBM Plex Mono", monospace;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        input:focus,
        textarea:focus {
            outline: none;
            border-color: var(--gold);
            box-shadow: 0 0 0 3px var(--gold-tint);
        }

        textarea {
            min-height: 84px;
            resize: vertical;
        }

        .full {
            grid-column: 1 / -1;
        }

        button {
            padding: 11px 22px;
            border: 1px solid var(--gold-dim);
            border-radius: 6px;
            background: linear-gradient(180deg, #B99A4E, var(--gold) 60%, var(--gold-dim));
            color: #FFFBF2;
            font-family: inherit;
            font-weight: 600;
            font-size: 14.5px;
            cursor: pointer;
            transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
        }

        button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(163,129,47,0.28);
            filter: brightness(1.03);
        }

        button:active {
            transform: translateY(0);
        }

        .clear-button {
            border: 1px solid var(--hairline-strong);
            background: transparent;
            text-decoration: none;
            padding: 10px 18px;
            border-radius: 6px;
            color: var(--ink-soft);
            font-weight: 500;
            font-size: 14.5px;
            transition: border-color .15s ease, color .15s ease;
        }

        .clear-button:hover {
            border-color: var(--gold-dim);
            color: var(--gold);
        }

        .search {
            display: flex;
            gap: 10px;
        }

        .search input {
            flex: 1;
            font-family: "IBM Plex Mono", monospace;
            letter-spacing: 0.06em;
        }

        /* ---- Tally ---- */

        .stats {
            display: flex;
            gap: 44px;
            margin-top: 26px;
            padding-top: 22px;
            border-top: 1px solid var(--hairline);
        }

        .stat-number {
            font-family: "Source Serif 4", serif;
            font-size: 30px;
            font-weight: 600;
            color: var(--gold);
            font-variant-numeric: tabular-nums;
        }

        .stat-label {
            color: var(--ink-soft);
            font-size: 12.5px;
            margin-top: 3px;
        }

        /* ---- Ledger table ---- */

        .table-container {
            overflow-x: auto;
            margin-top: 26px;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14.5px;
        }

        th,
        td {
            padding: 13px 14px;
            border-bottom: 1px solid var(--hairline);
            text-align: left;
        }

        th {
            font-weight: 600;
            font-size: 12.5px;
            color: var(--ink-soft);
            letter-spacing: 0.02em;
            border-bottom: 1.5px solid var(--hairline-strong);
        }

        tbody tr {
            animation: riseIn .45s ease both;
            transition: background .15s ease;
        }

        tbody tr:nth-child(1) { animation-delay: .05s; }
        tbody tr:nth-child(2) { animation-delay: .10s; }
        tbody tr:nth-child(3) { animation-delay: .15s; }
        tbody tr:nth-child(4) { animation-delay: .20s; }
        tbody tr:nth-child(5) { animation-delay: .25s; }
        tbody tr:nth-child(n+6) { animation-delay: .28s; }

        tbody tr:hover {
            background: var(--panel-hover);
        }

        td strong {
            font-family: "IBM Plex Mono", monospace;
            letter-spacing: 0.05em;
            font-weight: 500;
        }

        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 100px;
            font-size: 12px;
            font-weight: 500;
            letter-spacing: 0.02em;
            white-space: nowrap;
            margin-right: 8px;
        }

        .badge-insurance { background: var(--badge-insurance-bg); color: var(--badge-insurance-fg); }
        .badge-emissions { background: var(--badge-emissions-bg); color: var(--badge-emissions-fg); }
        .badge-registration { background: var(--badge-registration-bg); color: var(--badge-registration-fg); }
        .badge-safety { background: var(--badge-safety-bg); color: var(--badge-safety-fg); }
        .badge-licensing { background: var(--badge-licensing-bg); color: var(--badge-licensing-fg); }
        .badge-general { background: var(--badge-general-bg); color: var(--badge-general-fg); }

        .flag-cell {
            color: var(--ink);
        }

        .flag-text {
            color: var(--ink-soft);
        }

        .success,
        .error {
            padding: 13px 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            font-size: 14.5px;
            border-left: 3px solid;
            animation: riseIn .4s ease both;
        }

        .success {
            background: var(--success-bg);
            color: var(--success-fg);
            border-color: var(--success-fg);
        }

        .error {
            background: var(--error-bg);
            color: var(--error-fg);
            border-color: var(--error-fg);
        }

        .showing {
            margin-top: 18px;
            color: var(--ink-soft);
            font-size: 13.5px;
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
                gap: 18px;
            }

            .letterhead {
                align-items: flex-start;
            }

            .section {
                padding: 24px 20px 28px;
            }
        }

    </style>

</head>


<body>

<div class="container">

    <div class="letterhead">

        <div class="seal">MOT</div>

        <div>
            <h1>Ministry of Transportation</h1>
            <div class="subtitle">VEHICLE COMPLIANCE REGISTRY</div>
        </div>

    </div>

    <div class="ornament"></div>


    {% with messages = get_flashed_messages(with_categories=true) %}

        {% for category, message in messages %}

            <div class="{{ category }}">
                {{ message }}
            </div>

        {% endfor %}

    {% endwith %}


    <!-- ADD REPORT -->

    <div class="section">

        <h2>Register a report</h2>
        <p class="section-hint">
            File a new compliance flag against a vehicle plate.
        </p>

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
                        File report
                    </button>

                </div>

            </div>

        </form>

    </div>


    <!-- SEARCH -->

    <div class="section">

        <h2>Search the registry</h2>
        <p class="section-hint">
            Look up every report on file for a specific plate, or browse the latest entries.
        </p>

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
                    Show all
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
                    Total reports in database
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
                        Latest reports shown
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

                        <td class="flag-cell">
                            <span class="badge badge-{{ r.badge or 'general' }}">{{ (r.badge or 'general')|capitalize }}</span>
                            <span class="flag-text">{{ r.flag_reason or "—" }}</span>
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