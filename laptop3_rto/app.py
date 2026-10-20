import os
import re
from datetime import date, datetime

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, request, render_template_string, redirect, url_for

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("LOCAL_DB_HOST", "localhost"),
    "port": int(os.getenv("LOCAL_DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("LOCAL_DB_NAME", "rto_db"),
}

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

PLATE_RE = re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}$")
OFFICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ,.'\-]{1,59}$")


def normalize_plate(raw):
    if raw is None:
        return ""
    return re.sub(r"[\s\-]", "", raw.strip().upper())


def parse_date(raw, field_label, errors):
    raw = (raw or "").strip()

    if not raw:
        return None

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()

    except ValueError:
        errors.append(
            f"{field_label} must be a valid date (YYYY-MM-DD)."
        )
        return None


def validate_rto_record(form, editing_car_id=None):
    """
    Returns (errors: list[str], cleaned: dict).
    cleaned only contains keys worth trusting if errors is empty.
    """

    errors = []
    cleaned = {}

    raw_car_id = form.get("car_id", "")
    car_id = normalize_plate(raw_car_id)

    if not car_id:
        errors.append("Car ID is required.")

    elif not PLATE_RE.match(car_id):
        errors.append(
            f"'{raw_car_id}' doesn't look like a valid plate/car ID "
            "(expected pattern like DL01AB1234)."
        )

    cleaned["car_id"] = car_id

    registration_date = parse_date(
        form.get("registration_date"),
        "Registration date",
        errors
    )

    if registration_date is None and not errors:
        errors.append("Registration date is required.")

    elif registration_date and registration_date > date.today():
        errors.append("Registration date can't be in the future.")

    cleaned["registration_date"] = registration_date

    renewal_date = parse_date(
        form.get("renewal_date"),
        "Renewal date",
        errors
    )

    if (
        renewal_date
        and registration_date
        and renewal_date <= registration_date
    ):
        errors.append(
            "Renewal date must be after the registration date."
        )

    cleaned["renewal_date"] = renewal_date

    rto_office = form.get("rto_office", "").strip()

    if not rto_office:
        errors.append("RTO office is required.")

    elif not OFFICE_RE.match(rto_office):
        errors.append(
            "RTO office should be plain text under 60 characters."
        )

    cleaned["rto_office"] = rto_office

    if cleaned["car_id"] and not errors:

        existing = find_by_car_id(cleaned["car_id"])

        if existing and editing_car_id != cleaned["car_id"]:

            errors.append(
                f"Car ID '{cleaned['car_id']}' already has an RTO record. "
                "Use Edit instead of Add, or check for a typo."
            )

    return errors, cleaned


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


NORMALIZED_MATCH_SQL = (
    "UPPER(REPLACE(REPLACE(car_id, ' ', ''), '-', '')) = %s"
)


def find_by_car_id(car_id):

    car_id = normalize_plate(car_id)

    if not car_id:
        return None

    conn = get_connection()

    try:

        cur = conn.cursor(dictionary=True)

        cur.execute(
            f"""
            SELECT *
            FROM rto_records
            WHERE {NORMALIZED_MATCH_SQL}
            LIMIT 1
            """,
            (car_id,),
        )

        row = cur.fetchone()

        cur.close()

        return row

    finally:
        conn.close()


def search_rto_records(term):

    """
    If a search term is provided:
        Return up to 50 matching records.

    If no search term is provided:
        Return the latest 50 RTO records.
    """

    term = (term or "").strip()

    conn = get_connection()

    try:

        cur = conn.cursor(dictionary=True)

        if term:

            like = f"%{term}%"

            cur.execute(
                """
                SELECT *
                FROM rto_records
                WHERE car_id LIKE %s
                   OR rto_office LIKE %s
                ORDER BY id DESC
                LIMIT 50
                """,
                (like, like),
            )

        else:

            cur.execute(
                """
                SELECT *
                FROM rto_records
                ORDER BY id DESC
                LIMIT 50
                """
            )

        rows = cur.fetchall()

        cur.close()

        return rows

    finally:
        conn.close()


def insert_rto_record(cleaned):

    conn = get_connection()

    try:

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO rto_records
            (
                car_id,
                registration_date,
                renewal_date,
                rto_office
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                cleaned["car_id"],
                cleaned["registration_date"],
                cleaned["renewal_date"],
                cleaned["rto_office"],
            ),
        )

        conn.commit()

        cur.close()

    finally:
        conn.close()


def update_rto_record(original_car_id, cleaned):

    original_car_id = normalize_plate(original_car_id)

    conn = get_connection()

    try:

        cur = conn.cursor()

        cur.execute(
            f"""
            UPDATE rto_records

            SET
                car_id = %s,
                registration_date = %s,
                renewal_date = %s,
                rto_office = %s

            WHERE {NORMALIZED_MATCH_SQL}
            """,
            (
                cleaned["car_id"],
                cleaned["registration_date"],
                cleaned["renewal_date"],
                cleaned["rto_office"],
                original_car_id,
            ),
        )

        conn.commit()

        affected = cur.rowcount

        cur.close()

        return affected

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# TEMPLATE
# ---------------------------------------------------------------------------

TEMPLATE = """
<!doctype html>

<html lang="en">

<head>

    <meta charset="utf-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1"
    >

    <title>Laptop 3 — RTO Records</title>


    <!-- Modern fonts -->

    <link
        rel="preconnect"
        href="https://fonts.googleapis.com"
    >

    <link
        rel="preconnect"
        href="https://fonts.gstatic.com"
        crossorigin
    >

    <link
        href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap"
        rel="stylesheet"
    >


    <style>

        /* ============================================================
           COLOR SYSTEM
        ============================================================ */

        :root {

            --background: #f7f8fc;

            --white: #ffffff;

            --text: #242633;

            --text-soft: #686d7c;

            --text-muted: #9ca1af;

            --border: #e9eaf1;

            --border-hover: #d9dce7;


            /* Pastel blue */

            --blue: #7c9cff;
            --blue-dark: #6385ed;
            --blue-soft: #eef3ff;


            /* Pastel lavender */

            --lavender: #b39ddb;
            --lavender-soft: #f3effc;


            /* Pastel mint */

            --mint: #8dd9bd;
            --mint-soft: #ebfaf4;


            /* Pastel peach */

            --peach: #f4b99d;
            --peach-soft: #fff2ec;


            /* Pastel yellow */

            --yellow: #f3d27a;
            --yellow-soft: #fff9e9;


            /* Status */

            --green: #3e9d72;
            --green-soft: #edf9f3;

            --red: #d66b78;
            --red-soft: #fff0f2;


            /* Shadows */

            --shadow-small:
                0 2px 8px rgba(40, 45, 70, 0.035);

            --shadow:
                0 12px 35px rgba(40, 45, 70, 0.055);

            --shadow-hover:
                0 18px 45px rgba(40, 45, 70, 0.09);

        }


        /* ============================================================
           RESET
        ============================================================ */

        * {
            box-sizing: border-box;
        }


        body {

            margin: 0;

            min-height: 100vh;

            background:
                radial-gradient(
                    circle at 10% 0%,
                    rgba(179, 157, 219, 0.12),
                    transparent 25%
                ),

                radial-gradient(
                    circle at 100% 100%,
                    rgba(141, 217, 189, 0.12),
                    transparent 25%
                ),

                var(--background);

            color: var(--text);

            font-family:
                "DM Sans",
                -apple-system,
                BlinkMacSystemFont,
                "Segoe UI",
                sans-serif;
        }


        /* ============================================================
           PAGE
        ============================================================ */

        .page {

            width:
                min(
                    1180px,
                    calc(100% - 42px)
                );

            margin: 0 auto;

            padding:
                32px 0 60px;
        }


        /* ============================================================
           HEADER
        ============================================================ */

        .header {

            display: flex;

            align-items: center;

            justify-content: space-between;

            margin-bottom: 22px;
        }


        .brand {

            display: flex;

            align-items: center;

            gap: 13px;
        }


        .brand-icon {

            width: 43px;

            height: 43px;

            display: flex;

            align-items: center;

            justify-content: center;

            border-radius: 13px;

            background:
                linear-gradient(
                    135deg,
                    #8ba7ff,
                    #a5baff
                );

            color: white;

            font-family:
                "Space Grotesk",
                sans-serif;

            font-size: 13px;

            font-weight: 700;

            box-shadow:
                0 8px 20px
                rgba(124, 156, 255, 0.20);
        }


        .brand-name {

            font-family:
                "Space Grotesk",
                sans-serif;

            font-size: 16px;

            font-weight: 700;

            letter-spacing: -0.025em;
        }


        .brand-subtitle {

            margin-top: 2px;

            color: var(--text-muted);

            font-size: 11px;

            font-weight: 500;
        }


        .status {

            display: flex;

            align-items: center;

            gap: 8px;

            padding:
                8px 12px;

            border:
                1px solid var(--border);

            border-radius: 999px;

            background: rgba(255,255,255,.8);

            color: var(--text-soft);

            font-size: 11px;

            font-weight: 600;
        }


        .status-dot {

            width: 7px;

            height: 7px;

            border-radius: 50%;

            background: var(--mint);

            box-shadow:
                0 0 0 4px
                rgba(141,217,189,.16);
        }


        /* ============================================================
           MAIN LAYOUT
        ============================================================ */

        .layout {

            display: grid;

            grid-template-columns:
                215px minmax(0, 1fr);

            gap: 19px;
        }


        /* ============================================================
           SIDEBAR
        ============================================================ */

        .sidebar {

            height: fit-content;

            padding: 13px;

            background: rgba(255,255,255,.88);

            border:
                1px solid var(--border);

            border-radius: 18px;

            box-shadow: var(--shadow-small);
        }


        .sidebar-label {

            padding:
                9px 10px 8px;

            color: var(--text-muted);

            font-size: 9px;

            font-weight: 700;

            letter-spacing: .12em;

            text-transform: uppercase;
        }


        .nav {

            display: flex;

            flex-direction: column;

            gap: 4px;
        }


        .nav a {

            display: flex;

            align-items: center;

            gap: 10px;

            padding:
                11px 11px;

            border-radius: 10px;

            color: var(--text-soft);

            text-decoration: none;

            font-size: 12px;

            font-weight: 600;

            transition:
                background .18s ease,
                color .18s ease,
                transform .18s ease;
        }


        .nav a:hover {

            background: #fafbfe;

            color: var(--text);

            transform: translateX(2px);
        }


        .nav a.active {

            background: var(--blue-soft);

            color: var(--blue-dark);
        }


        .nav-icon {

            width: 26px;

            height: 26px;

            display: flex;

            align-items: center;

            justify-content: center;

            border-radius: 8px;

            background: #f4f5f8;

            font-size: 14px;
        }


        .nav a.active .nav-icon {

            background: white;

            box-shadow:
                0 2px 5px rgba(50,60,90,.05);
        }


        /* ============================================================
           DATABASE CARD
        ============================================================ */

        .database-card {

            margin-top: 18px;

            padding: 13px;

            border:
                1px solid var(--border);

            border-radius: 12px;

            background:
                linear-gradient(
                    135deg,
                    #fbfbff,
                    #f8fafc
                );
        }


        .database-label {

            color: var(--text-muted);

            font-size: 8px;

            font-weight: 700;

            letter-spacing: .1em;

            text-transform: uppercase;
        }


        .database-name {

            margin-top: 6px;

            color: var(--text);

            font-family:
                "Space Grotesk",
                sans-serif;

            font-size: 11px;

            font-weight: 600;

            word-break: break-word;
        }


        /* ============================================================
           CONTENT
        ============================================================ */

        .content {

            overflow: hidden;

            background:
                rgba(255,255,255,.94);

            border:
                1px solid var(--border);

            border-radius: 18px;

            box-shadow: var(--shadow);
        }


        /* ============================================================
           HERO
        ============================================================ */

        .hero {

            position: relative;

            overflow: hidden;

            padding:
                31px 33px 30px;

            border-bottom:
                1px solid var(--border);

            background:
                linear-gradient(
                    135deg,
                    #ffffff 0%,
                    #f8f9ff 60%,
                    #f7fcfa 100%
                );
        }


        .hero::after {

            content: "";

            position: absolute;

            width: 180px;

            height: 180px;

            right: -70px;

            top: -90px;

            border-radius: 50%;

            background:
                rgba(179,157,219,.13);
        }


        .hero-label {

            position: relative;

            z-index: 1;

            margin-bottom: 10px;

            color: var(--blue-dark);

            font-size: 9px;

            font-weight: 700;

            letter-spacing: .13em;

            text-transform: uppercase;
        }


        .hero h1 {

            position: relative;

            z-index: 1;

            margin: 0;

            font-family:
                "Space Grotesk",
                sans-serif;

            font-size:
                clamp(
                    28px,
                    4vw,
                    39px
                );

            line-height: 1.07;

            letter-spacing: -.055em;
        }


        .hero p {

            position: relative;

            z-index: 1;

            max-width: 610px;

            margin:
                12px 0 0;

            color: var(--text-soft);

            font-size: 12px;

            line-height: 1.6;
        }


        /* ============================================================
           WORKSPACE
        ============================================================ */

        .workspace {

            padding:
                25px 33px 31px;
        }


        /* ============================================================
           NOTICES
        ============================================================ */

        .notice {

            display: flex;

            gap: 10px;

            padding:
                12px 14px;

            margin-bottom: 19px;

            border-radius: 10px;

            font-size: 12px;

            line-height: 1.5;
        }


        .notice.success {

            color: var(--green);

            background: var(--green-soft);

            border:
                1px solid #ccefe0;
        }


        .notice.errors {

            color: var(--red);

            background: var(--red-soft);

            border:
                1px solid #f4d0d5;
        }


        .notice ul {

            margin:
                5px 0 0 17px;

            padding: 0;
        }


        /* ============================================================
           SEARCH
        ============================================================ */

        .search-row {

            display: flex;

            gap: 9px;

            margin-bottom: 21px;
        }


        .search-wrapper {

            position: relative;

            flex: 1;
        }


        .search-icon {

            position: absolute;

            left: 14px;

            top: 50%;

            transform:
                translateY(-50%);

            color: #a2a7b4;

            font-size: 16px;

            pointer-events: none;
        }


        input {

            width: 100%;

            padding:
                12px 14px;

            border:
                1px solid var(--border-hover);

            border-radius: 10px;

            outline: none;

            background: white;

            color: var(--text);

            font-family: inherit;

            font-size: 12px;

            transition:
                border .18s ease,
                box-shadow .18s ease;
        }


        .search-wrapper input {

            padding-left: 39px;
        }


        input::placeholder {

            color: #a7abb6;
        }


        input:focus {

            border-color:
                #a9bbff;

            box-shadow:
                0 0 0 3px
                rgba(124,156,255,.10);
        }


        button {

            padding:
                0 18px;

            border: none;

            border-radius: 10px;

            background:
                linear-gradient(
                    135deg,
                    #7d9eff,
                    #8daaff
                );

            color: white;

            font-family: inherit;

            font-size: 12px;

            font-weight: 700;

            cursor: pointer;

            transition:
                transform .18s ease,
                box-shadow .18s ease;
        }


        button:hover {

            transform:
                translateY(-1px);

            box-shadow:
                0 8px 18px
                rgba(124,156,255,.20);
        }


        /* ============================================================
           SECTION HEADER
        ============================================================ */

        .section-header {

            display: flex;

            align-items: center;

            justify-content: space-between;

            margin-bottom: 11px;
        }


        .section-title {

            font-family:
                "Space Grotesk",
                sans-serif;

            font-size: 14px;

            font-weight: 600;

            letter-spacing: -.015em;
        }


        .section-count {

            padding:
                4px 8px;

            border-radius: 999px;

            background: var(--lavender-soft);

            color: #8b72b6;

            font-size: 9px;

            font-weight: 700;
        }


        /* ============================================================
           TABLE
        ============================================================ */

        .table-container {

            overflow-x: auto;

            border:
                1px solid var(--border);

            border-radius: 12px;

            background: white;
        }


        table {

            width: 100%;

            min-width: 650px;

            border-collapse: collapse;

            font-size: 11px;
        }


        th {

            padding:
                12px 14px;

            text-align: left;

            background:
                #fafbfc;

            color: var(--text-muted);

            border-bottom:
                1px solid var(--border);

            font-size: 9px;

            font-weight: 700;

            letter-spacing: .08em;

            text-transform: uppercase;
        }


        td {

            padding:
                13px 14px;

            color: #555b6b;

            border-bottom:
                1px solid #f0f1f4;
        }


        tbody tr {

            transition:
                background .15s ease;
        }


        tbody tr:hover {

            background:
                #fbfcff;
        }


        tr:last-child td {

            border-bottom: none;
        }


        /* ============================================================
           CAR ID / NUMBER PLATE
        ============================================================ */

        .plate {

            display: inline-flex;

            align-items: center;

            padding:
                5px 8px;

            border-radius: 6px;

            background:
                linear-gradient(
                    135deg,
                    #f2f4fa,
                    #f8f9fc
                );

            border:
                1px solid #e5e7ee;

            color: #343947;

            font-family:
                "Space Grotesk",
                monospace;

            font-size: 10px;

            font-weight: 700;

            letter-spacing: .025em;
        }


        /* ============================================================
           EDIT
        ============================================================ */

        .edit-link {

            color:
                var(--blue-dark);

            text-decoration: none;

            font-size: 11px;

            font-weight: 700;
        }


        .edit-link:hover {

            text-decoration: underline;
        }


        /* ============================================================
           EMPTY STATE
        ============================================================ */

        .empty {

            padding:
                55px 20px;

            border:
                1px dashed
                var(--border-hover);

            border-radius: 12px;

            text-align: center;

            color: var(--text-muted);

            font-size: 12px;

            background:
                rgba(250,251,253,.7);
        }


        .empty-icon {

            margin-bottom: 8px;

            color:
                #c7cbd5;

            font-size: 25px;
        }


        /* ============================================================
           FORM
        ============================================================ */

        .form-card {

            max-width: 720px;

            padding: 20px;

            border:
                1px solid var(--border);

            border-radius: 13px;

            background:
                linear-gradient(
                    135deg,
                    #ffffff,
                    #fbfcff
                );

            box-shadow:
                var(--shadow-small);
        }


        .form-grid {

            display: grid;

            grid-template-columns:
                1fr 1fr;

            gap: 17px;
        }


        .field-row.full {

            grid-column:
                1 / -1;
        }


        .field-row label {

            display: block;

            margin-bottom: 7px;

            color:
                var(--text-soft);

            font-size: 9px;

            font-weight: 700;

            letter-spacing: .08em;

            text-transform: uppercase;
        }


        .required {

            color:
                var(--blue-dark);
        }


        .form-actions {

            display: flex;

            align-items: center;

            gap: 12px;

            margin-top: 20px;
        }


        .cancel {

            color:
                var(--text-soft);

            text-decoration: none;

            font-size: 11px;

            font-weight: 600;
        }


        .cancel:hover {

            color:
                var(--text);
        }


        /* ============================================================
           FOOTER
        ============================================================ */

        .footer {

            margin-top: 17px;

            text-align: right;

            color:
                #b0b4be;

            font-size: 9px;
        }


        /* ============================================================
           RESPONSIVE
        ============================================================ */

        @media (max-width: 800px) {

            .page {

                width:
                    calc(100% - 24px);

                padding-top: 20px;
            }


            .layout {

                grid-template-columns: 1fr;
            }


            .sidebar {

                position: static;
            }


            .nav {

                display: grid;

                grid-template-columns:
                    1fr 1fr;
            }


            .database-card {

                display: none;
            }


            .hero,
            .workspace {

                padding-left: 20px;

                padding-right: 20px;
            }


            .form-grid {

                grid-template-columns:
                    1fr;
            }


            .field-row.full {

                grid-column: auto;
            }
        }


        @media (max-width: 520px) {

            .status {

                display: none;
            }


            .search-row {

                flex-direction:
                    column;
            }


            button {

                height: 43px;
            }
        }

    </style>

</head>


<body>


<div class="page">


    <!-- ============================================================
         HEADER
    ============================================================ -->

    <header class="header">


        <div class="brand">


            <div class="brand-icon">

                03

            </div>


            <div>

                <div class="brand-name">

                    RTO DATA SYSTEM

                </div>


                <div class="brand-subtitle">

                    Laptop 3 · Local Operations

                </div>

            </div>


        </div>


        <div class="status">

            <span class="status-dot"></span>

            Local database active

        </div>


    </header>



    <!-- ============================================================
         LAYOUT
    ============================================================ -->

    <div class="layout">


        <!-- ========================================================
             SIDEBAR
        ========================================================= -->

        <aside class="sidebar">


            <div class="sidebar-label">

                Workspace

            </div>


            <nav class="nav">


                <a
                    class="{{ 'active' if mode=='find' else '' }}"
                    href="{{ url_for('find') }}"
                >

                    <span class="nav-icon">
                        ⌕
                    </span>

                    Find records

                </a>


                <a
                    class="{{ 'active' if mode=='add' else '' }}"
                    href="{{ url_for('add') }}"
                >

                    <span class="nav-icon">
                        ＋
                    </span>

                    Append record

                </a>


            </nav>


            <div class="database-card">


                <div class="database-label">

                    Connected source

                </div>


                <div class="database-name">

                    {{ db_name }}

                </div>


            </div>


        </aside>



        <!-- ========================================================
             CONTENT
        ========================================================= -->

        <main class="content">


            <!-- HERO -->

            <section class="hero">


                <div class="hero-label">

                    RTO / 003 / LOCAL

                </div>


                <h1>

                    Vehicle records,<br>

                    made simple.

                </h1>


                <p>

                    Manage registration data stored on this laptop's
                    local RTO database.

                </p>


            </section>



            <!-- WORKSPACE -->

            <section class="workspace">


                <!-- SUCCESS MESSAGE -->

                {% if success %}

                    <div class="notice success">

                        <span>
                            ✓
                        </span>

                        <div>

                            {{ success }}

                        </div>

                    </div>

                {% endif %}



                <!-- ERROR MESSAGE -->

                {% if errors %}

                    <div class="notice errors">

                        <span>
                            !
                        </span>


                        <div>

                            <strong>
                                Please fix the following:
                            </strong>


                            <ul>

                                {% for e in errors %}

                                    <li>
                                        {{ e }}
                                    </li>

                                {% endfor %}

                            </ul>

                        </div>

                    </div>

                {% endif %}



                <!-- =================================================
                     FIND PAGE
                ================================================== -->

                {% if mode == 'find' %}


                    <!-- SEARCH -->

                    <form
                        class="search-row"
                        method="get"
                        action="{{ url_for('find') }}"
                    >


                        <div class="search-wrapper">


                            <span class="search-icon">

                                ⌕

                            </span>


                            <input
                                name="q"
                                placeholder="Search by car ID or RTO office..."
                                value="{{ query or '' }}"
                            >


                        </div>


                        <button type="submit">

                            Search

                        </button>


                    </form>



                    <!-- RESULTS -->

                    <div class="section-header">


                        <div class="section-title">


                            {% if query %}

                                Search results

                            {% else %}

                                Latest RTO records

                            {% endif %}


                        </div>


                        <div class="section-count">

                            Showing {{ rows|length }} records

                        </div>


                    </div>



                    {% if rows %}


                        <div class="table-container">


                            <table>


                                <thead>


                                    <tr>


                                        <th>
                                            Car ID
                                        </th>


                                        <th>
                                            Registered
                                        </th>


                                        <th>
                                            Renewal
                                        </th>


                                        <th>
                                            RTO Office
                                        </th>


                                        <th>
                                        </th>


                                    </tr>


                                </thead>



                                <tbody>


                                {% for r in rows %}


                                    <tr>


                                        <td>

                                            <span class="plate">

                                                {{ r.car_id }}

                                            </span>

                                        </td>


                                        <td>

                                            {{ r.registration_date or '—' }}

                                        </td>


                                        <td>

                                            {{ r.renewal_date or '—' }}

                                        </td>


                                        <td>

                                            {{ r.rto_office or '—' }}

                                        </td>


                                        <td>

                                            <a
                                                class="edit-link"
                                                href="{{
                                                    url_for(
                                                        'edit',
                                                        car_id=r.car_id
                                                    )
                                                }}"
                                            >

                                                Edit →

                                            </a>

                                        </td>


                                    </tr>


                                {% endfor %}


                                </tbody>


                            </table>


                        </div>


                    {% else %}


                        <div class="empty">


                            <div class="empty-icon">

                                ⌁

                            </div>


                            {% if query %}

                                No matching RTO records found.

                            {% else %}

                                No RTO records available.

                            {% endif %}


                        </div>


                    {% endif %}


                {% endif %}



                <!-- =================================================
                     ADD / EDIT PAGE
                ================================================== -->

                {% if mode in ('add', 'edit') %}


                    <div class="section-header">


                        <div>


                            <div class="section-title">


                                {{

                                    'Edit RTO record'

                                    if mode == 'edit'

                                    else

                                    'Append new record'

                                }}


                            </div>


                            <div class="section-count">

                                Fields marked * are required

                            </div>


                        </div>


                    </div>



                    <form
                        class="form-card"
                        method="post"
                        action="{{
                            url_for(
                                'edit',
                                car_id=editing_car_id
                            )
                            if mode == 'edit'
                            else
                            url_for('add')
                        }}"
                    >


                        <div class="form-grid">


                            <!-- CAR ID -->

                            <div class="field-row full">


                                <label>

                                    Car ID

                                    <span class="required">
                                        *
                                    </span>

                                </label>


                                <input
                                    name="car_id"
                                    value="{{
                                        form_values.car_id
                                        if form_values
                                        else
                                        (editing_car_id or '')
                                    }}"
                                    placeholder="e.g. DL01AB1234"
                                    required
                                >


                            </div>



                            <!-- REGISTRATION DATE -->

                            <div class="field-row">


                                <label>

                                    Registration Date

                                    <span class="required">
                                        *
                                    </span>

                                </label>


                                <input
                                    type="date"
                                    name="registration_date"
                                    value="{{
                                        form_values.registration_date
                                        if form_values
                                        else
                                        ''
                                    }}"
                                    required
                                >


                            </div>



                            <!-- RENEWAL DATE -->

                            <div class="field-row">


                                <label>

                                    Renewal Date

                                </label>


                                <input
                                    type="date"
                                    name="renewal_date"
                                    value="{{
                                        form_values.renewal_date
                                        if form_values
                                        else
                                        ''
                                    }}"
                                >


                            </div>



                            <!-- RTO OFFICE -->

                            <div class="field-row full">


                                <label>

                                    RTO Office

                                    <span class="required">
                                        *
                                    </span>

                                </label>


                                <input
                                    name="rto_office"
                                    value="{{
                                        form_values.rto_office
                                        if form_values
                                        else
                                        ''
                                    }}"
                                    placeholder="e.g. Delhi South RTO"
                                    required
                                >


                            </div>


                        </div>



                        <!-- ACTIONS -->

                        <div class="form-actions">


                            <button type="submit">


                                {{

                                    'Save Changes'

                                    if mode == 'edit'

                                    else

                                    'Add RTO Record'

                                }}


                            </button>



                            {% if mode == 'edit' %}


                                <a
                                    class="cancel"
                                    href="{{ url_for('find') }}"
                                >

                                    Cancel

                                </a>


                            {% endif %}


                        </div>


                    </form>


                {% endif %}



                <!-- FOOTER -->

                <div class="footer">

                    rto_db · localhost · port 3306

                </div>


            </section>


        </main>


    </div>


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

        success = (
            f"RTO record '{query}' added successfully."
        )

    elif msg == "saved":

        success = (
            f"Changes to '{query}' saved successfully."
        )

    # Always show latest 50 records when there is no search term.
    # When query exists, show up to 50 matching records.
    rows = search_rto_records(query)

    return render_template_string(

        TEMPLATE,

        mode="find",

        db_name=DB_CONFIG["database"],

        query=query,

        rows=rows,

        errors=None,

        success=success,

        form_values=None,

        editing_car_id=None,
    )


@app.route("/add", methods=["GET", "POST"])
def add():

    if request.method == "GET":

        return render_template_string(

            TEMPLATE,

            mode="add",

            db_name=DB_CONFIG["database"],

            query=None,

            rows=None,

            errors=None,

            success=None,

            form_values=None,

            editing_car_id=None,
        )


    errors, cleaned = validate_rto_record(
        request.form
    )


    if errors:

        return render_template_string(

            TEMPLATE,

            mode="add",

            db_name=DB_CONFIG["database"],

            query=None,

            rows=None,

            errors=errors,

            success=None,

            form_values=request.form,

            editing_car_id=None,
        )


    insert_rto_record(cleaned)


    return redirect(
        url_for(
            "find",
            q=cleaned["car_id"],
            msg="added"
        )
    )


@app.route("/edit/<car_id>", methods=["GET", "POST"])
def edit(car_id):

    car_id = normalize_plate(car_id)


    if request.method == "GET":

        existing = find_by_car_id(car_id)


        if not existing:

            return render_template_string(

                TEMPLATE,

                mode="find",

                db_name=DB_CONFIG["database"],

                query=car_id,

                rows=[],

                errors=[
                    f"No RTO record found for car ID '{car_id}'."
                ],

                success=None,

                form_values=None,

                editing_car_id=None,
            )


        return render_template_string(

            TEMPLATE,

            mode="edit",

            db_name=DB_CONFIG["database"],

            query=None,

            rows=None,

            errors=None,

            success=None,

            form_values=existing,

            editing_car_id=car_id,
        )


    errors, cleaned = validate_rto_record(

        request.form,

        editing_car_id=car_id
    )


    if errors:

        return render_template_string(

            TEMPLATE,

            mode="edit",

            db_name=DB_CONFIG["database"],

            query=None,

            rows=None,

            errors=errors,

            success=None,

            form_values=request.form,

            editing_car_id=car_id,
        )


    affected = update_rto_record(
        car_id,
        cleaned
    )


    if affected == 0:

        return render_template_string(

            TEMPLATE,

            mode="edit",

            db_name=DB_CONFIG["database"],

            query=None,

            rows=None,

            errors=[
                f"No matching row for car ID '{car_id}' "
                "-- it may have been changed or removed by "
                "someone else. Please search again."
            ],

            success=None,

            form_values=request.form,

            editing_car_id=car_id,
        )


    return redirect(

        url_for(

            "find",

            q=cleaned["car_id"],

            msg="saved"
        )
    )




# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5030,
        debug=False
    )