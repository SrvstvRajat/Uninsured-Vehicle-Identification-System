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
<html lang="en">

<head>

    <meta charset="utf-8">
    <title>Ministry of Transportation · Vehicle Compliance Registry</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">

    <style>

        :root {
            --navy: #0D1B2E;
            --navy-2: #14283F;
            --navy-line: rgba(255,255,255,0.10);
            --paper: #F4F5F7;
            --surface: #FFFFFF;
            --ink: #14202F;
            --ink-2: #55637A;
            --ink-3: #8592A6;
            --line: #E3E7EE;
            --line-strong: #CDD4DF;
            --brass: #B8914A;
            --brass-deep: #96722F;
            --brass-soft: #F5EEDD;

            --b-insurance: #A33A3A;   --b-insurance-bg: #FBEBEA;
            --b-emissions: #8A6212;   --b-emissions-bg: #FAF1DC;
            --b-registration: #285E8E; --b-registration-bg: #E6F0F9;
            --b-safety: #6B3F8C;      --b-safety-bg: #F1E8F7;
            --b-licensing: #1F6B50;   --b-licensing-bg: #E3F3EC;
            --b-general: #46536B;     --b-general-bg: #EAEDF2;

            --ok: #1F6B50;  --ok-bg: #E3F3EC;
            --err: #A33A3A; --err-bg: #FBEBEA;
        }

        * { box-sizing: border-box; }

        html { scroll-behavior: smooth; }

        body {
            margin: 0;
            font-family: "Manrope", system-ui, sans-serif;
            font-size: 15px;
            line-height: 1.55;
            color: var(--ink);
            background: var(--paper);
            -webkit-font-smoothing: antialiased;
        }

        :focus-visible {
            outline: 2px solid var(--brass);
            outline-offset: 2px;
        }

        /* ---------- Masthead ---------- */

        .masthead {
            background:
                radial-gradient(900px 380px at 85% -20%, rgba(184,145,74,0.22), transparent 60%),
                linear-gradient(180deg, var(--navy) 0%, var(--navy-2) 100%);
            color: #fff;
            padding: 34px 0 120px;
            border-bottom: 3px solid var(--brass);
        }

        .wrap {
            max-width: 1120px;
            margin: 0 auto;
            padding: 0 28px;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .seal {
            flex: none;
            width: 48px;
            height: 48px;
            border-radius: 50%;
            border: 1.5px solid var(--brass);
            display: grid;
            place-items: center;
            font-family: "Newsreader", serif;
            font-weight: 600;
            font-size: 15px;
            letter-spacing: 0.06em;
            color: var(--brass);
            box-shadow: inset 0 0 0 4px var(--navy), inset 0 0 0 5px rgba(184,145,74,0.5);
        }

        .brand-name {
            font-size: 14px;
            font-weight: 600;
            letter-spacing: 0.01em;
            color: #fff;
        }

        .brand-sub {
            font-size: 12.5px;
            color: rgba(255,255,255,0.58);
        }

        .hero {
            margin-top: 56px;
            max-width: 640px;
        }

        .hero h1 {
            font-family: "Newsreader", serif;
            font-weight: 500;
            font-size: clamp(34px, 5vw, 50px);
            line-height: 1.08;
            letter-spacing: -0.015em;
            margin: 0 0 14px;
        }

        .hero p {
            margin: 0;
            color: rgba(255,255,255,0.68);
            font-size: 16px;
            max-width: 52ch;
        }

        /* ---------- Search bar (overlaps masthead) ---------- */

        .search-shell {
            margin-top: -44px;
            position: relative;
            z-index: 2;
        }

        .search-card {
            background: var(--surface);
            border-radius: 14px;
            padding: 22px 24px;
            box-shadow: 0 1px 0 rgba(255,255,255,0.6) inset, 0 24px 48px -16px rgba(13,27,46,0.35), 0 2px 6px rgba(13,27,46,0.08);
            display: flex;
            align-items: center;
            gap: 28px;
            flex-wrap: wrap;
        }

        .search-form {
            flex: 1 1 420px;
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .search-field {
            flex: 1;
            position: relative;
        }

        .search-field svg {
            position: absolute;
            left: 15px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--ink-3);
            pointer-events: none;
        }

        .search-field input {
            padding-left: 44px;
            height: 50px;
            font-family: "JetBrains Mono", monospace;
            font-size: 15px;
            letter-spacing: 0.06em;
        }

        .search-field input::placeholder {
            font-family: "Manrope", sans-serif;
            letter-spacing: 0;
        }

        .tally {
            display: flex;
            gap: 28px;
            padding-left: 28px;
            border-left: 1px solid var(--line);
        }

        .tally-num {
            font-family: "Newsreader", serif;
            font-size: 30px;
            font-weight: 500;
            line-height: 1;
            font-variant-numeric: tabular-nums;
            color: var(--navy);
        }

        .tally-label {
            font-size: 12.5px;
            color: var(--ink-2);
            margin-top: 6px;
            max-width: 15ch;
            line-height: 1.35;
        }

        /* ---------- Main layout ---------- */

        .main {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 340px;
            gap: 28px;
            align-items: start;
            margin-top: 28px;
            padding-bottom: 90px;
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 14px;
            box-shadow: 0 1px 2px rgba(13,27,46,0.04), 0 12px 32px -18px rgba(13,27,46,0.18);
        }

        .card-head {
            padding: 22px 26px 18px;
            border-bottom: 1px solid var(--line);
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }

        .card-head h2 {
            font-family: "Newsreader", serif;
            font-weight: 500;
            font-size: 22px;
            letter-spacing: -0.005em;
            margin: 0;
        }

        .card-head .meta {
            font-size: 13px;
            color: var(--ink-2);
        }

        /* ---------- Alerts ---------- */

        .alerts { margin-top: 24px; }

        .success, .error {
            padding: 13px 16px;
            border-radius: 10px;
            margin-bottom: 10px;
            font-size: 14px;
            font-weight: 500;
            border: 1px solid;
        }

        .success { background: var(--ok-bg); color: var(--ok); border-color: rgba(31,107,80,0.25); }
        .error   { background: var(--err-bg); color: var(--err); border-color: rgba(163,58,58,0.25); }

        /* ---------- Ledger ---------- */

        .table-container { overflow-x: auto; }

        table {
            width: 100%;
            border-collapse: collapse;
        }

        th {
            text-align: left;
            font-size: 12.5px;
            font-weight: 600;
            color: var(--ink-2);
            padding: 12px 26px;
            background: #F9FAFC;
            border-bottom: 1px solid var(--line);
            white-space: nowrap;
        }

        td {
            padding: 16px 26px;
            border-bottom: 1px solid var(--line);
            vertical-align: top;
            font-size: 14.5px;
        }

        tbody tr:last-child td { border-bottom: 0; }

        tbody tr { transition: background .15s ease; }
        tbody tr:hover { background: #FAFBFD; }

        .col-id {
            color: var(--ink-3);
            font-variant-numeric: tabular-nums;
            font-size: 13px;
            width: 1%;
        }

        .col-date {
            white-space: nowrap;
            color: var(--ink-2);
            font-variant-numeric: tabular-nums;
        }

        .col-by { color: var(--ink-2); font-size: 13.5px; }

        /* The memorable element: the plate itself */
        .plate {
            display: inline-flex;
            align-items: stretch;
            border: 1.5px solid var(--navy);
            border-radius: 6px;
            overflow: hidden;
            background: #fff;
            font-family: "JetBrains Mono", monospace;
            font-weight: 600;
            font-size: 14px;
            letter-spacing: 0.1em;
            color: var(--navy);
            white-space: nowrap;
        }

        .plate::before {
            content: "IND";
            display: grid;
            place-items: center;
            padding: 0 6px;
            background: var(--navy);
            color: #fff;
            font-size: 8.5px;
            letter-spacing: 0.08em;
        }

        .plate span { padding: 4px 10px; }

        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 100px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 6px;
        }

        .badge-insurance    { background: var(--b-insurance-bg);    color: var(--b-insurance); }
        .badge-emissions    { background: var(--b-emissions-bg);    color: var(--b-emissions); }
        .badge-registration { background: var(--b-registration-bg); color: var(--b-registration); }
        .badge-safety       { background: var(--b-safety-bg);       color: var(--b-safety); }
        .badge-licensing    { background: var(--b-licensing-bg);    color: var(--b-licensing); }
        .badge-general      { background: var(--b-general-bg);      color: var(--b-general); }

        .flag-text {
            display: block;
            color: var(--ink);
            max-width: 46ch;
        }

        .empty {
            text-align: center;
            padding: 56px 26px;
            color: var(--ink-2);
        }

        .empty strong {
            display: block;
            font-family: "Newsreader", serif;
            font-weight: 500;
            font-size: 20px;
            color: var(--ink);
            margin-bottom: 4px;
        }

        .showing {
            padding: 16px 26px;
            border-top: 1px solid var(--line);
            color: var(--ink-2);
            font-size: 13px;
            background: #F9FAFC;
            border-radius: 0 0 14px 14px;
        }

        /* ---------- Form ---------- */

        .side { position: sticky; top: 24px; }

        .side .card-head { display: block; }

        .side .card-head p {
            margin: 4px 0 0;
            font-size: 13px;
            color: var(--ink-2);
        }

        form.report { padding: 22px 26px 26px; }

        .field { margin-bottom: 18px; }

        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: var(--ink);
            margin-bottom: 7px;
        }

        .req { color: var(--brass-deep); }

        input, textarea {
            width: 100%;
            padding: 11px 14px;
            border: 1px solid var(--line-strong);
            border-radius: 10px;
            background: #FBFCFD;
            font-family: inherit;
            font-size: 14.5px;
            color: var(--ink);
            transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
        }

        input::placeholder, textarea::placeholder { color: #9AA6B8; }

        input:hover, textarea:hover { border-color: #B6C0CF; }

        input:focus, textarea:focus {
            outline: none;
            background: #fff;
            border-color: var(--brass);
            box-shadow: 0 0 0 4px rgba(184,145,74,0.16);
        }

        input[name="vehicle_plate"] {
            font-family: "JetBrains Mono", monospace;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }

        input[name="vehicle_plate"]::placeholder { text-transform: none; letter-spacing: 0.04em; }

        textarea { min-height: 96px; resize: vertical; }

        button {
            height: 50px;
            padding: 0 24px;
            border: 0;
            border-radius: 10px;
            background: var(--navy);
            color: #fff;
            font-family: inherit;
            font-size: 14.5px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 1px 0 rgba(255,255,255,0.12) inset, 0 8px 18px -8px rgba(13,27,46,0.6);
            transition: background .15s ease, transform .15s ease;
        }

        button:hover { background: #1B3556; }
        button:active { transform: translateY(1px); }

        button.primary-brass {
            width: 100%;
            background: linear-gradient(180deg, #C4A15C, var(--brass-deep));
            box-shadow: 0 1px 0 rgba(255,255,255,0.3) inset, 0 10px 20px -10px rgba(150,114,47,0.8);
        }

        button.primary-brass:hover { background: linear-gradient(180deg, #CCAA66, #9F7A35); }

        .clear-button {
            flex: none;
            height: 50px;
            display: inline-flex;
            align-items: center;
            padding: 0 18px;
            border: 1px solid var(--line-strong);
            border-radius: 10px;
            color: var(--ink-2);
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
            transition: border-color .15s ease, color .15s ease;
        }

        .clear-button:hover { border-color: var(--brass); color: var(--brass-deep); }

        /* ---------- Responsive ---------- */

        @media (max-width: 960px) {
            .main { grid-template-columns: 1fr; }
            .side { position: static; order: -1; }
        }

        @media (max-width: 680px) {
            .wrap { padding: 0 18px; }
            .masthead { padding-bottom: 104px; }
            .hero { margin-top: 38px; }
            .search-card { padding: 18px; gap: 18px; }
            .search-form { flex-direction: column; align-items: stretch; flex-basis: 100%; }
            .search-form button, .clear-button { width: 100%; justify-content: center; }
            .tally { padding-left: 0; border-left: 0; border-top: 1px solid var(--line); padding-top: 16px; width: 100%; }
            th, td { padding-left: 16px; padding-right: 16px; }
            .card-head { padding-left: 18px; padding-right: 18px; }
        }

        @media (prefers-reduced-motion: reduce) {
            * { transition: none !important; scroll-behavior: auto !important; }
        }

    </style>

</head>


<body>

    <header class="masthead">

        <div class="wrap">

            <div class="brand">
                <div class="seal" aria-hidden="true">MOT</div>
                <div>
                    <div class="brand-name">Ministry of Transportation</div>
                    <div class="brand-sub">Vehicle Compliance Registry</div>
                </div>
            </div>

            <div class="hero">
                <h1>Every flag on file, one plate at a time.</h1>
                <p>
                    Search a vehicle to see its full compliance history,
                    or file a new report against a plate.
                </p>
            </div>

        </div>

    </header>


    <div class="wrap">

        <!-- SEARCH -->

        <div class="search-shell">

            <div class="search-card">

                <form class="search-form" method="get" role="search">

                    <div class="search-field">

                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                             stroke="currentColor" stroke-width="2" stroke-linecap="round"
                             stroke-linejoin="round" aria-hidden="true">
                            <circle cx="11" cy="11" r="7"></circle>
                            <path d="m20 20-3.5-3.5"></path>
                        </svg>

                        <input
                            name="plate"
                            value="{{ plate }}"
                            placeholder="Search by vehicle plate, e.g. DL01AB1002"
                            aria-label="Vehicle plate"
                        >

                    </div>

                    <button type="submit">Search</button>

                    {% if plate %}
                        <a href="/" class="clear-button">Show all</a>
                    {% endif %}

                </form>

                <div class="tally">

                    <div>
                        <div class="tally-num">{{ total_records }}</div>
                        <div class="tally-label">Total reports in database</div>
                    </div>

                    <div>
                        <div class="tally-num">{{ records|length }}</div>
                        <div class="tally-label">
                            {% if plate %}
                                Reports for {{ plate }}
                            {% else %}
                                Latest reports shown
                            {% endif %}
                        </div>
                    </div>

                </div>

            </div>

        </div>


        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="alerts">
                    {% for category, message in messages %}
                        <div class="{{ category }}" role="status">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}

        {% if error %}
            <div class="alerts">
                <div class="error" role="alert">Could not load reports: {{ error }}</div>
            </div>
        {% endif %}


        <div class="main">

            <!-- LEDGER -->

            <section class="card" aria-labelledby="ledger-title">

                <div class="card-head">
                    <h2 id="ledger-title">
                        {% if plate %}Reports for {{ plate }}{% else %}Latest reports{% endif %}
                    </h2>
                    <span class="meta">
                        {{ records|length }} {{ 'report' if records|length == 1 else 'reports' }}
                    </span>
                </div>

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

                                <td class="col-id">{{ r.id }}</td>

                                <td>
                                    <span class="plate"><span>{{ r.vehicle_plate }}</span></span>
                                </td>

                                <td class="col-date">{{ r.report_date or "—" }}</td>

                                <td>
                                    <span class="badge badge-{{ r.badge or 'general' }}">{{ (r.badge or 'general')|capitalize }}</span>
                                    <span class="flag-text">{{ r.flag_reason or "—" }}</span>
                                </td>

                                <td class="col-by">{{ r.reported_by or "—" }}</td>

                            </tr>

                        {% else %}

                            <tr>
                                <td colspan="5" class="empty">
                                    <strong>No ministry reports found</strong>
                                    {% if plate %}
                                        Check the plate for typos, or file a report using the form.
                                    {% else %}
                                        File the first report using the form.
                                    {% endif %}
                                </td>
                            </tr>

                        {% endfor %}

                        </tbody>

                    </table>

                </div>

                {% if not plate and total_records > 100 %}
                    <div class="showing">
                        Showing the latest 100 of {{ total_records }} reports.
                        Search by plate to find a specific vehicle.
                    </div>
                {% endif %}

            </section>


            <!-- ADD REPORT -->

            <aside class="card side" aria-labelledby="form-title">

                <div class="card-head">
                    <h2 id="form-title">Register a report</h2>
                    <p>File a new compliance flag against a vehicle plate.</p>
                </div>

                <form class="report" method="post" action="/add">

                    <div class="field">
                        <label for="vehicle_plate">Vehicle plate <span class="req">*</span></label>
                        <input
                            id="vehicle_plate"
                            name="vehicle_plate"
                            placeholder="DL01AB1002"
                            required
                        >
                    </div>

                    <div class="field">
                        <label for="report_date">Report date</label>
                        <input id="report_date" type="date" name="report_date">
                    </div>

                    <div class="field">
                        <label for="flag_reason">Flag reason <span class="req">*</span></label>
                        <textarea
                            id="flag_reason"
                            name="flag_reason"
                            placeholder="UNINSURED — no policy on record"
                            required
                        ></textarea>
                    </div>

                    <div class="field">
                        <label for="reported_by">Reported by</label>
                        <input
                            id="reported_by"
                            name="reported_by"
                            placeholder="federated-integration-engine"
                        >
                    </div>

                    <button type="submit" class="primary-brass">File report</button>

                </form>

            </aside>

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