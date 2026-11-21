"""
Shared, re-runnable DDL helpers for the Phase 3 setup scripts (M3, M4, M5).
Every statement is checked against information_schema first, so running a setup
step twice never fails: existing tables, columns, indexes and constraints are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

def statements(path: Path) -> list[str]:
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.strip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


def scalar(cur, sql, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def table_exists(cur, db, table):
    return bool(scalar(cur, "SELECT COUNT(*) FROM information_schema.TABLES "
                            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (db, table)))


def column_exists(cur, db, table, column):
    return bool(scalar(cur, "SELECT COUNT(*) FROM information_schema.COLUMNS WHERE "
                            "TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                       (db, table, column)))


def index_exists(cur, db, table, index):
    return bool(scalar(cur, "SELECT COUNT(*) FROM information_schema.STATISTICS WHERE "
                            "TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s",
                       (db, table, index)))


def constraint_exists(cur, db, table, name):
    return bool(scalar(cur, "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME=%s",
                       (db, table, name)))


def run_idempotent(cur, db, stmt) -> str:
    """Execute one DDL statement unless what it creates already exists."""
    flat = " ".join(stmt.split())
    m = re.match(r"ALTER TABLE (\w+) ENGINE=(\w+)", flat, re.I)
    if m:
        engine = scalar(cur, "SELECT ENGINE FROM information_schema.TABLES WHERE "
                             "TABLE_SCHEMA=%s AND TABLE_NAME=%s", (db, m.group(1)))
        if str(engine).lower() == m.group(2).lower():
            return f"skip  {m.group(1)} already {engine}"
        cur.execute(stmt)
        return f"done  {m.group(1)}: {engine} -> {m.group(2)}"
    m = re.match(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", flat, re.I)
    if m:
        if column_exists(cur, db, m.group(1), m.group(2)):
            return f"skip  column {m.group(1)}.{m.group(2)} exists"
        cur.execute(stmt)
        return f"done  column {m.group(1)}.{m.group(2)} added"
    m = re.match(r"ALTER TABLE (\w+) ADD INDEX (\w+)", flat, re.I)
    if m:
        if index_exists(cur, db, m.group(1), m.group(2)):
            return f"skip  index {m.group(2)} exists"
        cur.execute(stmt)
        return f"done  index {m.group(2)} added"
    m = re.match(r"ALTER TABLE (\w+) ADD CONSTRAINT (\w+)", flat, re.I)
    if m:
        if constraint_exists(cur, db, m.group(1), m.group(2)):
            return f"skip  constraint {m.group(2)} exists"
        cur.execute(stmt)
        return f"done  constraint {m.group(2)} added"
    m = re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", flat, re.I)
    if m:
        existed = table_exists(cur, db, m.group(1))
        cur.execute(stmt)
        return f"{'skip ' if existed else 'done '} table {m.group(1)}" + (
            " exists" if existed else " created")
    cur.execute(stmt)
    return f"done  {flat[:60]}"


def fk_list(cur, db):
    cur.execute("SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, "
                "CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s "
                "AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY TABLE_NAME, COLUMN_NAME", (db,))
    return cur.fetchall()


def orphan_report(cur, db):
    problems = 0
    for child, col, parent, pcol, _name in fk_list(cur, db):
        n = scalar(cur, f"SELECT COUNT(*) FROM `{child}` c LEFT JOIN `{parent}` p "
                        f"ON p.`{pcol}` = c.`{col}` WHERE c.`{col}` IS NOT NULL AND p.`{pcol}` IS NULL")
        problems += n
        print(f"  orphans {child}.{col} -> {parent}.{pcol}: {n}")
    return problems




def grant_select(cur, database, tables, user):
    """GRANT SELECT on `tables` to every host entry of `user`; prints SQL if not allowed."""
    import mysql.connector
    cur.execute("SELECT Host FROM mysql.user WHERE User=%s", (user,))
    hosts = [h for (h,) in cur.fetchall()]
    if not hosts:
        raise SystemExit(f"MySQL user {user!r} not found (the user source_api.py connects as).")
    for host in hosts:
        try:
            for table in tables:
                cur.execute(f"GRANT SELECT ON `{database}`.`{table}` TO %s@%s", (user, host))
        except mysql.connector.Error as exc:
            print(f"  could not grant ({exc.msg}). Run as root instead:")
            for t in tables:
                print(f"    GRANT SELECT ON {database}.{t} TO '{user}'@'{host}';")
            return
        print(f"  SELECT on {', '.join(tables)} granted to '{user}'@'{host}'")
