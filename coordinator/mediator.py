"""
Federated Vehicle Integration - Mediator

Architecture:
    User Query (noisy / OCR plate, optional details)
        |
        v
    Mediator ----- POST /api/similar ----> Vehicle Registration API  \\
        |    ----- POST /api/similar ----> Insurance API              |  SIMILARITY
        |    ----- POST /api/similar ----> RTO API                    |  MATCHING
        |    ----- POST /api/similar ----> Theft API                 /   (on each source)
        v
    ENTITY MATCHING (detail_match.py): which records across the four
    sources are the same vehicle?
        |
        v
    Vehicle 360 -> Decision

Similarity matching runs on each source laptop, next to its data; only the
best candidates (with scores and their rows) travel to the Coordinator. The
Coordinator links those records into vehicles and decides.

The Coordinator opens NO MySQL connection to the source laptops: every call
goes through source_client.py (the sources' REST APIs). No vehicle master is
built or stored; everything is fetched per request and discarded.
"""

from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Optional

import detail_match
from config import SOURCE_NAMES
from detail_match import (best_anchor, build_entities, decide, rank_entities,
                          symmetric_plate_score)
from fuzzy_match import fold_lookalikes
from source_client import (api_query_dicts, health, plate_column,
                           similar)

SOURCES = ("vehicles", "insurance", "rto", "theft")
CANDIDATES_PER_SOURCE = 10     # similar plates asked from each source
MAX_QUERY_VARIANTS = 6         # corrected readings sent per lookup
DETAIL_SEED_FIELDS = (         # identifiers that can find a vehicle without a plate
    ("vehicles", "chassis_no"), ("vehicles", "engine_no"),
    ("insurance", "policy_no"), ("vehicles", "owner_name"),
)
FUZZY_LINK_TRUST_PENALTY = 10  # per record linked by similarity, not exact plate
MAX_CONTEXT_LOOKUPS = 20       # registered-plate neighbourhoods fetched per lookup


def normalize_plate(raw: Any) -> Optional[str]:
    """Convert source-specific plate formats to one canonical key."""
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    return re.sub(r"[\s\-]", "", value).upper()


def _status(source: str, available: bool, error: Optional[str],
            record_found: bool = False, checked_at: Optional[str] = None) -> dict:
    return {
        "available": available,
        "source": SOURCE_NAMES.get(source, source),
        "checked_at": checked_at or datetime.now().isoformat(timespec="seconds"),
        "error": error,
        "record_found": record_found,
    }


def check_source_status() -> dict:
    """Database reachability of each source, via its REST API /api/health."""
    def check_one(source):
        result = health(source)
        if not result["available"]:
            print(f"[mediator] {source} health check failed: {result['error']}")
        return _status(source, result["available"], result["error"],
                       checked_at=result["checked_at"])

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        return dict(zip(SOURCES, pool.map(check_one, SOURCES)))


# --------------------------------------------------------------------------
# Similarity matching: ask every source, in parallel
# --------------------------------------------------------------------------
def _as_keys(queries) -> list[str]:
    queries = [queries] if isinstance(queries, str) else list(queries or [])
    keys = []
    for query in queries:
        key = normalize_plate(query)
        if key and key not in keys:
            keys.append(key)
    return keys[:MAX_QUERY_VARIANTS]


def find_candidates(queries, limit: int = CANDIDATES_PER_SOURCE):
    """Send the plate (and its corrected variants) to every source's /api/similar.

    Returns (per_source, source_status):
        per_source[source] = {"available", "error", "matches": [...]}
    where each stored value keeps its best score over all variants.
    """
    keys = _as_keys(queries)
    jobs = [(source, key) for source in SOURCES for key in keys]

    def run(job):
        source, key = job
        try:
            return source, similar(source, plate_column(source), key,
                                   limit=limit, with_rows=True), None
        except Exception as exc:
            return source, None, str(exc)

    merged = {s: {"available": False, "error": None, "matches": {}, "via": None}
              for s in SOURCES}
    if jobs:
        with ThreadPoolExecutor(max_workers=min(len(jobs), 16)) as pool:
            for source, data, error in pool.map(run, jobs):
                slot = merged[source]
                if data is None:
                    slot["error"] = slot["error"] or error
                    continue
                slot["available"] = True
                slot["via"] = data.get("via")
                for match in data.get("matches") or []:
                    prev = slot["matches"].get(match["value"])
                    if prev is None or match["score"] > prev["score"]:
                        slot["matches"][match["value"]] = match

    per_source, source_status = {}, {}
    for source, slot in merged.items():
        matches = sorted(slot["matches"].values(), key=lambda m: -m["score"])
        available = slot["available"] or not keys
        per_source[source] = {"available": available,
                              "error": None if available else slot["error"],
                              "matches": matches, "via": slot["via"]}
        source_status[source] = _status(source, available,
                                        None if available else slot["error"],
                                        record_found=bool(matches))
    if keys:
        _add_registered_neighbours(per_source, keys)
    return per_source, source_status


def _add_registered_neighbours(per_source: dict, keys: list[str]) -> None:
    """Make sure every record can be linked to ITS OWN registered vehicle.

    A source with no exact hit returns its nearest plates, which may belong to
    a different registered vehicle than the one asked for (asking for
    UP09AI8815 can return the theft record of UP09AI8845). Before entity
    matching links such a record, ask the registration source which registered
    plates are near the record's plate, so the record is linked to its closest
    registered vehicle, never just to whatever was asked.
    """
    vehicles = per_source.get("vehicles")
    if not vehicles or not vehicles["available"]:
        return
    registered = {normalize_plate(m["value"]) for m in vehicles["matches"]}
    orphans = []
    for source, result in per_source.items():
        if source == "vehicles":
            continue
        for match in result["matches"]:
            key = normalize_plate(match["value"])
            if key and key not in registered and key not in orphans:
                orphans.append(key)
    orphans = orphans[:MAX_CONTEXT_LOOKUPS]
    if not orphans:
        return

    def lookup(key):
        try:
            return similar("vehicles", plate_column("vehicles"), key,
                           limit=5, with_rows=True)
        except Exception as exc:
            print(f"[mediator] registered-neighbour lookup for {key} failed: {exc}")
            return None

    known = {m["value"] for m in vehicles["matches"]}
    with ThreadPoolExecutor(max_workers=min(len(orphans), 8)) as pool:
        for data in pool.map(lookup, orphans):
            for match in (data or {}).get("matches") or []:
                if match["value"] in known:
                    continue
                known.add(match["value"])
                # Score against what was actually asked, not the orphan plate.
                score = max(symmetric_plate_score(key, normalize_plate(match["value"]))
                            for key in keys)
                vehicles["matches"].append(dict(match, score=round(score, 4)))


def _seed_plates_from_details(details: dict) -> list[str]:
    """No plate typed: find candidate plates through identifier similarity."""
    seeds = []
    for source, column in DETAIL_SEED_FIELDS:
        value = (details or {}).get(column)
        if not value:
            continue
        try:
            data = similar(source, column, value, limit=5, with_rows=True)
        except Exception as exc:
            print(f"[mediator] seed lookup {source}.{column} failed: {exc}")
            continue
        for match in data.get("matches") or []:
            for row in match.get("rows") or []:
                key = normalize_plate(row.get(plate_column(source)))
                if key and key not in seeds:
                    seeds.append(key)
    return seeds[:MAX_QUERY_VARIANTS]


# --------------------------------------------------------------------------
# Entity matching + ranking (used by the lookup / scan pages)
# --------------------------------------------------------------------------
def identify(queries, details: Optional[dict] = None, limit: int = 5) -> dict:
    """Similarity on the sources, entity matching here, then a decision.

    Returns {"candidates", "best", "auto", "reason", "used_details",
             "source_status"}. Candidates keep the UI's item shape
    (plate, score, plate_score, fields, row) plus sources/links.
    """
    details = {k: v for k, v in (details or {}).items() if v}
    keys = _as_keys(queries)
    has_plate = bool(keys)
    if not has_plate and details:
        keys = _seed_plates_from_details(details)
    if not keys:
        return {"candidates": [], "best": None, "auto": False,
                "reason": "Give a plate, or a chassis / engine / policy number "
                          "or owner name to search by.",
                "used_details": bool(details), "source_status": {}}

    per_source, source_status = find_candidates(keys)
    available = {s for s, st in source_status.items() if st["available"]}
    entities = build_entities(per_source)
    ranked = rank_entities(entities, details, available,
                           has_plate=has_plate, limit=limit)
    best, auto, reason = decide(ranked, used_details=bool(details))
    return {"candidates": ranked, "best": best, "auto": auto, "reason": reason,
            "used_details": bool(details), "source_status": source_status}


def similar_plates(queries, limit: int = 5) -> list[dict]:
    """Registered-plate suggestions for a noisy plate (cleaning workbench)."""
    per_source, _ = find_candidates(queries, limit=limit)
    best = {}
    for result in per_source.values():
        for match in result["matches"]:
            key = normalize_plate(match["value"])
            if key and match["score"] > best.get(key, -1):
                best[key] = match["score"]
    return [{"value": k, "score": s}
            for k, s in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]]


def similar_field_values(column: str, value: str, limit: int = 5) -> list[dict]:
    """Similar registration-DB values for one field (cleaning workbench)."""
    data = similar("vehicles", column, value, limit=limit)
    return [{"value": m["value"], "score": m["score"]} for m in data.get("matches") or []]


# --------------------------------------------------------------------------
# Vehicle 360 for one plate
# --------------------------------------------------------------------------
def _to_date(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def build_result(plate_input: str, entity: dict, source_status: dict) -> dict:
    """Integrate one resolved entity into the Vehicle 360 view + decision."""
    records = entity["records"]
    vehicle = records.get("vehicles")
    insurance = records.get("insurance")
    rto = records.get("rto")
    theft = records.get("theft")
    source_status = {
        s: dict(st, record_found=s in records) for s, st in source_status.items()
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
    policy_end_date = None
    if insurance_available and policy_end:
        try:
            policy_end_date = _to_date(policy_end)
            is_expired = policy_end_date < date.today()
        except (TypeError, ValueError):
            flags.append("INSURANCE DATE COULD NOT BE VERIFIED")

    if insurance_available:
        if not has_policy:
            flags.append("UNINSURED — no policy on record")
        elif is_expired:
            flags.append(f"INSURANCE EXPIRED on {policy_end_date}")
    else:
        flags.append("INSURANCE DATA COULD NOT BE VERIFIED — source unavailable")

    theft_status = theft.get("status") if theft else None

    if source_status["theft"]["available"]:
        if theft_status == "stolen":
            flags.append("VEHICLE FLAGGED: STOLEN")
        elif theft_status == "shredded":
            flags.append("VEHICLE FLAGGED: SHREDDED")
    else:
        flags.append("THEFT/SHREDDING DATA COULD NOT BE VERIFIED — source unavailable")

    # Vehicle-source unavailable takes priority over "anomaly".
    if not source_status["vehicles"]["available"]:
        flags.append(
            "VEHICLE REGISTRATION DATA COULD NOT BE VERIFIED — source unavailable"
        )
    elif vehicle is None and rto is not None:
        flags.append(
            "DATA QUALITY ANOMALY — RTO record exists but "
            "vehicle registration record is missing"
        )

    if not source_status["rto"]["available"]:
        flags.append("RTO DATA COULD NOT BE VERIFIED — source unavailable")

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

    # Entity-matching evidence: records joined by similarity, not exact plate.
    entity_links = []
    link_notes = []
    for source, link in sorted(entity["links"].items()):
        entity_links.append({
            "source": source, "stored_plate": link["value"],
            "link_score": link["link_score"], "exact": link["exact"],
        })
        if not link["exact"]:
            link_notes.append(
                f"{SOURCE_NAMES.get(source, source)} record stored under plate "
                f"'{link['value']}' was linked to {entity['plate']} by similarity "
                f"({link['link_score']:.0%})."
            )

    trust_score = 100 - (20 * len(source_warnings))
    if theft_status in {"stolen", "shredded"}:
        trust_score -= 5
    if vehicle is None and rto is not None and source_status["vehicles"]["available"]:
        trust_score -= 15
    trust_score -= FUZZY_LINK_TRUST_PENALTY * len(link_notes)
    trust_score = max(0, min(100, trust_score))

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
        "vehicle_key": entity["plate"],

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
        "entity_links": entity_links,
        "link_notes": link_notes,
        "source_status": source_status,
        "integration_mode": ("MEDIATION / FEDERATED VIRTUAL INTEGRATION — "
                             "similarity at the sources, entity matching at "
                             "the coordinator"),
        "queried_at": datetime.now().isoformat(timespec="seconds"),
    }


def query_vehicle(plate_input: str) -> dict:
    """
    Federated Vehicle 360 query for one plate.

    Every source returns its records whose plate is identical or similar to
    the given plate. Entity matching links them into vehicles; the vehicle
    that owns this exact plate (as a registered plate, or as a record's
    stored plate that was linked to it) is returned.
    """
    key = normalize_plate(plate_input)
    if key is None:
        return {
            "plate": plate_input,
            "found": False,
            "message": "Please provide a vehicle plate number.",
        }

    per_source, source_status = find_candidates([key])
    entities = build_entities(per_source)
    entity = next((e for e in entities if key in e["keys"]), None)

    if entity is None:
        unavailable = [
            name for name, status in source_status.items()
            if not status["available"]
        ]
        message = (
            "No vehicle record could be constructed because the following "
            f"source(s) are unavailable: {', '.join(unavailable)}."
            if unavailable and not entities
            else "No record with this plate in the federated source databases."
        )
        return {
            "plate": plate_input,
            "vehicle_key": key,
            "found": False,
            "message": message,
            "suggestions": [e["plate"] for e in entities[:5]],
            "source_status": {
                s: dict(st, record_found=False) for s, st in source_status.items()
            },
        }

    return build_result(plate_input, entity, source_status)


# --------------------------------------------------------------------------
# Batch (nightly report): bulk entity matching over every source
# --------------------------------------------------------------------------
BULK_SQL = {
    "vehicles": "SELECT * FROM vehicles ORDER BY id DESC",
    "insurance": "SELECT * FROM insurance_policies ORDER BY policy_end_date DESC",
    "rto": "SELECT * FROM rto_records ORDER BY registration_date DESC",
    "theft": "SELECT * FROM theft_records ORDER BY theft_date DESC",
}
BULK_BLOCK = 30  # anchor plates compared exactly per unmatched record


def _bigrams(text: str) -> set:
    return {text[i:i + 2] for i in range(len(text) - 1)}


def bulk_results() -> list[dict]:
    """Vehicle 360 results for EVERY vehicle known to any source.

    Used by the batch report, where one /api/similar call per plate would be
    far too slow. Each source is read once; records are grouped by exact
    plate, then records whose plate is not a registered plate are linked to
    the closest registered plate with the same rules as build_entities().
    """
    def fetch(source):
        try:
            return source, api_query_dicts(source, BULK_SQL[source]), None
        except Exception as exc:
            return source, None, str(exc)

    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        fetched = list(pool.map(fetch, SOURCES))

    source_status = {}
    groups: dict[str, dict] = {}
    for source, rows, error in fetched:
        source_status[source] = _status(source, rows is not None, error)
        for row in rows or []:
            key = normalize_plate(row.get(plate_column(source)))
            if not key:
                continue
            entity = groups.setdefault(key, detail_match._new_entity(key))
            if source in entity["records"]:
                continue                               # newest row already kept
            entity["records"][source] = row
            entity["links"][source] = {"value": row.get(plate_column(source)),
                                       "query_score": 1.0, "link_score": 1.0,
                                       "exact": True}

    anchors = {k: e for k, e in groups.items() if "vehicles" in e["records"]}
    entities = dict(anchors)
    index: dict[str, set] = {}
    for key in anchors:
        for gram in _bigrams(fold_lookalikes(key)):
            index.setdefault(gram, set()).add(key)

    for key, entity in groups.items():
        if key in anchors:
            continue
        hits = Counter()
        for gram in _bigrams(fold_lookalikes(key)):
            hits.update(index.get(gram, ()))
        block = [k for k, _ in hits.most_common(BULK_BLOCK)]
        anchor_key, score, margin = best_anchor(key, block)
        target = anchors.get(anchor_key)
        if (target is not None and score >= detail_match.LINK_MIN_SCORE
                and margin >= detail_match.LINK_MIN_MARGIN
                and not set(entity["records"]) & set(target["records"])):
            target["keys"] |= entity["keys"]
            for source, row in entity["records"].items():
                target["records"][source] = row
                link = dict(entity["links"][source])
                link.update(link_score=round(score, 4), exact=False)
                target["links"][source] = link
        else:
            entities[key] = entity

    return [build_result(key, entity, source_status)
            for key, entity in sorted(entities.items())]


def list_candidate_plates() -> list[str]:
    """Every plate known to any source (read through the REST APIs)."""
    candidates = set()
    for source in SOURCES:
        column = plate_column(source)
        table = {"vehicles": "vehicles", "insurance": "insurance_policies",
                 "rto": "rto_records", "theft": "theft_records"}[source]
        try:
            for row in api_query_dicts(source, f"SELECT {column} FROM {table}"):
                key = normalize_plate(row.get(column))
                if key:
                    candidates.add(key)
        except Exception:
            continue                    # use the sources that are available
    return sorted(candidates)


# --------------------------------------------------------------------------
# Dropdown values for the detail form (distinct values only, never rows)
# --------------------------------------------------------------------------
OPTION_QUERIES = (
    ("vehicles", "SELECT DISTINCT make, model FROM vehicles"),
    ("vehicles", "SELECT DISTINCT color FROM vehicles"),
    ("vehicles", "SELECT DISTINCT owner_name FROM vehicles LIMIT 5000"),
    ("insurance", "SELECT DISTINCT insurer_name FROM insurance_policies"),
    ("rto", "SELECT DISTINCT rto_office FROM rto_records"),
    ("rto", "SELECT DISTINCT YEAR(registration_date) AS registration_year "
            "FROM rto_records"),
    ("theft", "SELECT DISTINCT YEAR(theft_date) AS theft_year FROM theft_records"),
)


def field_option_values() -> tuple[dict, dict, bool]:
    """(values_by_field, models_by_make, any_source_answered)."""
    def run(job):
        source, sql = job
        try:
            return api_query_dicts(source, sql)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(OPTION_QUERIES)) as pool:
        results = list(pool.map(run, OPTION_QUERIES))

    values: dict[str, set] = {}
    models: dict[str, set] = {}
    answered = False
    for rows in results:
        if rows is None:
            continue
        answered = True
        for row in rows:
            for field, value in row.items():
                text = str(value).strip() if value is not None else ""
                if text:
                    values.setdefault(field, set()).add(text)
            make, model = row.get("make"), row.get("model")
            if make and model:
                models.setdefault(str(make).strip(), set()).add(str(model).strip())
    return values, models, answered


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