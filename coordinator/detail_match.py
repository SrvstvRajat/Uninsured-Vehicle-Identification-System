# """Identify a vehicle from a partial / noisy plate PLUS verified details.

# The plate alone is often ambiguous (e.g. ``DL01AB10?1`` is close to several
# registered plates).  When the operator can also see the vehicle's make, model,
# colour, owner, engine or chassis number, that evidence is fused with the plate
# similarity so the one registration that agrees on *everything* wins.

# Pure Python, no database access: callers pass registry rows
# (dicts with reg_plate, make, model, color, owner_name, engine_no, chassis_no).
# """

# import re
# from difflib import SequenceMatcher

# from fuzzy_match import (
#     normalize_plate,
#     plate_similarity,
#     _substring_distance,
# )

# # Weight of the plate vs. each operator-supplied detail.  Identifier-like
# # fields (chassis/engine) are near-unique so they carry the most weight;
# # colour is common to many cars so it carries the least of the descriptive set.
# PLATE_WEIGHT = 0.45
# DETAIL_WEIGHTS = {
#     "chassis_no": 0.35,
#     "engine_no": 0.30,
#     "model": 0.25,
#     "color": 0.20,
#     "owner_name": 0.15,
#     "make": 0.15,
# }
# DETAIL_FIELDS = tuple(DETAIL_WEIGHTS)

# # Identifier-like fields: a one-character difference is usually a *different*
# # vehicle (ENG1000006 vs ENG1000000), so near-matches are sharpened downward.
# STRICT_FIELDS = frozenset(("chassis_no", "engine_no", "owner_name"))

# MATCH_LEVEL = 0.80      # field counts as "matches"
# MISMATCH_LEVEL = 0.50   # below this the field "contradicts" the candidate

# AUTO_SCORE = 0.70       # combined score needed to auto-identify
# AUTO_MARGIN = 0.08      # lead required over the runner-up
# PLATE_ONLY_SCORE = 0.60  # same thresholds the plate-only flow already used
# PLATE_ONLY_MARGIN = 0.07


# def _norm(value, field):
#     if value is None:
#         return ""
#     text = str(value).strip().casefold()
#     if field == "owner_name":
#         return " ".join(sorted(re.findall(r"[a-z0-9]+", text)))
#     return re.sub(r"[^a-z0-9]", "", text)


# def _detail_similarity(supplied, stored, field):
#     left, right = _norm(supplied, field), _norm(stored, field)
#     if not left or not right:
#         return None
#     if left == right:
#         return 1.0
#     # A typed fragment that sits inside the stored value ("nex" in "nexon")
#     # is a strong partial match, but not as strong as a full match.
#     if len(left) >= 3 and (left in right or right in left):
#         return 0.9
#     return SequenceMatcher(None, left, right, autojunk=False).ratio()


# def partial_plate_similarity(query, candidate):
#     """Plate similarity that also tolerates truncated / fragment queries.

#     ``plate_similarity`` handles OCR confusions, wildcards and extra text.
#     A query that is only a *piece* of the plate ("AB1001", "DL01AB10") is
#     aligned against any substring of the candidate instead, then scaled down
#     for very short fragments so 2-3 characters never look conclusive.
#     """
#     q, c = normalize_plate(query), normalize_plate(candidate)
#     if not q or not c:
#         return 0.0
#     best = plate_similarity(q, c)
#     if len(q) < len(c):
#         distance = _substring_distance(q, c)
#         fragment = max(0.0, 1.0 - distance / len(q))
#         fragment *= min(1.0, 0.5 + len(q) / 16.0)
#         best = max(best, fragment)
#     return min(1.0, best)


# def score_with_details(plate_query, details, row):
#     """Return (combined_score, plate_score, per_field_verdicts) for one row."""
#     plate_score = partial_plate_similarity(plate_query, row.get("reg_plate"))
#     weighted = PLATE_WEIGHT * plate_score if plate_query else 0.0
#     total = PLATE_WEIGHT if plate_query else 0.0
#     verdicts = {}
#     for field, weight in DETAIL_WEIGHTS.items():
#         supplied = (details or {}).get(field)
#         if not supplied:
#             continue
#         sim = _detail_similarity(supplied, row.get(field), field)
#         if sim is None:       # registry has no value: neither evidence nor penalty
#             continue
#         if field in STRICT_FIELDS and sim < 1.0:
#             sim = max(0.0, (sim - 0.5) / 0.5) ** 2
#         weighted += weight * sim
#         total += weight
#         verdicts[field] = {
#             "supplied": supplied,
#             "stored": row.get(field),
#             "similarity": sim,
#             "status": (
#                 "match" if sim >= MATCH_LEVEL
#                 else "mismatch" if sim < MISMATCH_LEVEL
#                 else "partial"
#             ),
#         }
#     combined = weighted / total if total else 0.0
#     return combined, plate_score, verdicts


# def rank_with_details(plate_query, details, rows, limit=5):
#     """Rank registry rows by plate + detail evidence (best first)."""
#     details = {k: v.strip() for k, v in (details or {}).items()
#                if k in DETAIL_WEIGHTS and v and v.strip()}
#     scored = []
#     for row in rows:
#         combined, plate_score, verdicts = score_with_details(
#             plate_query, details, row
#         )
#         scored.append({
#             "plate": normalize_plate(row.get("reg_plate")),
#             "score": combined,
#             "plate_score": plate_score,
#             "fields": verdicts,
#             "row": row,
#         })
#     scored.sort(key=lambda item: (-item["score"], -item["plate_score"],
#                                   item["plate"]))
#     return scored[:limit]


# def decide(ranked, used_details):
#     """Return (best_plate, auto_ok, reason).

#     With details: the leader must clear the combined threshold, lead the
#     runner-up, and agree with at least one supplied detail without
#     contradicting any supplied detail.  Without details the original
#     plate-only thresholds apply.
#     """
#     if not ranked:
#         return None, False, "no candidates"
#     best = ranked[0]
#     second = ranked[1]["score"] if len(ranked) > 1 else 0.0
#     margin = best["score"] - second

#     if not used_details:
#         ok = best["score"] >= PLATE_ONLY_SCORE and margin >= PLATE_ONLY_MARGIN
#         return best["plate"], ok, "plate only"

#     fields = best["fields"]
#     agreeing = [f for f, v in fields.items() if v["status"] == "match"]
#     conflicts = [f for f, v in fields.items() if v["status"] == "mismatch"]
#     ok = (
#         best["score"] >= AUTO_SCORE
#         and margin >= AUTO_MARGIN
#         and bool(agreeing)
#         and not conflicts
#     )
#     if ok:
#         reason = "plate + " + ", ".join(agreeing)
#     elif margin < AUTO_MARGIN:
#         reason = "several vehicles fit equally well; add another detail"
#     elif conflicts:
#         reason = ("a supplied detail contradicts the closest plate: "
#                   + ", ".join(conflicts))
#     else:
#         reason = "no registration agrees strongly enough"
#     return best["plate"], ok, reason


"""Identify a vehicle from a partial / noisy plate PLUS verified details.

The plate alone is often ambiguous (e.g. ``DL01AB10?1`` is close to several
registered plates).  When the operator can also see the vehicle's make, model,
colour, owner, engine or chassis number, that evidence is fused with the plate
similarity so the one registration that agrees on *everything* wins.

Pure Python, no database access: callers pass registry rows
(dicts with reg_plate, make, model, color, owner_name, engine_no, chassis_no).
"""

import re
from difflib import SequenceMatcher

from fuzzy_match import (
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


def score_with_details(plate_query, details, row):
    """Return (combined_score, plate_score, per_field_verdicts) for one row."""
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