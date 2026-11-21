"""
Phase 3 — M5 (Theft & Shredding) database setup. Run ON M5, inside the TheftDB folder.

    python3 setup_theft.py all        # schema -> load -> fk -> verify
    python3 setup_theft.py schema     # step 1: tables + FK columns
    python3 setup_theft.py load       # step 2: insert generated CSV data
    python3 setup_theft.py fk         # step 3: FK constraints on theft_records
    python3 setup_theft.py grant      # SELECT on new tables for the API user
    python3 setup_theft.py verify     # evidence for Rubric 1 (also saved to evidence/)
    python3 setup_theft.py reset      # undo the DATA (keeps tables) to reload

Every step is safe to re-run. Connects as an admin user (default root; set
PHASE3_DB_USER / PHASE3_DB_PASSWORD in .env to avoid the password prompt).

Back up first:  mysqldump -u root -p --result-file=backup_theft.sql theft_db
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from p3_common import add_db_args, connect, none_if_blank, read_csv
from p3_setup import (column_exists, constraint_exists, fk_list, grant_select, orphan_report,
                      run_idempotent, scalar, statements, table_exists)

HERE = Path(__file__).resolve().parent
SCHEMA_SQL = HERE / "schema_theft.sql"
FK_SQL = HERE / "schema_theft_fk.sql"
HUB = "theft_records"
NEW_TABLES = ("police_stations", "firs", "recoveries", "shredding_certificates")
ALL_TABLES = (HUB,) + NEW_TABLES
BATCH = 1000


def step_schema(conn, args):
    cur = conn.cursor()
    db = args.database
    if not table_exists(cur, db, HUB):
        sys.exit(f"Table `{HUB}` not found — is this the theft database?")
    pk = scalar(cur, "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE "
                     "TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY'", (db, HUB))
    if pk != "id":
        sys.exit(f"{HUB} must have PRIMARY KEY (id); found {pk!r}. Fix that first.")
    id_type = scalar(cur, "SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE "
                          "TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME='id'", (db, HUB))
    id_sql_type = re.sub(r"\(\d+\)", "", str(id_type)).upper()
    print(f"{HUB}.id type: {id_type}  -> recoveries / shredding_certificates.theft_id use "
          f"{id_sql_type}")
    for stmt in statements(SCHEMA_SQL):
        if ("CREATE TABLE IF NOT EXISTS recoveries" in stmt
                or "CREATE TABLE IF NOT EXISTS shredding_certificates" in stmt) \
                and id_sql_type != "INT":
            stmt = re.sub(r"theft_id\s+INT\b", f"theft_id {id_sql_type}", stmt)
        print("  " + run_idempotent(cur, db, stmt))
    conn.commit()


def step_load(conn, args):
    data = Path(args.data)
    files = {n: data / f"{n}.csv" for n in ("police_stations", "firs", "theft_links",
                                            "recoveries", "shredding_certificates")}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        sys.exit("Missing generated files (run gen_theft.py first):\n  "
                 + "\n  ".join(missing))
    cur = conn.cursor()
    for table in NEW_TABLES:
        if not table_exists(cur, args.database, table):
            sys.exit(f"Table {table} does not exist — run the `schema` step first.")
        if scalar(cur, f"SELECT COUNT(*) FROM `{table}`"):
            sys.exit(f"Table {table} already has rows. Run `reset` first to reload.")

    def insert(table, columns, rows):
        sql = (f"INSERT INTO `{table}` ({', '.join(columns)}) "
               f"VALUES ({', '.join(['%s'] * len(columns))})")
        values = [tuple(none_if_blank(r.get(c)) for c in columns) for r in rows]
        for i in range(0, len(values), BATCH):
            cur.executemany(sql, values[i:i + BATCH])
        print(f"  {table:24s} {len(values):>7} rows")

    insert("police_stations", ["station_id", "station_code", "station_name", "city", "phone"],
           read_csv(files["police_stations"]))
    insert("firs", ["fir_id", "fir_no", "station_id", "filed_on", "complainant_name",
                    "complainant_phone"], read_csv(files["firs"]))

    links = read_csv(files["theft_links"])
    count = scalar(cur, f"SELECT COUNT(*) FROM `{HUB}`")
    if len(links) != count:
        print(f"  WARNING: {len(links)} links for {count} theft records — were records added "
              "after gen_theft.py ran? Unlinked records keep NULL FKs.")
    cur.execute("CREATE TEMPORARY TABLE tmp_theft_links (id BIGINT PRIMARY KEY, "
                "station_id INT, fir_id INT)")
    values = [(l["id"], none_if_blank(l["station_id"]), none_if_blank(l["fir_id"]))
              for l in links]
    for i in range(0, len(values), BATCH):
        cur.executemany("INSERT INTO tmp_theft_links VALUES (%s, %s, %s)", values[i:i + BATCH])
    cur.execute(f"UPDATE `{HUB}` t JOIN tmp_theft_links x ON x.id = t.id "
                "SET t.station_id = x.station_id, t.fir_id = x.fir_id")
    print(f"  {HUB + ' (FK links)':24s} {cur.rowcount:>7} rows updated")
    cur.execute("DROP TEMPORARY TABLE tmp_theft_links")

    insert("recoveries", ["recovery_id", "theft_id", "recovery_date", "location",
                          "vehicle_condition"], read_csv(files["recoveries"]))
    insert("shredding_certificates", ["cert_id", "theft_id", "scrap_yard", "shred_date",
                                      "certificate_no"], read_csv(files["shredding_certificates"]))
    conn.commit()


def step_fk(conn, args):
    cur = conn.cursor()
    for col, parent, pcol in (("station_id", "police_stations", "station_id"),
                              ("fir_id", "firs", "fir_id")):
        n = scalar(cur, f"SELECT COUNT(*) FROM `{HUB}` t LEFT JOIN `{parent}` x ON "
                        f"x.`{pcol}` = t.`{col}` WHERE t.`{col}` IS NOT NULL AND x.`{pcol}` IS NULL")
        if n:
            sys.exit(f"{n} {HUB}.{col} values point to a missing {parent} row — fix the data "
                     "before adding constraints.")
    for stmt in statements(FK_SQL):
        print("  " + run_idempotent(cur, args.database, stmt))
    conn.commit()


def step_grant(conn, args):
    if not args.api_user:
        sys.exit("Give --api-user (the MySQL user source_api.py connects as).")
    if args.api_user == "root":
        print("  source_api.py connects as root here: no grant needed.")
        return
    grant_select(conn.cursor(), args.database, NEW_TABLES, args.api_user)


def step_verify(conn, args):
    cur = conn.cursor()
    db = args.database
    lines = [f"Phase 3 verification — {db} — {datetime.now():%Y-%m-%d %H:%M}", ""]

    def out(text=""):
        print(text)
        lines.append(text)

    out("Tables (engine, rows):")
    for table in ALL_TABLES:
        if not table_exists(cur, db, table):
            out(f"  {table:24s} MISSING")
            continue
        engine = scalar(cur, "SELECT ENGINE FROM information_schema.TABLES WHERE "
                             "TABLE_SCHEMA=%s AND TABLE_NAME=%s", (db, table))
        out(f"  {table:24s} {engine:7s} {scalar(cur, f'SELECT COUNT(*) FROM `{table}`'):>8}")
    out("\nForeign keys (information_schema.KEY_COLUMN_USAGE):")
    fks = fk_list(cur, db)
    for child, col, parent, pcol, name in fks:
        out(f"  {name:18s} {child}.{col} -> {parent}.{pcol}")
    out(f"  total: {len(fks)}")
    out("\nOrphan checks (must all be 0):")
    lines.append(f"  total orphans: {orphan_report(cur, db)}")
    out("\nMulti-table JOIN (entity information distributed over 5 tables):")
    cur.execute(f"SELECT t.plate_no, t.status, t.theft_date, f.fir_no, f.complainant_name, "
                f"s.station_name, r.recovery_date, sc.certificate_no FROM `{HUB}` t "
                "JOIN firs f ON f.fir_id = t.fir_id "
                "JOIN police_stations s ON s.station_id = t.station_id "
                "LEFT JOIN recoveries r ON r.theft_id = t.id "
                "LEFT JOIN shredding_certificates sc ON sc.theft_id = t.id "
                "ORDER BY t.id LIMIT 6")
    for row in cur.fetchall():
        out("  " + " | ".join(str(x) for x in row))
    out("\nRecovered vehicles (theft_records -> recoveries):")
    cur.execute(f"SELECT t.plate_no, t.theft_date, r.recovery_date, r.location, "
                f"r.vehicle_condition FROM recoveries r JOIN `{HUB}` t ON t.id = r.theft_id "
                "ORDER BY r.recovery_id LIMIT 4")
    for row in cur.fetchall():
        out("  " + " | ".join(str(x) for x in row))
    path = HERE / "evidence" / "M5_theft_verify.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nsaved: {path}")


def step_reset(conn, args):
    if not args.yes and input("Delete all rows of the NEW tables and clear the theft FK "
                              "columns? (yes/no) ").strip().lower() != "yes":
        print("cancelled")
        return
    cur = conn.cursor()
    db = args.database
    for name in ("fk_theft_station", "fk_theft_fir"):
        if constraint_exists(cur, db, HUB, name):
            cur.execute(f"ALTER TABLE `{HUB}` DROP FOREIGN KEY {name}")
            print(f"  dropped constraint {name}")
    for table in ("recoveries", "shredding_certificates"):
        if table_exists(cur, db, table):
            cur.execute(f"DELETE FROM `{table}`")
    if column_exists(cur, db, HUB, "fir_id"):
        cur.execute(f"UPDATE `{HUB}` SET station_id = NULL, fir_id = NULL")
    for table in ("firs", "police_stations"):
        if table_exists(cur, db, table):
            cur.execute(f"DELETE FROM `{table}`")
    conn.commit()
    print("  data cleared; tables and columns kept. Run `load` then `fk` again.")


def main():
    ap = argparse.ArgumentParser(description="Phase 3 setup for theft_db (M5).")
    ap.add_argument("step", choices=["all", "schema", "load", "fk", "grant", "verify", "reset"])
    add_db_args(ap, "theft_db")
    ap.add_argument("--data", default=str(HERE / "data" / "M5_theft"))
    ap.add_argument("--api-user", default=None,
                    help="MySQL user of source_api.py (default SOURCE_DB_USER / COORDINATOR_USER)")
    ap.add_argument("--yes", action="store_true", help="no confirmation for reset")
    args = ap.parse_args()
    args.api_user = (args.api_user or os.getenv("SOURCE_DB_USER")
                     or os.getenv("COORDINATOR_USER") or os.getenv("MYSQL_USER"))

    conn = connect(args)
    try:
        steps = {"schema": [step_schema], "load": [step_load], "fk": [step_fk],
                 "grant": [step_grant], "verify": [step_verify], "reset": [step_reset],
                 "all": [step_schema, step_load, step_fk, step_verify]}[args.step]
        for step in steps:
            print(f"\n== {step.__name__.replace('step_', '')} ==")
            step(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
