"""
Federated Vehicle Integration - Mediator

Architecture:
    User Query
        |
        v
    Mediator
        |
        +--> Vehicle Registration DB
        +--> Insurance DB
        +--> RTO DB
        +--> Theft DB
        |
        v
    Runtime integration -> Vehicle 360° -> Decision

Unlike the previous materialized implementation, this module does NOT
build or read vehicle_master.pkl. Data stays in the source databases and
is fetched when a vehicle is queried.
"""

import re
from datetime import datetime
from typing import Any

import mysql.connector

from config import DB_CONFIGS, SOURCE_NAMES


SOURCE_QUERIES = {
    "vehicles": {
        "table": "vehicles",
        "key_column": "reg_plate",
        "columns": "*",
    },
    "insurance": {
        "table": "insurance_policies",
        "key_column": "vehicle_number",
        "columns": "*",
        "order_by": "policy_end_date DESC",
    },
    "rto": {
        "table": "rto_records",
        "key_column": "car_id",
        "columns": "*",
        "order_by": "registration_date DESC",
    },
    "theft": {
        "table": "theft_records",
        "key_column": "plate_no",
        "columns": "*",
        "order_by": "theft_date DESC",
    },
}


def normalize_plate(raw: Any) -> str | None:
    """Convert source-specific plate formats to one canonical key."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return re.sub(r"[\s\-]", "", value).upper()


def _normalized_sql(column: str) -> str:
    """
    MySQL expression used for query-time identifier resolution.

    Examples:
        DL01AB1004
        DL 01 AB 1004
        DL-01-AB-1004

    all match the same canonical key.
    """
    return (
        f"REPLACE(REPLACE(UPPER(COALESCE({column}, '')), ' ', ''), '-', '')"
    )


def fetch_one(source_name: str, plate_key: str) -> tuple[dict | None, dict]:
    """
    Query exactly one source for one canonical vehicle key.

    Returns:
        (record, source_metadata)
    """
    spec = SOURCE_QUERIES[source_name]
    cfg = DB_CONFIGS[source_name]

    sql = (
        f"SELECT {spec['columns']} "
        f"FROM {spec['table']} "
        f"WHERE {_normalized_sql(spec['key_column'])} = %s"
    )

    if spec.get("order_by"):
        sql += f" ORDER BY {spec['order_by']}"

    sql += " LIMIT 1"

    conn = None
    checked_at = datetime.now().isoformat(timespec="seconds")

    try:
        conn = mysql.connector.connect(**cfg)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (plate_key,))
        record = cursor.fetchone()
        cursor.close()

        return record, {
            "available": True,
            "source": SOURCE_NAMES[source_name],
            "checked_at": checked_at,
            "error": None,
            "record_found": record is not None,
        }

    except Exception as exc:
        return None, {
            "available": False,
            "source": SOURCE_NAMES[source_name],
            "checked_at": checked_at,
            "error": str(exc),
            "record_found": False,
        }

    finally:
        if conn is not None and conn.is_connected():
            conn.close()


def query_vehicle(plate_input: str) -> dict:
    """
    Federated Vehicle 360 query.

    The mediator sends the same logical vehicle key to all independent
    source databases, receives source-specific records, resolves the
    different identifier names at the integration layer, and creates
    one virtual result.

    No integrated master is persisted.
    """
    key = normalize_plate(plate_input)

    if key is None:
        return {
            "plate": plate_input,
            "found": False,
            "message": "Please provide a vehicle plate number.",
        }

    records = {}
    source_status = {}

    # Runtime federation: query each autonomous source independently.
    for source_name in ("vehicles", "insurance", "rto", "theft"):
        record, status = fetch_one(source_name, key)
        records[source_name] = record
        source_status[source_name] = status

    vehicle = records["vehicles"]
    insurance = records["insurance"]
    rto = records["rto"]
    theft = records["theft"]

    any_record = any(record is not None for record in records.values())

    if not any_record:
        unavailable = [
            name for name, status in source_status.items()
            if not status["available"]
        ]

        if unavailable:
            return {
                "plate": plate_input,
                "vehicle_key": key,
                "found": False,
                "message": (
                    "No vehicle record could be constructed because the "
                    f"following source(s) are unavailable: {', '.join(unavailable)}."
                ),
                "source_status": source_status,
            }

        return {
            "plate": plate_input,
            "vehicle_key": key,
            "found": False,
            "message": "No record found in the federated source databases.",
            "source_status": source_status,
        }

    flags = []
    source_warnings = [
        f"{name} source unavailable"
        for name, status in source_status.items()
        if not status["available"]
    ]

    # Insurance decision is only made when the insurance source answered.
    insurance_available = source_status["insurance"]["available"]
    has_policy = insurance is not None
    policy_end = insurance.get("policy_end_date") if insurance else None

    is_expired = False
    if insurance_available and policy_end:
        try:
            is_expired = (
                __import__("pandas").to_datetime(policy_end).date()
                < __import__("datetime").date.today()
            )
        except Exception:
            flags.append("INSURANCE DATE COULD NOT BE VERIFIED")

    if insurance_available:
        if not has_policy:
            flags.append("UNINSURED — no policy on record")
        elif is_expired:
            flags.append(
                f"INSURANCE EXPIRED on "
                f"{__import__('pandas').to_datetime(policy_end).date()}"
            )

    theft_status = theft.get("status") if theft else None

    if source_status["theft"]["available"]:
        if theft_status == "stolen":
            flags.append("VEHICLE FLAGGED: STOLEN")
        elif theft_status == "shredded":
            flags.append("VEHICLE FLAGGED: SHREDDED")

    # Registration anomaly: RTO knows the vehicle but the main registration
    # source does not.
    if vehicle is None and rto is not None:
        flags.append(
            "DATA QUALITY ANOMALY — RTO record exists but "
            "vehicle registration record is missing"
        )

    # Decision priority: safety-critical flags first, then insurance,
    # then source uncertainty.
    if theft_status == "stolen":
        decision = "STOLEN"
    elif theft_status == "shredded":
        decision = "SCRAPPED/SHREDDED"
    elif insurance_available and not has_policy:
        decision = "UNINSURED"
    elif insurance_available and is_expired:
        decision = "INSURANCE EXPIRED"
    elif not source_status["vehicles"]["available"]:
        decision = "INCONCLUSIVE — VEHICLE SOURCE UNAVAILABLE"
    elif source_warnings:
        decision = "INCONCLUSIVE — SOURCE UNAVAILABLE"
    elif vehicle is None:
        decision = "DATA QUALITY ANOMALY"
    else:
        decision = "OK — INSURED AND CLEAR"

    trust_score = 100 - (20 * len(source_warnings))

    if theft_status in {"stolen", "shredded"}:
        trust_score -= 5

    if vehicle is None and rto is not None:
        trust_score -= 15

    trust_score = max(0, min(100, trust_score))

    # Resolve the final Vehicle 360 view from the source records.
    plate = (
        vehicle.get("reg_plate") if vehicle
        else rto.get("car_id") if rto
        else insurance.get("vehicle_number") if insurance
        else theft.get("plate_no") if theft
        else plate_input
    )

    return {
        "plate": plate,
        "found": True,
        "vehicle_key": key,

        # Vehicle registration / description
        "make": vehicle.get("make") if vehicle else None,
        "model": vehicle.get("model") if vehicle else None,
        "color": vehicle.get("color") if vehicle else None,
        "owner": vehicle.get("owner_name") if vehicle else None,
        "engine_no": vehicle.get("engine_no") if vehicle else None,
        "chassis_no": vehicle.get("chassis_no") if vehicle else None,

        # RTO
        "registration_date": rto.get("registration_date") if rto else None,
        "renewal_date": rto.get("renewal_date") if rto else None,
        "rto_office": rto.get("rto_office") if rto else None,

        # Insurance
        "insurer": insurance.get("insurer_name") if insurance else None,
        "policy_no": insurance.get("policy_no") if insurance else None,
        "policy_start_date": (
            insurance.get("policy_start_date") if insurance else None
        ),
        "policy_end_date": policy_end,

        # Theft / shredding
        "theft_date": theft.get("theft_date") if theft else None,
        "theft_status": theft_status,
        "shredded_date": theft.get("shredded_date") if theft else None,

        # Decision / evidence
        "decision": decision,
        "trust_score": trust_score,
        "source_warnings": source_warnings,
        "flags": flags,
        "source_status": source_status,
        "integration_mode": "MEDIATION / FEDERATED VIRTUAL INTEGRATION",
        "queried_at": datetime.now().isoformat(timespec="seconds"),
    }


def list_candidate_plates() -> list[str]:
    """
    Discover plates for batch reporting.

    This is NOT a master-building operation. It only retrieves candidate
    identifiers from source systems; each vehicle is then queried live
    through query_vehicle().
    """
    candidates = set()

    for source_name in ("vehicles", "rto", "insurance", "theft"):
        spec = SOURCE_QUERIES[source_name]
        cfg = DB_CONFIGS[source_name]

        sql = f"SELECT {spec['key_column']} FROM {spec['table']}"

        conn = None
        try:
            conn = mysql.connector.connect(**cfg)
            cursor = conn.cursor()
            cursor.execute(sql)

            for (raw_plate,) in cursor.fetchall():
                key = normalize_plate(raw_plate)
                if key:
                    candidates.add(key)

            cursor.close()

        except Exception:
            # Batch reporting can continue with the sources that are
            # available; individual vehicle queries still expose source
            # availability in their result.
            continue

        finally:
            if conn is not None and conn.is_connected():
                conn.close()

    return sorted(candidates)


if __name__ == "__main__":
    print("=" * 70)
    print("FEDERATED VEHICLE MEDIATOR")
    print("=" * 70)
    plate = input("Enter vehicle plate: ").strip()
    result = query_vehicle(plate)

    for key, value in result.items():
        if key != "source_status":
            print(f"{key:20s}: {value}")

    print("\nSource status:")
    for source, status in result.get("source_status", {}).items():
        state = "AVAILABLE" if status["available"] else "UNAVAILABLE"
        print(f"  {source:12s}: {state}")
