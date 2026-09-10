import os
from datetime import date
import pandas as pd

from integration_engine import CACHE_FILE, build_vehicle_master, normalize_plate, save_master

TODAY = date.today()


def load_master(refresh=False):
    if refresh or not os.path.exists(CACHE_FILE):
        master = build_vehicle_master()
        save_master(master)
        return master
    return pd.read_pickle(CACHE_FILE)


def get_vehicle_status(plate_input, master=None):
    if not plate_input:
        return {
            "plate": plate_input,
            "found": False,
            "message": "Please provide a vehicle plate number.",
        }

    master = master if master is not None else load_master()
    key = normalize_plate(plate_input)
    rows = master[master["key"] == key]

    if rows.empty:
        return {
            "plate": plate_input,
            "found": False,
            "message": "No record found in the integrated vehicle master.",
        }

    row = rows.iloc[0]
    flags = []

    policy_end = row.get("policy_end_date")
    has_policy = pd.notna(policy_end)

    if not has_policy:
        flags.append("UNINSURED — no policy on record")
    elif pd.to_datetime(policy_end).date() < TODAY:
        flags.append(f"INSURANCE EXPIRED on {pd.to_datetime(policy_end).date()}")

    theft_status = row.get("status")
    if theft_status == "stolen":
        flags.append("VEHICLE FLAGGED: STOLEN")
    elif theft_status == "shredded":
        flags.append("VEHICLE FLAGGED: SHREDDED")

    source_warnings = []
    for source in ["vehicles", "insurance", "rto", "theft"]:
        col = f"{source}_source_available"
        if col in master.columns and not bool(row.get(col, False)):
            source_warnings.append(f"{source} source unavailable")

    if theft_status == "stolen":
        decision = "STOLEN"
    elif theft_status == "shredded":
        decision = "SCRAPPED/SHREDDED"
    elif not has_policy:
        decision = "UNINSURED"
    elif pd.to_datetime(policy_end).date() < TODAY:
        decision = "INSURANCE EXPIRED"
    elif source_warnings:
        decision = "INCONCLUSIVE — SOURCE UNAVAILABLE"
    else:
        decision = "OK — INSURED AND CLEAR"

    trust_score = 100
    trust_score -= 20 * len(source_warnings)
    if theft_status in {"stolen", "shredded"}:
        trust_score -= 5
    trust_score = max(0, min(100, trust_score))

    return {
        "plate": row.get("reg_plate"),
        "found": True,
        "vehicle_key": key,
        "make": row.get("make"),
        "model": row.get("model"),
        "color": row.get("color"),
        "owner": row.get("owner_name"),
        "registration_date": row.get("registration_date"),
        "insurer": row.get("insurer_name"),
        "policy_start_date": row.get("policy_start_date"),
        "policy_end_date": policy_end,
        "theft_status": theft_status,
        "decision": decision,
        "trust_score": trust_score,
        "source_warnings": source_warnings,
        "flags": flags,
    }


def print_result(result):
    print("\n" + "=" * 70)
    print("VEHICLE 360° PROFILE")
    print("=" * 70)

    if not result["found"]:
        print(f"Plate: {result['plate']}")
        print(result["message"])
        return

    fields = [
        ("Plate", result["plate"]),
        ("Vehicle Key", result["vehicle_key"]),
        ("Make", result["make"]),
        ("Model", result["model"]),
        ("Color", result["color"]),
        ("Owner", result["owner"]),
        ("Registration Date", result["registration_date"]),
        ("Insurer", result["insurer"]),
        ("Policy Start", result["policy_start_date"]),
        ("Policy End", result["policy_end_date"]),
        ("Theft Status", result["theft_status"]),
        ("Decision", result["decision"]),
        ("Trust Score", result["trust_score"]),
    ]

    for name, value in fields:
        print(f"{name:20s}: {value}")

    print("\nFlags:")
    for flag in result["flags"] or ["None"]:
        print(f"  - {flag}")

    if result["source_warnings"]:
        print("\nSource warnings:")
        for warning in result["source_warnings"]:
            print(f"  - {warning}")


if __name__ == "__main__":
    print("Uninsured Vehicle Lookup")
    print("Type a plate number, 'refresh', or 'quit'.")

    master = load_master()

    while True:
        q = input("\nEnter plate number: ").strip()

        if q.lower() == "quit":
            break

        if q.lower() == "refresh":
            master = load_master(refresh=True)
            print("Integrated master refreshed from remote databases.")
            continue

        print_result(get_vehicle_status(q, master))
