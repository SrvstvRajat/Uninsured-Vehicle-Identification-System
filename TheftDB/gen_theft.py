"""
Phase 3 — M5 data generator: rows for the new theft tables (police_stations, firs,
recoveries, shredding_certificates) and the FK links of the existing `theft_records`.
Writes CSVs only; setup_theft.py loads them.

Reads the CURRENT `theft_records` table (so every id matches), or a CSV export,
plus M2's generated registration data (copy phase3/data/M2_registration from M2):

    python3 gen_theft.py                     # reads data/M2_registration/ next to this script

Cross-database consistency (what makes round-2 context discovery work):
  * firs          one FIR per theft. The complainant is the person who owned the car on
                  the theft date (M2 owners + ownership_transfers), with the same phone
                  as in M2 in 90% of cases and the name written differently in ~10%.
                  FIR number FIR/<station code>/<year>/<seq>, filed 0–2 days after the theft.
  * stations      police stations in the owners' cities (+ the NCR region); a theft is
                  registered at a station in the owner's city.
  * recoveries    every 'recovered' theft: 3–90 days later, 40% in another city.
  * shredding     every 'shredded' theft: scrap yard, shred date, certificate number.

Output (default data/M5_theft/ next to this script):
    police_stations.csv firs.csv theft_links.csv recoveries.csv shredding_certificates.csv
    theft_records.csv  <- full export incl. the new FK columns. Give this file to the
                          insurance laptop (gen_insurance.py --theft-csv) and the RTO laptop
                          (gen_rto.py --theft-csv) so their claims / challans match.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))     # project root (phase3 layout); HERE is already on the path
from p3_common import (add_db_args, connect, display_name, norm_plate, read_csv,  # noqa: E402
                       write_csv)

try:
    from fuzzy_match import fold_lookalikes
except ImportError:
    def fold_lookalikes(text):
        return text

STATION_AREAS = {
    "Delhi": ["Karol Bagh", "Lajpat Nagar", "Rohini", "Dwarka", "Saket", "Model Town",
              "Mayur Vihar", "Connaught Place"],
    "Ghaziabad": ["Kavi Nagar", "Indirapuram", "Vijay Nagar", "Sihani Gate"],
    "Noida": ["Sector 20", "Sector 39", "Sector 58"],
    "Gurugram": ["DLF Phase 1", "Sector 29", "Sohna Road"],
    "Faridabad": ["Sector 31", "NIT"],
    "Meerut": ["Civil Lines", "Partapur"], "Lucknow": ["Hazratganj", "Gomti Nagar"],
    "Mumbai": ["Andheri", "Bandra"], "Pune": ["Shivajinagar", "Kothrud"],
    "Bengaluru": ["Whitefield", "Indiranagar"], "Jaipur": ["Malviya Nagar", "Vaishali Nagar"],
    "Chandigarh": ["Sector 17", "Sector 34"],
}
REGION = ["Delhi", "Ghaziabad", "Noida", "Gurugram", "Faridabad"]
OTHER_CITIES = ["Meerut", "Alwar", "Panipat", "Sonipat", "Mathura", "Rohtak", "Bulandshahr"]
RECOVERY_SPOTS = ["near the railway station", "in an abandoned plot", "on the highway service road",
                  "in a multi-level parking", "behind a market", "near an industrial area"]
CONDITIONS = ["intact", "minor scratches", "damaged front bumper", "number plates removed",
              "stereo and battery missing", "partially stripped"]
SCRAP_YARDS = ["Mayapuri Scrap Yard", "Loni Auto Recyclers", "Mundka Vehicle Scrapping Centre",
               "Kundli Auto Dismantlers", "Sahibabad Scrap Market"]
FIRST = ["Rahul", "Priya", "Amit", "Neha", "Vikas", "Pooja", "Sanjay", "Anjali", "Rohit",
         "Kavita", "Manoj", "Sunita", "Deepak", "Ritu", "Arjun", "Meena"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Yadav", "Mehta", "Kumar", "Jain", "Agarwal",
        "Chauhan", "Malhotra", "Saxena"]


def load_thefts(args) -> list[dict]:
    if args.thefts_csv:
        rows = read_csv(args.thefts_csv)
    else:
        conn = connect(args)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, plate_no, theft_date, status, shredded_date "
                    "FROM theft_records ORDER BY id")
        rows = [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
                for r in cur.fetchall()]
        conn.close()
    if not rows:
        raise SystemExit("No theft records found.")
    return rows


def plate_key(value) -> str:
    return fold_lookalikes(norm_plate(value))


def as_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def noisy_name(name: str, rng: random.Random) -> str:
    parts = name.split()
    if len(parts) >= 2 and rng.random() < 0.5:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    if len(name) > 5:
        i = rng.randrange(1, len(name) - 1)
        if name[i] != " ":
            return name[:i] + name[i + 1:]
    return name


def main():
    ap = argparse.ArgumentParser(description="Generate Phase 3 theft data (M5).")
    add_db_args(ap, "theft_db")
    ap.add_argument("--thefts-csv", type=Path, help="use a CSV instead of MySQL")
    ap.add_argument("--registration", type=Path, default=HERE / "data" / "M2_registration",
                    help="M2's generated data folder (vehicles.csv, owners.csv, ...)")
    ap.add_argument("--out", type=Path, default=HERE / "data" / "M5_theft")
    ap.add_argument("--seed", type=int, default=45)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    today = date.today()

    thefts = load_thefts(args)
    print(f"theft records read: {len(thefts)}  "
          f"({', '.join(f'{k} {v}' for k, v in Counter(t['status'] for t in thefts).items())})")

    reg = args.registration
    if not (reg / "vehicles.csv").is_file() or not (reg / "owners.csv").is_file():
        raise SystemExit(f"M2 data not found in {reg}. Copy the registration laptop's "
                         "phase3/data/M2_registration/ files there (FIR complainants are the "
                         "registered owners).")
    vehicles = read_csv(reg / "vehicles.csv")
    owners = {o["owner_id"]: o for o in read_csv(reg / "owners.csv")}
    transfers = defaultdict(list)
    if (reg / "ownership_transfers.csv").is_file():
        for t in read_csv(reg / "ownership_transfers.csv"):
            transfers[t["vehicle_id"]].append(t)
    vehicle_by_key = {plate_key(v["reg_plate"]): v for v in vehicles}
    known_phones = {o["phone"] for o in owners.values()}

    def owner_at(vehicle: dict, when: date | None) -> str:
        chain = sorted(transfers.get(str(vehicle["id"]), []), key=lambda t: t["transfer_date"])
        if when is not None:
            for t in chain:
                if as_date(t["transfer_date"]) and when < as_date(t["transfer_date"]):
                    return t["from_owner_id"] or vehicle["owner_id"]
        return vehicle["owner_id"]

    phone_pool = iter(p for p in rng.sample(range(6_000_000_000, 9_999_999_999),
                                            len(thefts) * 3 + 300)
                      if str(p) not in known_phones)

    # ---- police stations ---------------------------------------------------------------
    owner_cities = {o["city"] for o in owners.values() if o.get("city")}
    cities = [c for c in STATION_AREAS if c in owner_cities or c in REGION]
    stations, stations_in = [], defaultdict(list)
    for city in cities:
        for n, area in enumerate(STATION_AREAS[city], 1):
            station_id = len(stations) + 1
            stations.append({"station_id": station_id,
                             "station_code": f"{city[:3].upper()}{n:02d}",
                             "station_name": f"{area} Police Station", "city": city,
                             "phone": str(next(phone_pool))})
            stations_in[city].append(station_id)
    station_by_id = {s["station_id"]: s for s in stations}

    # ---- FIRs + links ---------------------------------------------------------------------
    firs, links, recoveries, shredding = [], [], [], []
    seq_per_station_year = Counter()
    holder_stats = Counter()
    for t in sorted(thefts, key=lambda r: (str(r.get("theft_date") or ""), int(r["id"]))):
        theft_day = as_date(t.get("theft_date")) or (today - timedelta(days=rng.randint(30, 600)))
        vehicle = vehicle_by_key.get(plate_key(t.get("plate_no")))
        if vehicle is not None:
            owner = owners.get(owner_at(vehicle, theft_day), {})
            name = display_name(owner.get("full_name") or "Unknown Owner")
            if rng.random() < 0.10:
                name = noisy_name(name, rng)
            phone = owner.get("phone") or str(next(phone_pool))
            if rng.random() < 0.10:
                phone = str(next(phone_pool))
            city = owner.get("city") or rng.choice(REGION)
            holder_stats["complainant = registered owner"] += 1
        else:
            name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            phone = str(next(phone_pool))
            city = rng.choice(REGION)
            holder_stats["plate not registered (random complainant)"] += 1
        station_id = rng.choice(stations_in.get(city) or stations_in[REGION[0]])
        code = station_by_id[station_id]["station_code"]
        filed = min(theft_day + timedelta(days=rng.choice([0, 0, 1, 1, 2])), today)
        seq_per_station_year[(code, filed.year)] += 1
        fir_id = len(firs) + 1
        firs.append({"fir_id": fir_id,
                     "fir_no": f"FIR/{code}/{filed.year}/{seq_per_station_year[(code, filed.year)]:04d}",
                     "station_id": station_id, "filed_on": filed.isoformat(),
                     "complainant_name": name, "complainant_phone": phone})
        links.append({"id": t["id"], "station_id": station_id, "fir_id": fir_id})

        status = str(t.get("status") or "").lower()
        if status == "recovered":
            when = min(theft_day + timedelta(days=rng.randint(3, 90)), today)
            place = (f"{rng.choice(OTHER_CITIES)}, {rng.choice(RECOVERY_SPOTS)}"
                     if rng.random() < 0.4 else f"{city}, {rng.choice(RECOVERY_SPOTS)}")
            recoveries.append({"recovery_id": len(recoveries) + 1, "theft_id": t["id"],
                               "recovery_date": when.isoformat(), "location": place,
                               "vehicle_condition": rng.choice(CONDITIONS)})
        elif status == "shredded":
            shred = as_date(t.get("shredded_date")) or min(
                theft_day + timedelta(days=rng.randint(120, 400)), today)
            cert_id = len(shredding) + 1
            shredding.append({"cert_id": cert_id, "theft_id": t["id"],
                              "scrap_yard": rng.choice(SCRAP_YARDS),
                              "shred_date": shred.isoformat(),
                              "certificate_no": f"SHR{shred.year}{cert_id:05d}"})

    # ---- write ---------------------------------------------------------------------------------
    out = args.out
    write_csv(out / "police_stations.csv", stations,
              ["station_id", "station_code", "station_name", "city", "phone"])
    write_csv(out / "firs.csv", firs, ["fir_id", "fir_no", "station_id", "filed_on",
                                       "complainant_name", "complainant_phone"])
    write_csv(out / "theft_links.csv", links, ["id", "station_id", "fir_id"])
    write_csv(out / "recoveries.csv", recoveries,
              ["recovery_id", "theft_id", "recovery_date", "location", "vehicle_condition"])
    write_csv(out / "shredding_certificates.csv", shredding,
              ["cert_id", "theft_id", "scrap_yard", "shred_date", "certificate_no"])
    link_by_id = {str(l["id"]): l for l in links}
    export = [dict(t, station_id=link_by_id[str(t["id"])]["station_id"],
                   fir_id=link_by_id[str(t["id"])]["fir_id"]) for t in thefts]
    write_csv(out / "theft_records.csv", export,
              ["id", "plate_no", "theft_date", "status", "shredded_date", "station_id", "fir_id"])

    print(f"police_stations: {len(stations)}   firs: {len(firs)}   recoveries: {len(recoveries)}"
          f"   shredding_certificates: {len(shredding)}")
    print("complainants: " + ", ".join(f"{k} {v}" for k, v in holder_stats.items()))
    print(f"written to {out}/  (give {out / 'theft_records.csv'} to the insurance and RTO laptops)")


if __name__ == "__main__":
    main()
