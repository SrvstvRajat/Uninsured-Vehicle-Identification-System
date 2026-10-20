"""
Generate a Ministry of Transport report using federated queries.

No vehicle_master.pkl is used. Candidate vehicle identifiers are collected
from the independent source systems, and every candidate is evaluated by the
mediator at runtime.
"""

from datetime import date

import mysql.connector
import pandas as pd

from config import DB_CONFIGS
from mediator import list_candidate_plates, query_vehicle


OUTPUT_CSV = "ministry_report.csv"


def write_to_mot(report_df: pd.DataFrame) -> None:
    """Write the generated flags to the Ministry database."""
    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(**DB_CONFIGS["mot"])
        cursor = conn.cursor()

        for _, row in report_df.iterrows():
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

        conn.commit()

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None and conn.is_connected():
            conn.close()


def generate_ministry_report() -> None:
    plates = list_candidate_plates()
    flagged_rows = []

    print(f"Found {len(plates)} candidate vehicle identifiers.")

    for plate in plates:
        result = query_vehicle(plate)

        if result.get("decision") != "OK — INSURED AND CLEAR":
            reasons = result.get("flags") or [result.get("decision")]

            for reason in reasons:
                flagged_rows.append(
                    {
                        "vehicle_plate": plate,
                        "report_date": date.today(),
                        "flag_reason": reason,
                        "reported_by": "federated-integration-engine",
                    }
                )

    report_df = pd.DataFrame(
        flagged_rows,
        columns=[
            "vehicle_plate",
            "report_date",
            "flag_reason",
            "reported_by",
        ],
    )

    report_df.to_csv(OUTPUT_CSV, index=False)
    print(f"{len(report_df)} flags written to {OUTPUT_CSV}")

    if not report_df.empty:
        write_to_mot(report_df)
        print("Report written to mot_db.mot_reports")
    else:
        print("No flagged vehicles. Nothing inserted into mot_db.")


if __name__ == "__main__":
    generate_ministry_report()
