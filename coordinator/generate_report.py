# """
# Generate a Ministry of Transport report using federated queries.

# No vehicle_master.pkl is used. Candidate vehicle identifiers are collected
# from the independent source systems, and every candidate is evaluated by the
# mediator at runtime.
# """

# import csv
# from datetime import date

# import mysql.connector

# from config import DB_CONFIGS
# from mediator import list_candidate_plates, query_vehicle


# OUTPUT_CSV = "ministry_report.csv"
# OUTPUT_COLUMNS = [
#     "vehicle_plate",
#     "report_date",
#     "flag_reason",
#     "reported_by",
# ]


# def write_to_mot_row(cursor, row: dict) -> None:
#     """Insert one flagged row into the Ministry database immediately."""
#     cursor.execute(
#         """
#         INSERT INTO mot_reports
#         (vehicle_plate, report_date, flag_reason, reported_by)
#         VALUES (%s, %s, %s, %s)
#         """,
#         (
#             row["vehicle_plate"],
#             row["report_date"],
#             row["flag_reason"],
#             row["reported_by"],
#         ),
#     )


# def generate_ministry_report() -> None:
#     plates = list_candidate_plates()
#     flag_count = 0

#     print(f"Found {len(plates)} candidate vehicle identifiers.")

#     conn = None
#     cursor = None

#     try:
#         conn = mysql.connector.connect(**DB_CONFIGS["mot"])
#         cursor = conn.cursor()

#         with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csv_file:
#             writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
#             writer.writeheader()

#             for plate in plates:
#                 result = query_vehicle(plate)

#                 if result.get("decision") != "OK — INSURED AND CLEAR":
#                     reasons = result.get("flags") or [result.get("decision")]

#                     for reason in reasons:
#                         row = {
#                             "vehicle_plate": plate,
#                             "report_date": date.today(),
#                             "flag_reason": reason,
#                             "reported_by": "federated-integration-engine",
#                         }
#                         writer.writerow(row)
#                         csv_file.flush()

#                         write_to_mot_row(cursor, row)
#                         conn.commit()
#                         flag_count += 1

#             print(f"{flag_count} flags written to {OUTPUT_CSV}")

#         if flag_count:
#             print("Report written to mot_db.mot_reports as rows are generated.")
#         else:
#             print("No flagged vehicles. Nothing inserted into mot_db.")

#     finally:
#         if cursor is not None:
#             cursor.close()
#         if conn is not None and conn.is_connected():
#             conn.close()


# if __name__ == "__main__":
#     generate_ministry_report()


"""
Nightly Ministry of Transport batch sweep.

This is the completeness half of the hybrid reporting strategy — it
covers every known candidate plate, including ones nobody has manually
searched through app.py (which reports in real time, see app.py +
reporting.py). Both paths go through reporting.report_flags(), which
never raises — if mot_db is unreachable it returns None instead of
crashing, so this loop can finish and report what it found even if the
Ministry database itself was briefly unavailable partway through.

Run this on a schedule (cron / Task Scheduler) rather than manually,
so uninsured/stolen vehicles get reported even if no one queries them
that day. See the scheduling notes at the bottom of this file.
"""

import csv
from datetime import date

from mediator import list_candidate_plates, query_vehicle
from reporting import report_flags


OUTPUT_CSV = "ministry_report.csv"
OUTPUT_COLUMNS = [
    "vehicle_plate",
    "report_date",
    "flag_reason",
    "reported_by",
]


def generate_ministry_report() -> None:
    plates = list_candidate_plates()
    flag_count = 0
    unreported_count = 0  # vehicles that were flagged but mot_db was down

    print(f"Found {len(plates)} candidate vehicle identifiers.")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for plate in plates:
            try:
                result = query_vehicle(plate)
            except Exception as exc:
                # query_vehicle() is already fault-tolerant internally,
                # but this outer guard means even a genuinely unexpected
                # error on one plate can't stop the whole batch.
                print(f"  skipping {plate}: unexpected error ({exc})")
                continue

            if not result.get("found"):
                continue
            if result.get("decision") == "OK — INSURED AND CLEAR":
                continue

            newly_written = report_flags(result, reported_by="batch-sweep")

            if newly_written is None:
                # mot_db was unreachable for this vehicle. Still record
                # it in the CSV (so nothing is silently lost) but don't
                # count it as reported to the database.
                unreported_count += 1
            else:
                flag_count += newly_written

            for reason in result.get("flags") or [result.get("decision")]:
                writer.writerow({
                    "vehicle_plate": result.get("plate"),
                    "report_date": date.today(),
                    "flag_reason": reason,
                    "reported_by": "batch-sweep",
                })
                csv_file.flush()

    print(f"{flag_count} new flag(s) written to mot_db.mot_reports.")
    print(f"All flags are also in {OUTPUT_CSV} regardless of mot_db availability.")

    if unreported_count:
        print(
            f"WARNING: {unreported_count} flagged vehicle(s) could not be "
            "written to mot_db (source was unavailable during the run). "
            "They are still present in the CSV — re-run this script once "
            "mot_db is back up to insert them."
        )


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