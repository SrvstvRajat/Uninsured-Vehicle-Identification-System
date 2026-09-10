from datetime import date
import pandas as pd
import mysql.connector

from config import DB_CONFIGS
from query_tool import get_vehicle_status, load_master

OUTPUT_CSV = "ministry_report.csv"


def generate_ministry_report():
    master = load_master()
    flagged_rows = []

    for plate in master["reg_plate"].dropna().unique():
        result = get_vehicle_status(plate, master)

        if result["decision"] != "OK — INSURED AND CLEAR":
            reasons = result["flags"] or [result["decision"]]

            for reason in reasons:
                flagged_rows.append({
                    "vehicle_plate": plate,
                    "report_date": date.today(),
                    "flag_reason": reason,
                    "reported_by": "automated-integration-engine",
                })

    report_df = pd.DataFrame(
        flagged_rows,
        columns=["vehicle_plate", "report_date", "flag_reason", "reported_by"]
    )

    report_df.to_csv(OUTPUT_CSV, index=False)
    print(f"{len(report_df)} flags written to {OUTPUT_CSV}")

    # Laptop 5 is the Ministry output DB.
    conn = mysql.connector.connect(**DB_CONFIGS["mot"])
    cur = conn.cursor()

    for _, row in report_df.iterrows():
        cur.execute(
            """
            INSERT INTO mot_reports
            (vehicle_plate, report_date, flag_reason, reported_by)
            VALUES (%s,%s,%s,%s)
            """,
            (
                row["vehicle_plate"],
                row["report_date"],
                row["flag_reason"],
                row["reported_by"],
            )
        )

    conn.commit()
    cur.close()
    conn.close()

    print("Report written to Laptop 5: mot_db.mot_reports")


if __name__ == "__main__":
    generate_ministry_report()
