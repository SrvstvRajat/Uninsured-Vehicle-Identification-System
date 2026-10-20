"""
Import real CSV data into each source database, replacing the dummy
40-row fixtures created by generate_data.py.

Run this ONCE PER LAPTOP, on that laptop, pointing at its own CSV and
its own local MySQL server (same as generate_data.py did).

Usage:
    python3 import_real_data.py vehicles laptop1_vehicle_registration.csv
    python3 import_real_data.py insurance laptop2_insurance.csv
    python3 import_real_data.py rto laptop3_rto.csv
    python3 import_real_data.py theft laptop4_theft_shredding.csv

By default this TRUNCATEs the table first, so the old dummy rows are
wiped and only the real CSV data remains. Pass --keep to append instead.
"""

import argparse
import os
import sys

import mysql.connector
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

PASSWORD = os.getenv("MYSQL_ROOT_PASSWORD")

# source name -> (database, table, ordered columns to insert, date columns to clean)
SOURCES = {
    "vehicles": (
        "vehicle_registration_db",
        "vehicles",
        ["reg_plate", "make", "model", "color", "owner_name", "engine_no", "chassis_no"],
        [],
    ),
    "insurance": (
        "insurance_db",
        "insurance_policies",
        ["vehicle_number", "insurer_name", "policy_no", "policy_start_date",
         "policy_end_date", "premium_amount"],
        ["policy_start_date", "policy_end_date"],
    ),
    "rto": (
        "rto_db",
        "rto_records",
        ["car_id", "registration_date", "renewal_date", "rto_office"],
        ["registration_date", "renewal_date"],
    ),
    "theft": (
        "theft_db",
        "theft_records",
        ["plate_no", "theft_date", "status", "shredded_date"],
        ["theft_date", "shredded_date"],
    ),
}

CHUNK_SIZE = 5000


def import_source(source_name, csv_path, truncate=True, host="localhost"):
    database, table, columns, date_cols = SOURCES[source_name]

    df = pd.read_csv(csv_path)
    missing = [c for c in columns if c not in df.columns]
    if missing:
        sys.exit(f"CSV is missing expected column(s) for '{source_name}': {missing}")

    df = df[columns].copy()

    # Build rows checking each VALUE individually with pd.isna(), not a
    # DataFrame-wide .where(). On pandas' newer default "str" dtype, a
    # missing cell can still be an underlying float NaN even though the
    # column reports dtype "str" — a column-level .where()/.notna() check
    # can silently miss it and let a real NaN reach mysql.connector, which
    # rejects it. pd.isna() on a single scalar is reliable regardless of
    # the column's declared dtype (handles NaN, None, and NaT alike).
    rows = [
        tuple(None if pd.isna(v) else v for v in record)
        for record in df.itertuples(index=False, name=None)
    ]
    if not rows:
        print(f"{csv_path} has 0 data rows — nothing to import for '{source_name}'.")
        return

    conn = mysql.connector.connect(
        host=host, user="root", password=PASSWORD, database=database
    )
    cur = conn.cursor()

    if truncate:
        cur.execute(f"TRUNCATE TABLE {table}")
        print(f"Truncated {database}.{table} (old dummy rows removed).")

    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    inserted = 0
    for start in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[start:start + CHUNK_SIZE]
        cur.executemany(insert_sql, chunk)
        conn.commit()
        inserted += len(chunk)
        print(f"  {inserted}/{len(rows)} rows into {database}.{table}", end="\r")

    print(f"\nDone: {inserted} rows imported into {database}.{table}.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import real CSV data into a source database.")
    parser.add_argument("source", choices=SOURCES.keys(), help="Which source table to load")
    parser.add_argument("csv_path", help="Path to that source's CSV file")
    parser.add_argument("--keep", action="store_true",
                         help="Append instead of truncating existing dummy rows first")
    parser.add_argument("--host", default="localhost",
                         help="MySQL host (default: localhost, for local smoke testing)")
    args = parser.parse_args()

    import_source(args.source, args.csv_path, truncate=not args.keep, host=args.host)
