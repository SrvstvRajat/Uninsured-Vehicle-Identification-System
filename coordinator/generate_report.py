"""
Generate a Ministry of Transport report using federated queries.

No vehicle_master.pkl is used. Candidate vehicle identifiers are collected
from the independent source systems, and every candidate is evaluated by the
mediator at runtime.
"""

import csv
from datetime import date

import mysql.connector

from config import DB_CONFIGS
from mediator import list_candidate_plates, query_vehicle


OUTPUT_CSV = "ministry_report.csv"
OUTPUT_COLUMNS = [
    "vehicle_plate",
    "report_date",
    "flag_reason",
    "reported_by",
]


def write_to_mot_row(cursor, row: dict) -> None:
    """Insert one flagged row into the Ministry database immediately."""
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
    plates = list_candidate_plates()
    flag_count = 0

    print(f"Found {len(plates)} candidate vehicle identifiers.")

    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(**DB_CONFIGS["mot"])
        cursor = conn.cursor()

        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()

            for plate in plates:
                result = query_vehicle(plate)

                if result.get("decision") != "OK — INSURED AND CLEAR":
                    reasons = result.get("flags") or [result.get("decision")]

                    for reason in reasons:
                        row = {
                            "vehicle_plate": plate,
                            "report_date": date.today(),
                            "flag_reason": reason,
                            "reported_by": "federated-integration-engine",
                        }
                        writer.writerow(row)
                        csv_file.flush()

                        write_to_mot_row(cursor, row)
                        conn.commit()
                        flag_count += 1

            print(f"{flag_count} flags written to {OUTPUT_CSV}")

        if flag_count:
            print("Report written to mot_db.mot_reports as rows are generated.")
        else:
            print("No flagged vehicles. Nothing inserted into mot_db.")

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    generate_ministry_report()
