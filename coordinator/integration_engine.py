# import re
# from datetime import datetime
# import pandas as pd
# import mysql.connector

# from config import DB_CONFIGS, SOURCE_NAMES

# CACHE_FILE = "vehicle_master.pkl"


# def normalize_plate(raw):
#     """Convert source-specific plate formats to one canonical key."""
#     if pd.isna(raw):
#         return None
#     return re.sub(r"[\s\-]", "", str(raw).strip().upper())


# def fetch_table(source_name, query):
#     """Fetch one source table over the network."""
#     cfg = DB_CONFIGS[source_name]
#     conn = None
#     try:
#         conn = mysql.connector.connect(**cfg)
#         df = pd.read_sql(query, conn)
#         return df, None
#     except Exception as exc:
#         return pd.DataFrame(), str(exc)
#     finally:
#         if conn is not None and conn.is_connected():
#             conn.close()


# def build_vehicle_master():
#     """
#     Read the four vehicle-information sources, normalize their identifiers,
#     resolve entities using the canonical plate key, and merge them.

#     Laptop 5 is the Ministry output destination, so it is not read here.
#     """
#     queries = {
#         "vehicles": "SELECT * FROM vehicles",
#         "insurance": "SELECT * FROM insurance_policies",
#         "rto": "SELECT * FROM rto_records",
#         "theft": "SELECT * FROM theft_records",
#     }

#     fetched = {}
#     source_status = {}

#     for source_name, query in queries.items():
#         df, error = fetch_table(source_name, query)
#         fetched[source_name] = df
#         source_status[source_name] = {
#             "available": error is None,
#             "source": SOURCE_NAMES[source_name],
#             "error": error,
#             "checked_at": datetime.now().isoformat(timespec="seconds"),
#         }

#     vehicles = fetched["vehicles"]
#     if vehicles.empty:
#         raise RuntimeError(
#             "Vehicle Registration DB is unavailable or empty. "
#             "The Coordinator needs Laptop 1 as the anchor source."
#         )

#     vehicles = vehicles.copy()
#     vehicles["key"] = vehicles["reg_plate"].apply(normalize_plate)

#     insurance = fetched["insurance"].copy()
#     if not insurance.empty:
#         insurance["key"] = insurance["vehicle_number"].apply(normalize_plate)
#         insurance["policy_end_date"] = pd.to_datetime(
#             insurance["policy_end_date"], errors="coerce"
#         )
#         insurance = (
#             insurance.sort_values("policy_end_date")
#             .drop_duplicates("key", keep="last")
#         )

#     rto = fetched["rto"].copy()
#     if not rto.empty:
#         rto["key"] = rto["car_id"].apply(normalize_plate)
#         rto = rto.drop_duplicates("key", keep="last")

#     theft = fetched["theft"].copy()
#     if not theft.empty:
#         theft["key"] = theft["plate_no"].apply(normalize_plate)
#         theft = theft.drop_duplicates("key", keep="last")

#     master = vehicles.merge(
#         insurance, on="key", how="left", suffixes=("", "_insurance")
#     )
#     master = master.merge(
#         rto, on="key", how="left", suffixes=("", "_rto")
#     )
#     master = master.merge(
#         theft, on="key", how="left", suffixes=("", "_theft")
#     )

#     for source_name, status in source_status.items():
#         master[f"{source_name}_source_available"] = status["available"]

#     registration_keys = set(vehicles["key"].dropna())
#     rto_keys = set(rto["key"].dropna()) if not rto.empty else set()

#     master.attrs["rto_only_keys"] = sorted(rto_keys - registration_keys)
#     master.attrs["source_status"] = source_status
#     master.attrs["built_at"] = datetime.now().isoformat(timespec="seconds")

#     return master


# def save_master(master, path=CACHE_FILE):
#     master.to_pickle(path)


# if __name__ == "__main__":
#     master = build_vehicle_master()
#     save_master(master)

#     print("=" * 70)
#     print("INTEGRATED VEHICLE MASTER")
#     print("=" * 70)
#     print(f"Vehicles: {len(master)}")
#     print(f"Cache: {CACHE_FILE}")
#     print(f"Built: {master.attrs.get('built_at')}")

#     print("\nSource status:")
#     for source, status in master.attrs["source_status"].items():
#         state = "AVAILABLE" if status["available"] else "UNAVAILABLE"
#         print(f"  {SOURCE_NAMES[source]:35s} {state}")

#     print("\nRTO-only anomaly keys:")
#     print(master.attrs.get("rto_only_keys", []))

#     cols = ["key", "reg_plate", "make", "model", "policy_end_date", "status"]
#     print("\nSample:")
#     print(master[[c for c in cols if c in master.columns]].head(10).to_string(index=False))



import re
from datetime import datetime
import pandas as pd
import mysql.connector

from config import DB_CONFIGS, SOURCE_NAMES

CACHE_FILE = "vehicle_master.pkl"


def normalize_plate(raw):
    """Convert source-specific plate formats to one canonical key."""
    if pd.isna(raw):
        return None
    return re.sub(r"[\s\-]", "", str(raw).strip().upper())


def fetch_table(source_name, query):
    """Fetch one source table over the network."""
    cfg = DB_CONFIGS[source_name]
    conn = None
    try:
        conn = mysql.connector.connect(**cfg)
        df = pd.read_sql(query, conn)
        return df, None
    except Exception as exc:
        return pd.DataFrame(), str(exc)
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


def build_vehicle_master():
    """
    Read the four vehicle-information sources, normalize their identifiers,
    resolve entities using the canonical plate key, and merge them.

    Laptop 5 is the Ministry output destination, so it is not read here.
    """
    queries = {
        "vehicles": "SELECT * FROM vehicles",
        "insurance": "SELECT * FROM insurance_policies",
        "rto": "SELECT * FROM rto_records",
        "theft": "SELECT * FROM theft_records",
    }

    fetched = {}
    source_status = {}

    for source_name, query in queries.items():
        df, error = fetch_table(source_name, query)
        fetched[source_name] = df
        source_status[source_name] = {
            "available": error is None,
            "source": SOURCE_NAMES[source_name],
            "error": error,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }

    vehicles = fetched["vehicles"]
    if vehicles.empty:
        raise RuntimeError(
            "Vehicle Registration DB is unavailable or empty. "
            "The Coordinator needs Laptop 1 as the anchor source."
        )

    vehicles = vehicles.copy()
    vehicles["key"] = vehicles["reg_plate"].apply(normalize_plate)

    # --- insurance ---
    # NOTE: use "column present?" rather than "df.empty?" to decide whether
    # a source produced real data. A source that is down over the network
    # returns pd.DataFrame() with ZERO COLUMNS, so it has no "key" to merge
    # on. A source that is up but genuinely has no matching rows still has
    # its normal columns. Both cases are "empty", but only the second one
    # is safe to treat as "no data for this vehicle" vs. "unknown".
    insurance = fetched["insurance"].copy()
    if "vehicle_number" in insurance.columns:
        insurance["key"] = insurance["vehicle_number"].apply(normalize_plate)
        insurance["policy_end_date"] = pd.to_datetime(
            insurance["policy_end_date"], errors="coerce"
        )
        insurance = (
            insurance.sort_values("policy_end_date")
            .drop_duplicates("key", keep="last")
        )
    else:
        insurance["key"] = pd.Series(dtype=object)

    # --- rto ---
    rto = fetched["rto"].copy()
    if "car_id" in rto.columns:
        rto["key"] = rto["car_id"].apply(normalize_plate)
        rto = rto.drop_duplicates("key", keep="last")
    else:
        rto["key"] = pd.Series(dtype=object)

    # --- theft ---
    theft = fetched["theft"].copy()
    if "plate_no" in theft.columns:
        theft["key"] = theft["plate_no"].apply(normalize_plate)
        theft = theft.drop_duplicates("key", keep="last")
    else:
        theft["key"] = pd.Series(dtype=object)

    master = vehicles.merge(
        insurance, on="key", how="left", suffixes=("", "_insurance")
    )
    master = master.merge(
        rto, on="key", how="left", suffixes=("", "_rto")
    )
    master = master.merge(
        theft, on="key", how="left", suffixes=("", "_theft")
    )

    for source_name, status in source_status.items():
        master[f"{source_name}_source_available"] = status["available"]

    registration_keys = set(vehicles["key"].dropna())
    rto_keys = set(rto["key"].dropna()) if "key" in rto.columns else set()

    master.attrs["rto_only_keys"] = sorted(rto_keys - registration_keys)
    master.attrs["source_status"] = source_status
    master.attrs["built_at"] = datetime.now().isoformat(timespec="seconds")

    return master


def save_master(master, path=CACHE_FILE):
    master.to_pickle(path)


if __name__ == "__main__":
    master = build_vehicle_master()
    save_master(master)

    print("=" * 70)
    print("INTEGRATED VEHICLE MASTER")
    print("=" * 70)
    print(f"Vehicles: {len(master)}")
    print(f"Cache: {CACHE_FILE}")
    print(f"Built: {master.attrs.get('built_at')}")

    print("\nSource status:")
    for source, status in master.attrs["source_status"].items():
        state = "AVAILABLE" if status["available"] else "UNAVAILABLE"
        print(f"  {SOURCE_NAMES[source]:35s} {state}")

    print("\nRTO-only anomaly keys:")
    print(master.attrs.get("rto_only_keys", []))

    cols = ["key", "reg_plate", "make", "model", "policy_end_date", "status"]
    print("\nSample:")
    print(master[[c for c in cols if c in master.columns]].head(10).to_string(index=False))