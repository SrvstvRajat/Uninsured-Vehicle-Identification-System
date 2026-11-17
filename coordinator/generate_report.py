"""
Generate a Ministry of Transport report using federated queries.

No vehicle_master.pkl is used. Each source database is read once through its
REST API; records are grouped by plate and records stored under a slightly
different plate are linked to the registered vehicle by entity matching
(mediator.bulk_results). Every resulting vehicle gets the same decision logic
as a live lookup, and flagged vehicles are written to ministry_report.csv and
mot_db.mot_reports.
"""

import csv
from datetime import date

import mysql.connector

from config import DB_CONFIGS
from mediator import bulk_results

OUTPUT_CSV = "ministry_report.csv"
OUTPUT_COLUMNS = [
    "vehicle_plate",
    "report_date",
    "flag_reason",
    "reported_by",
]
CLEAR_DECISION = "OK — INSURED AND CLEAR"
REPORTED_BY = "federated-integration-engine"


def _already_reported_today(cursor, plate: str, reason: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM mot_reports
        WHERE vehicle_plate = %s AND flag_reason = %s AND report_date = %s
        LIMIT 1
        """,
        (plate, reason, date.today()),
    )
    return cursor.fetchone() is not None


def write_to_mot_row(cursor, row: dict) -> None:
    """Insert one flagged row into the Ministry database."""
    cursor.execute(
        """
        INSERT INTO mot_reports
        (vehicle_plate, report_date, flag_reason, reported_by)
        VALUES (%s, %s, %s, %s)
        """,
        (
            row["vehicle_plate"],
            row["report_date"],
            row["flag_reason"],
            row["reported_by"],
        ),
    )


def generate_ministry_report() -> None:
    results = bulk_results()
    print(f"Evaluated {len(results)} vehicles (entity-matched across sources).")

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**DB_CONFIGS["mot"])
        cursor = conn.cursor()
    except Exception as exc:
        print(f"[report] mot_db unavailable, writing CSV only: {exc}")

    flag_count = 0
    inserted = 0
    try:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()

            for result in results:
                if result.get("decision") == CLEAR_DECISION:
                    continue
                plate = result.get("vehicle_key") or result.get("plate")
                reasons = result.get("flags") or [result.get("decision")]

                for reason in reasons:
                    row = {
                        "vehicle_plate": plate,
                        "report_date": date.today(),
                        "flag_reason": reason,
                        "reported_by": REPORTED_BY,
                    }
                    writer.writerow(row)
                    flag_count += 1

                    if cursor is not None and not _already_reported_today(
                        cursor, plate, reason
                    ):
                        write_to_mot_row(cursor, row)
                        inserted += 1

                if cursor is not None:
                    conn.commit()

        print(f"{flag_count} flags written to {OUTPUT_CSV}")
        if cursor is not None:
            print(f"{inserted} new rows written to mot_db.mot_reports "
                  "(flags already reported today were skipped).")

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    generate_ministry_report()


# ---------------------------------------------------------------------
# Scheduling — run this automatically instead of by hand
# ---------------------------------------------------------------------
#
# Mac/Linux (cron), e.g. daily at 2 AM:
#   crontab -e
#   0 2 * * * cd /path/to/project && /usr/bin/python3 generate_report.py >> mot_batch.log 2>&1
#
# Windows (Task Scheduler):
#   Create Task -> Trigger: Daily, 2:00 AM
#   Action: Start a program
#     Program: python.exe
#     Arguments: generate_report.py
#     Start in: C:\path\to\project