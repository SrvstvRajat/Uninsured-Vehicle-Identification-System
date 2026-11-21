"""Shared helpers for the Phase 3 scripts (DB connection, CSV, normalisation)."""

from __future__ import annotations

import csv
import getpass
import os
import re
from pathlib import Path

try:                                     # same .env as source_api.py / the Phase 2 apps
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def add_db_args(parser, database: str):
    """Admin connection (needs CREATE / ALTER / INSERT rights, e.g. root)."""
    parser.add_argument("--host", default=os.getenv("SOURCE_DB_HOST")
                        or os.getenv("MYSQL_HOST") or "127.0.0.1")
    parser.add_argument("--port", type=int,
                        default=int(os.getenv("SOURCE_DB_PORT", os.getenv("DB_PORT", "3306"))))
    parser.add_argument("--user", default=os.getenv("PHASE3_DB_USER")
                        or os.getenv("MYSQL_USER") or "root",
                        help="admin user (PHASE3_DB_USER, else MYSQL_USER, else root)")
    parser.add_argument("--database", default=database)


def connect(args):
    import mysql.connector
    password = os.getenv("PHASE3_DB_PASSWORD")
    if password is None and args.user == (os.getenv("MYSQL_USER") or "root"):
        # laptops whose .env already holds the MySQL login (e.g. the insurance laptop)
        password = os.getenv("MYSQL_PASSWORD") or os.getenv("MYSQL_ROOT_PASSWORD")
    if password is None:
        password = getpass.getpass(f"MySQL password for {args.user}@{args.host}: ")
    return mysql.connector.connect(host=args.host, port=args.port, user=args.user,
                                   password=password, database=args.database,
                                   connection_timeout=10)


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def none_if_blank(value):
    return None if value is None or str(value).strip() == "" else value


def norm_plate(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def name_key(value) -> str:
    """'Sharma, Rajat' and 'rajat  sharma' -> 'rajat sharma' (word order ignored)."""
    return " ".join(sorted(re.findall(r"[a-z]+", str(value or "").casefold())))


def display_name(value) -> str:
    """'Sharma, Rajat' -> 'Rajat Sharma'; tidy spacing and capitals."""
    text = str(value or "").strip()
    if "," in text:
        last, first = [p.strip() for p in text.split(",", 1)]
        text = f"{first} {last}"
    return " ".join(w.capitalize() for w in text.split())
