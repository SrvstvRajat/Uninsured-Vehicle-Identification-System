"""ENTITY MATCHING at the Coordinator.

Similarity matching happens on the source laptops (POST /api/similar): each
source only answers "which of MY stored values look like this one?".  This
module takes those per-source candidates and decides which records across
the four databases are the SAME vehicle (entity resolution), then ranks the
resulting vehicles against the typed plate and any operator-supplied details.

    build_entities()  link per-source candidate records into vehicles
    entity_profile()  one flat profile per vehicle (for detail scoring / UI)
    rank_entities()   rank vehicles by plate + detail evidence
    decide()          auto-identify only a strong, unambiguous winner

Identify a vehicle from a partial / noisy plate PLUS verified details.

The plate alone is often ambiguous (e.g. ``DL01AB10?1`` is close to several
registered plates).  When the operator can also see the vehicle's make, model,
colour, owner, engine or chassis number, that evidence is fused with the plate
similarity so the one registration that agrees on *everything* wins.

Pure Python, no database access: callers pass registry rows
(dicts with reg_plate, make, model, color, owner_name, engine_no, chassis_no).
"""

import re
from datetime import date
from difflib import SequenceMatcher

from fuzzy_match import (
    edit_similarity,
    normalize_plate,
    plate_similarity,
    _substring_distance,
)

# Weight of the plate vs. each operator-supplied detail.  Identifier-like
# fields (chassis/engine) are near-unique so they carry the most weight;
# colour is common to many cars so it carries the least of the descriptive set.
PLATE_WEIGHT = 0.45   # minimum plate share; grows with the number of details

# One entry per field, grouped by the source database it comes from.
# (weight reflects how unique the value is: identifiers > descriptive > status)
SECTIONS = [
    {"key": "vehicles", "title": "Vehicle Registration DB", "icon": "\U0001F697",
     "fields": [("make", "Make"), ("model", "Model"), ("color", "Color"),
                ("owner_name", "Owner name"), ("engine_no", "Engine no."),
                ("chassis_no", "Chassis no.")]},
    {"key": "insurance", "title": "Insurance DB", "icon": "\U0001F6E1\uFE0F",
     "fields": [("insurer_name", "Insurer"), ("policy_no", "Policy no."),
                ("policy_status", "Policy status")]},
    {"key": "rto", "title": "RTO DB", "icon": "\U0001F3DB\uFE0F",
     "fields": [("rto_office", "RTO office"),
                ("registration_year", "Registration year"),
                ("renewal_status", "Renewal status")]},
    {"key": "theft", "title": "Theft / Shredding DB", "icon": "\U0001F6A8",
     "fields": [("theft_status", "Theft status"), ("theft_year", "Theft year")]},
]
DETAIL_LABELS = {f: label for sec in SECTIONS for f, label in sec["fields"]}

DETAIL_WEIGHTS = {
    "chassis_no": 0.35, "policy_no": 0.35, "engine_no": 0.30,
    "model": 0.25, "color": 0.20, "insurer_name": 0.20, "theft_status": 0.20,
    "owner_name": 0.15, "make": 0.15,
    "theft_year": 0.12, "registration_year": 0.12,
    "rto_office": 0.10, "policy_status": 0.10, "renewal_status": 0.08,
}
DETAIL_FIELDS = tuple(DETAIL_WEIGHTS)

# Closed-vocabulary fields compare exactly (no partial credit).
CATEGORICAL_FIELDS = frozenset((
    "policy_status", "renewal_status", "theft_status",
    "registration_year", "theft_year",
))
# Fields shared by many vehicles: agreeing on them alone is weak evidence,
# so they never count as the "agreeing detail" needed for auto-identification.
LOW_INFO_FIELDS = frozenset(("policy_status", "renewal_status", "rto_office"))

# Identifiers compared with OCR-aware edit distance.
CODE_FIELDS = frozenset(("chassis_no", "engine_no", "policy_no"))

# Identifier-like fields: a one-character difference is usually a *different*
# vehicle (ENG1000006 vs ENG1000000), so near-matches are sharpened downward.
STRICT_FIELDS = frozenset(("chassis_no", "engine_no", "owner_name", "policy_no"))

MATCH_LEVEL = 0.80      # field counts as "matches"
MISMATCH_LEVEL = 0.50   # below this the field "contradicts" the candidate

AUTO_SCORE = 0.70       # combined score needed to auto-identify
AUTO_MARGIN = 0.08      # lead required over the runner-up
PLATE_ONLY_SCORE = 0.60  # same thresholds the plate-only flow already used
PLATE_ONLY_MARGIN = 0.07


def _norm(value, field):
    if value is None:
        return ""
    text = str(value).strip().casefold()
    if field == "owner_name":
        return " ".join(sorted(re.findall(r"[a-z0-9]+", text)))
    return re.sub(r"[^a-z0-9]", "", text)


def _detail_similarity(supplied, stored, field):
    left, right = _norm(supplied, field), _norm(stored, field)
    if not left or not right:
        return None
    if left == right:
        return 1.0
    if field in CATEGORICAL_FIELDS:
        return 0.0
    if field in CODE_FIELDS:
        # Identifiers: OCR look-alikes (0/O, 1/I, 8/B ...) are cheap edits.
        return max(
            SequenceMatcher(None, left, right, autojunk=False).ratio(),
            edit_similarity(left.upper(), right.upper(), ocr_aware=True),
        )
    # A typed fragment that sits inside the stored value ("nex" in "nexon")
    # is a strong partial match, but not as strong as a full match.
    if len(left) >= 3 and (left in right or right in left):
        return 0.9
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def partial_plate_similarity(query, candidate):
    """Plate similarity that also tolerates truncated / fragment queries.

    ``plate_similarity`` handles OCR confusions, wildcards and extra text.
    A query that is only a *piece* of the plate ("AB1001", "DL01AB10") is
    aligned against any substring of the candidate instead, then scaled down
    for very short fragments so 2-3 characters never look conclusive.
    """
    q, c = normalize_plate(query), normalize_plate(candidate)
    if not q or not c:
        return 0.0
    best = plate_similarity(q, c)
    if len(q) < len(c):
        distance = _substring_distance(q, c)
        fragment = max(0.0, 1.0 - distance / len(q))
        fragment *= min(1.0, 0.5 + len(q) / 16.0)
        best = max(best, fragment)
    return min(1.0, best)


def score_with_details(plate_query, details, row, plate_score=None):
    """Return (combined_score, plate_score, per_field_verdicts) for one row.

    `plate_score` may be supplied when the plate similarity is already known
    (e.g. computed by the source laptop); otherwise it is computed here.
    """
    if plate_score is None:
        plate_score = partial_plate_similarity(plate_query, row.get("reg_plate"))
    verdicts = {}
    detail_sum = detail_total = 0.0
    for field, weight in DETAIL_WEIGHTS.items():
        supplied = (details or {}).get(field)
        if not supplied:
            continue
        sim = _detail_similarity(supplied, row.get(field), field)
        if sim is None:       # source has no value: neither evidence nor penalty
            continue
        if field in STRICT_FIELDS and sim < 1.0:
            sim = max(0.0, (sim - 0.5) / 0.5) ** 2
        detail_sum += weight * sim
        detail_total += weight
        verdicts[field] = {
            "supplied": supplied,
            "stored": row.get(field),
            "similarity": sim,
            "status": (
                "match" if sim >= MATCH_LEVEL
                else "mismatch" if sim < MISMATCH_LEVEL
                else "partial"
            ),
        }
    if plate_query:
        # Keep the plate a substantial share however many details are given.
        plate_w = max(PLATE_WEIGHT, min(1.0, 0.6 * detail_total))
    else:
        plate_w = 0.0
    total = plate_w + detail_total
    combined = (plate_w * plate_score + detail_sum) / total if total else 0.0
    return combined, plate_score, verdicts


def rank_with_details(plate_query, details, rows, limit=5):
    """Rank registry rows by plate + detail evidence (best first)."""
    details = {k: v.strip() for k, v in (details or {}).items()
               if k in DETAIL_WEIGHTS and v and v.strip()}
    scored = []
    for row in rows:
        combined, plate_score, verdicts = score_with_details(
            plate_query, details, row
        )
        scored.append({
            "plate": normalize_plate(row.get("reg_plate")),
            "score": combined,
            "plate_score": plate_score,
            "fields": verdicts,
            "row": row,
        })
    scored.sort(key=lambda item: (-item["score"], -item["plate_score"],
                                  item["plate"]))
    return scored[:limit]


def decide(ranked, used_details):
    """Return (best_plate, auto_ok, reason).

    With details: the leader must clear the combined threshold, lead the
    runner-up, and agree with at least one supplied detail without
    contradicting any supplied detail.  Without details the original
    plate-only thresholds apply.
    """
    if not ranked:
        return None, False, "no candidates"
    best = ranked[0]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    margin = best["score"] - second

    if not used_details:
        ok = best["score"] >= PLATE_ONLY_SCORE and margin >= PLATE_ONLY_MARGIN
        return best["plate"], ok, "plate only"

    fields = best["fields"]
    agreeing = [f for f, v in fields.items()
                if v["status"] == "match" and f not in LOW_INFO_FIELDS]
    conflicts = [f for f, v in fields.items() if v["status"] == "mismatch"]
    ok = (
        best["score"] >= AUTO_SCORE
        and margin >= AUTO_MARGIN
        and bool(agreeing)
        and not conflicts
    )
    if ok:
        reason = "plate + " + ", ".join(DETAIL_LABELS[f] for f in agreeing)
    elif margin < AUTO_MARGIN:
        reason = "several vehicles fit equally well; add another detail"
    elif conflicts:
        reason = ("a supplied detail contradicts the closest plate: "
                  + ", ".join(conflicts))
    else:
        reason = "no registration agrees strongly enough"
    return best["plate"], ok, reason


# =========================================================================
# Entity resolution across sources
# =========================================================================
ENTITY_SOURCES = ("vehicles", "insurance", "rto", "theft")

# A record whose plate is not exactly a registered plate is linked to the
# registered vehicle whose plate it resembles most, only if it is clearly
# closest (score and margin) and that vehicle has no record from the same
# source already (an exact record always wins over a similar one).
LINK_MIN_SCORE = 0.85
LINK_MIN_MARGIN = 0.05


def symmetric_plate_score(left, right):
    if left == right:
        return 1.0
    return max(plate_similarity(left, right), plate_similarity(right, left))


def best_anchor(key, anchor_keys):
    """Return (anchor_key, score, margin) of the closest anchor plate, or (None, 0, 0)."""
    scored = sorted(
        ((symmetric_plate_score(key, anchor), anchor) for anchor in anchor_keys),
        reverse=True,
    )
    if not scored:
        return None, 0.0, 0.0
    best_score, best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return best, best_score, best_score - second


def _new_entity(key):
    return {"plate": key, "keys": {key}, "plate_score": 0.0,
            "records": {}, "links": {}}


def build_entities(per_source):
    """Link the per-source similarity candidates into vehicle entities.

    per_source: {source: {"available": bool,
                          "matches": [{"value", "score", "rows": [...]}]}}
    Returns a list of entities:
        {"plate": anchor plate key, "keys": {every member plate key},
         "plate_score": similarity of the query to the anchor plate,
         "records": {source: newest row},
         "links": {source: {"value", "query_score", "link_score", "exact"}}}
    """
    items = []
    for source, result in (per_source or {}).items():
        if source not in ENTITY_SOURCES or not result.get("available"):
            continue
        for match in result.get("matches") or []:
            key = normalize_plate(match.get("value"))
            if not key:
                continue
            rows = match.get("rows") or []
            items.append({
                "source": source, "key": key, "value": match.get("value"),
                "query_score": float(match.get("score") or 0.0),
                "row": rows[0] if rows else None,
            })

    # 1. Records with the same normalised plate are the same vehicle.
    groups = {}
    for item in sorted(items, key=lambda it: -it["query_score"]):
        entity = groups.setdefault(item["key"], _new_entity(item["key"]))
        entity["plate_score"] = max(entity["plate_score"], item["query_score"])
        if item["source"] in entity["records"]:
            continue
        entity["records"][item["source"]] = item["row"]
        entity["links"][item["source"]] = {
            "value": item["value"], "query_score": item["query_score"],
            "link_score": 1.0, "exact": True,
        }

    # 2. Registered plates (vehicles source) are anchors; link the others.
    anchors = {k: e for k, e in groups.items() if "vehicles" in e["records"]}
    if not anchors:
        return _sorted_entities(groups.values())

    entities = dict(anchors)
    others = sorted((e for k, e in groups.items() if k not in anchors),
                    key=lambda e: -e["plate_score"])
    for entity in others:
        anchor_key, score, margin = best_anchor(entity["plate"], anchors)
        target = anchors.get(anchor_key)
        if (target is not None and score >= LINK_MIN_SCORE
                and margin >= LINK_MIN_MARGIN
                and not set(entity["records"]) & set(target["records"])):
            target["keys"] |= entity["keys"]
            for source, row in entity["records"].items():
                target["records"][source] = row
                link = dict(entity["links"][source])
                link.update(link_score=round(score, 4), exact=False)
                target["links"][source] = link
        else:
            entities[entity["plate"]] = entity      # stands alone
    return _sorted_entities(entities.values())


def _sorted_entities(entities):
    return sorted(entities, key=lambda e: (-e["plate_score"],
                                           -len(e["records"]), e["plate"]))


def _year(value):
    text = str(value or "")[:4]
    return text if text.isdigit() else None


def entity_profile(entity, available_sources):
    """Flat profile of one entity (same fields the detail form offers).

    A field is None when its source is unreachable (no evidence, no penalty).
    When the source answered but holds no record for this vehicle the field
    gets an explicit "No ..." marker, so "insurer = HDFC" contradicts an
    uninsured vehicle.
    """
    today = date.today().isoformat()
    records = entity["records"]
    profile = {"reg_plate": entity["plate"]}

    vehicle = records.get("vehicles")
    if vehicle:
        for field in ("make", "model", "color", "owner_name",
                      "engine_no", "chassis_no"):
            profile[field] = vehicle.get(field)

    insurance = records.get("insurance")
    if insurance:
        end = str(insurance.get("policy_end_date") or "")[:10]
        profile.update(insurer_name=insurance.get("insurer_name"),
                       policy_no=insurance.get("policy_no"),
                       policy_status="Active" if end and end >= today else "Expired")
    elif "insurance" in available_sources:
        profile.update(insurer_name="No policy", policy_no="No policy",
                       policy_status="No policy")

    rto = records.get("rto")
    if rto:
        renewal = str(rto.get("renewal_date") or "")[:10]
        profile.update(rto_office=rto.get("rto_office"),
                       registration_year=_year(rto.get("registration_date")),
                       renewal_status="Valid" if renewal and renewal >= today else "Lapsed")
    elif "rto" in available_sources:
        profile.update(rto_office="No RTO record", registration_year="No RTO record",
                       renewal_status="No RTO record")

    theft = records.get("theft")
    if theft:
        profile.update(
            theft_status=str(theft.get("status") or "").strip().capitalize() or None,
            theft_year=_year(theft.get("theft_date")))
    elif "theft" in available_sources:
        profile.update(theft_status="No theft record", theft_year="No theft record")
    return profile


def rank_entities(entities, details, available_sources, has_plate=True, limit=5):
    """Rank entities by plate similarity alone, or plate + details.

    Items keep the shape the UI already uses: plate, score, plate_score,
    fields, row (+ sources and links for the entity view).
    """
    details = {k: v.strip() for k, v in (details or {}).items()
               if k in DETAIL_WEIGHTS and v and v.strip()}
    ranked = []
    for entity in entities:
        profile = entity_profile(entity, available_sources)
        plate_score = entity["plate_score"] if has_plate else 0.0
        if details:
            score, _plate, verdicts = score_with_details(
                "plate" if has_plate else "", details, profile,
                plate_score=plate_score)
        else:
            score, verdicts = plate_score, {}
        ranked.append({
            "plate": entity["plate"], "score": score, "plate_score": plate_score,
            "fields": verdicts, "row": profile,
            "sources": sorted(entity["records"]), "links": entity["links"],
            "entity": entity,
        })
    # More corroborating sources breaks ties between equally similar plates.
    ranked.sort(key=lambda item: (-item["score"], -len(item["sources"]),
                                  -item["plate_score"], item["plate"]))
    return ranked[:limit]