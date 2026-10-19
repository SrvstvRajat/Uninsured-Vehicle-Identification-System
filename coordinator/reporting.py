"""
Shared Ministry-of-Transport reporting logic.

Used by TWO callers:
  - app.py             -> real-time: report immediately when a live
                          lookup finds a flagged vehicle (STP-style trigger)
  - generate_report.py -> batch: nightly sweep across all known plates

report_flags() NEVER raises. If mot_db is unreachable, it returns None
(distinct from 0, which means "reachable, nothing new to report") so
callers can tell the difference between "all clear" and "couldn't even
check" without a crash either way.
"""

from datetime import date
from typing import Optional

import mysql.connector

from config import DB_CONFIGS


def _already_reported_today(cursor, plate: str, reason: str) -> bool:
    """
    Dedup check: has this exact plate+reason already been reported today?
    """
    cursor.execute(
        """
        SELECT 1 FROM mot_reports
        WHERE vehicle_plate = %s AND flag_reason = %s AND report_date = %s
        LIMIT 1
        """,
        (plate, reason, date.today()),
    )
    return cursor.fetchone() is not None


def report_flags(result: dict, reported_by: str) -> Optional[int]:
    """
    Given a query_vehicle() result, write any flags to mot_reports that
    haven't already been reported today.

    Returns:
        int  -> number of NEW rows written (0 if vehicle was clean or
                already reported today; mot_db WAS reachable)
        None -> mot_db was unreachable; nothing could be written.
                Callers must treat this as "unknown", not "0 flags",
                and must NOT let it propagate as an exception.
    """
    if not result.get("found"):
        return 0

    if result.get("decision") == "OK — INSURED AND CLEAR":
        return 0

    plate = result.get("plate")
    reasons = result.get("flags") or [result.get("decision")]

    conn = None

    try:
        conn = mysql.connector.connect(**DB_CONFIGS["mot"])
        cursor = conn.cursor()

        written = 0
        for reason in reasons:
            if _already_reported_today(cursor, plate, reason):
                continue

            cursor.execute(
                """
                INSERT INTO mot_reports
                (vehicle_plate, report_date, flag_reason, reported_by)
                VALUES (%s, %s, %s, %s)
                """,
                (plate, date.today(), reason, reported_by),
            )
            written += 1

        conn.commit()
        cursor.close()
        return written

    except Exception as exc:
        # mot_db unreachable, auth failure, table missing, etc.
        # Never let this crash the caller (app.py's live UI or the
        # batch sweep) — surface it as "couldn't report" and move on.
        print(f"[reporting] mot_db unavailable, skipping report: {exc}")
        return None

    finally:
        if conn is not None and conn.is_connected():
            conn.close()
