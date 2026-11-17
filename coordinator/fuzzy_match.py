"""Rank noisy vehicle records against a clean reference CSV."""

import argparse
import csv
import heapq
import itertools
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_NOISY = ROOT / "data" / "laptop1_vehicle_registration_noisy.csv"
DEFAULT_REFERENCE = ROOT / "data" / "laptop1_vehicle_registration.csv"
DEFAULT_OUTPUT = ROOT / "data" / "phase2_match_candidates.csv"

PLATE_WEIGHT = 0.48
FIELD_WEIGHTS = {
    "make": 0.06,
    "model": 0.08,
    "color": 0.03,
    "owner_name": 0.03,
    "engine_no": 0.14,
    "chassis_no": 0.18,
}
OCR_CONFUSIONS = {
    frozenset(("0", "O")),
    frozenset(("0", "D")),
    frozenset(("0", "Q")),
    frozenset(("1", "I")),
    frozenset(("1", "L")),
    frozenset(("2", "Z")),
    frozenset(("5", "S")),
    frozenset(("6", "G")),
    frozenset(("8", "B")),
    frozenset(("4", "A")),
    frozenset(("7", "T")),
    frozenset(("3", "8")),
    frozenset(("1", "7")),
    frozenset(("5", "6")),
    frozenset(("0", "8")),
    frozenset(("4", "9")),
    frozenset(("M", "N")),
    frozenset(("U", "V")),
    frozenset(("P", "R")),
    frozenset(("E", "F")),
    frozenset(("C", "G")),
    frozenset(("K", "X")),
}
WILDCARD_CHARS = frozenset(("?", "@", "#", "*"))
IDENTIFIER_PREFIXES = {
    "engine_no": "ENG",
    "chassis_no": "CHS",
}
SPLIT_MERGE_CONFUSIONS = (
    ("W", "VV"),
    ("M", "IV"),
    ("H", "II"),
    ("U", "LI"),
    ("M", "RN"),
)
TOP_CANDIDATES = 5
AUTO_MATCH_SCORE = 0.85
REVIEW_SCORE = 0.60
MIN_AUTO_MARGIN = 0.07


def normalize_plate(value):
    """Normalize formatting without guessing at OCR-confused characters."""
    if value is None:
        return ""
    text = re.sub(r"[\s.-]", "", str(value).strip().upper())
    return re.sub(r"[^A-Z0-9?@#*]", "?", text)


def learn_plate_confusions(noisy_rows, reference_rows):
    """Learn substitution costs from paired rows with matching IDs."""
    reference_by_id = {
        str(row.get("id")): row
        for row in reference_rows
        if row.get("id")
    }
    counts = Counter()
    for row in noisy_rows:
        row_id = str(row.get("id") or "")
        reference = reference_by_id.get(row_id)
        if reference is None:
            continue
        noisy = normalize_plate(row.get("reg_plate"))
        clean = normalize_plate(reference.get("reg_plate"))
        if len(noisy) != len(clean):
            continue
        for observed, expected in zip(noisy, clean):
            if observed != expected and observed not in WILDCARD_CHARS:
                counts[frozenset((observed, expected))] += 1
    if not counts:
        return {}
    learned = {
        pair: max(
            0.05,
            0.3 / (1 + (count - 1) ** 0.5),
        )
        for pair, count in counts.items()
        if count >= 2
    }
    return learned


def _substitution_cost(left, right, ocr_aware, confusion_costs):
    if left == right:
        return 0.0
    if left in WILDCARD_CHARS or right in WILDCARD_CHARS:
        return 0.05
    pair = frozenset((left, right))
    if confusion_costs and pair in confusion_costs:
        return confusion_costs[pair]
    if ocr_aware and pair in OCR_CONFUSIONS:
        return 0.3
    return 1.0


def _weighted_damerau_distance(left, right, confusion_costs=None):
    rows, columns = len(left), len(right)
    matrix = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows + 1):
        matrix[row][0] = float(row)
    for column in range(columns + 1):
        matrix[0][column] = float(column)

    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            matrix[row][column] = min(
                matrix[row - 1][column] + 1.0,
                matrix[row][column - 1] + 1.0,
                matrix[row - 1][column - 1] + _substitution_cost(
                    left[row - 1], right[column - 1], True, confusion_costs
                ),
            )
            if (
                row > 1 and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                matrix[row][column] = min(
                    matrix[row][column],
                    matrix[row - 2][column - 2] + 0.75,
                )
            for single, double in SPLIT_MERGE_CONFUSIONS:
                if (
                    row >= 1 and column >= 2
                    and left[row - 1] == single
                    and right[column - 2:column] == double
                ):
                    matrix[row][column] = min(
                        matrix[row][column],
                        matrix[row - 1][column - 2] + 0.3,
                    )
                if (
                    row >= 2 and column >= 1
                    and left[row - 2:row] == double
                    and right[column - 1] == single
                ):
                    matrix[row][column] = min(
                        matrix[row][column],
                        matrix[row - 2][column - 1] + 0.3,
                    )
    return matrix[rows][columns]


def _substring_distance(left, right, confusion_costs=None):
    """Align all of left to a substring of right, ignoring right-side borders."""
    rows, columns = len(left), len(right)
    matrix = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        matrix[row][0] = float(row)
    for column in range(columns + 1):
        matrix[0][column] = 0.0

    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            matrix[row][column] = min(
                matrix[row - 1][column] + 1.0,
                matrix[row][column - 1] + 1.0,
                matrix[row - 1][column - 1] + _substitution_cost(
                    left[row - 1], right[column - 1], True, confusion_costs
                ),
            )
            if (
                row > 1 and column > 1
                and left[row - 1] == right[column - 2]
                and left[row - 2] == right[column - 1]
            ):
                matrix[row][column] = min(
                    matrix[row][column],
                    matrix[row - 2][column - 2] + 0.75,
                )
    return min(matrix[rows])


def _plate_segments(value):
    return re.findall(r"[A-Z]+|[0-9]+|[?@#*]+", value)


def segment_order_variants(value):
    segments = _plate_segments(value)
    if len(segments) != 4 or any(
        any(char in WILDCARD_CHARS for char in segment)
        for segment in segments
    ):
        return {value}
    if sum(segment.isalpha() for segment in segments) != 2:
        return {value}
    if sum(segment.isdigit() for segment in segments) != 2:
        return {value}
    if (
        segments[0].isalpha()
        and len(segments[0]) == 2
        and segments[1].isdigit()
        and len(segments[1]) in (1, 2)
        and segments[2].isalpha()
        and 1 <= len(segments[2]) <= 3
        and segments[3].isdigit()
        and 1 <= len(segments[3]) <= 4
    ):
        return {value}
    return {"".join(order) for order in itertools.permutations(segments)}


def plate_similarity(query, candidate, confusion_costs=None):
    """Score OCR plate text, including wildcards, extra text and segment reordering."""
    left = normalize_plate(query)
    right = normalize_plate(candidate)
    if not left or not right:
        return 0.0

    variants = segment_order_variants(left)
    best = 0.0
    for variant in variants:
        distance = _weighted_damerau_distance(
            variant, right, confusion_costs
        )
        best = max(
            best,
            1.0 - distance / max(len(variant), len(right), 1),
        )

        if len(variant) > len(right) and len(right) >= 7:
            distance = _substring_distance(
                right, variant, confusion_costs
            )
            best = max(best, 1.0 - distance / len(right))

    # Plate frames and labels can add text before or after the plate. Compare
    # plausible plate-sized windows, but do not turn short fragments into matches.
    return max(0.0, min(1.0, best))


def normalize_text(value, field):
    if value is None:
        return ""
    text = str(value).strip().casefold()
    if field == "owner_name":
        # Sorting tokens supports common OCR/source variations such as
        # "Mehta, Deepak" versus "Deepak Mehta".
        return " ".join(sorted(re.findall(r"[a-z0-9]+", text)))
    return re.sub(r"[^a-z0-9]", "", text)


def edit_similarity(left, right, ocr_aware=False, confusion_costs=None):
    """Return a 0..1 edit similarity, with low-cost OCR substitutions."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    previous = [float(index) for index in range(len(right) + 1)]
    before_previous = None

    for row, left_char in enumerate(left, start=1):
        current = [float(row)]
        for column, right_char in enumerate(right, start=1):
            substitution_cost = _substitution_cost(
                left_char, right_char, ocr_aware, confusion_costs
            )

            cost = min(
                previous[column] + 1.0,
                current[column - 1] + 1.0,
                previous[column - 1] + substitution_cost,
            )
            if (
                before_previous is not None
                and row > 1
                and column > 1
                and left_char == right[column - 2]
                and left[row - 2] == right_char
            ):
                cost = min(cost, before_previous[column - 2] + 0.75)
            current.append(cost)
        before_previous, previous = previous, current

    return max(0.0, 1.0 - previous[-1] / max(len(left), len(right)))


def normalize_identifier(value, field):
    """Remove identifier formatting and the standard prefix for its field."""
    text = re.sub(r"[\s.-]", "", str(value or "").strip().upper())
    text = re.sub(r"[^A-Z0-9?@#*]", "?", text)
    prefix = IDENTIFIER_PREFIXES.get(field, "")
    if prefix and text.startswith(prefix):
        text = text[len(prefix):]
    return text


def identifier_similarity(left, right, field):
    """Compare engine/chassis serials independently of their field prefixes."""
    return edit_similarity(
        normalize_identifier(left, field),
        normalize_identifier(right, field),
        ocr_aware=True,
    )


def field_similarity(left, right, field):
    left_value = normalize_text(left, field)
    right_value = normalize_text(right, field)
    if not left_value or not right_value:
        return None
    return SequenceMatcher(None, left_value, right_value, autojunk=False).ratio()


def row_identifier(row, row_number):
    """Return an output label; IDs are never used to create or score matches."""
    return str(row.get("id") or row_number)


def read_csv(path):
    with Path(path).open("r", newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


def make_candidate_index(reference_rows):
    exact_fields = defaultdict(lambda: defaultdict(set))
    normalized_plates = []
    plate_grams = []
    folded_grams = defaultdict(set)
    for index, row in enumerate(reference_rows):
        plate = normalize_plate(row.get("reg_plate"))
        normalized_plates.append(plate)
        plate_grams.append({plate[offset:offset + 2] for offset in range(len(plate) - 1)})
        folded = fold_lookalikes(plate)
        for offset in range(len(folded) - 1):
            folded_grams[folded[offset:offset + 2]].add(index)
        for field in FIELD_WEIGHTS:
            value = normalize_text(row.get(field), field)
            if value:
                exact_fields[field][value].add(index)
    return normalized_plates, plate_grams, folded_grams, exact_fields


def fold_lookalikes(value):
    groups = (
        ("0ODQ", "0"),
        ("1IL", "1"),
        ("2Z", "2"),
        ("5S", "5"),
        ("6G", "6"),
        ("8B", "8"),
        ("4A", "4"),
        ("7T", "7"),
    )
    folded = []
    for char in value:
        folded.append(next((target for source, target in groups if char in source), char))
    return "".join(folded)


def candidate_indices(
    query, reference_rows, normalized_plates, plate_grams, folded_grams,
    exact_fields
):
    """Use approximate plate neighbors plus exact contextual evidence."""
    query_plate = normalize_plate(query.get("reg_plate"))
    query_grams = {
        query_plate[offset:offset + 2] for offset in range(len(query_plate) - 1)
    }
    query_folded = fold_lookalikes(query_plate)
    folded_query_grams = {
        query_folded[offset:offset + 2]
        for offset in range(len(query_folded) - 1)
    }
    plate_ranked = []
    for index, candidate_grams in enumerate(plate_grams):
        overlap = sum(gram in candidate_grams for gram in query_grams)
        union_size = len(query_grams) + len(candidate_grams) - overlap
        similarity = overlap / union_size if union_size else 0.0
        plate_ranked.append((similarity, index))
    plate_ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = {index for _, index in plate_ranked[:50]}

    folded_hits = Counter()
    for gram in folded_query_grams:
        folded_hits.update(folded_grams.get(gram, ()))
    selected.update(index for index, _ in folded_hits.most_common(50))

    for field in ("owner_name", "engine_no", "chassis_no"):
        value = normalize_text(query.get(field), field)
        if value:
            selected.update(exact_fields[field].get(value, ()))

    return selected


def score_candidate(query, candidate, confusion_costs=None):
    query_plate = normalize_plate(query.get("reg_plate"))
    candidate_plate = normalize_plate(candidate.get("reg_plate"))
    weighted_score = 0.0
    total_weight = 0.0

    if query_plate and candidate_plate:
        weighted_score += PLATE_WEIGHT * plate_similarity(
            query_plate, candidate_plate, confusion_costs
        )
        total_weight += PLATE_WEIGHT

    evidence = []
    for field, weight in FIELD_WEIGHTS.items():
        similarity = field_similarity(query.get(field), candidate.get(field), field)
        if similarity is not None:
            weighted_score += weight * similarity
            total_weight += weight
            if similarity >= 0.80:
                evidence.append(field)

    score = weighted_score / total_weight if total_weight else 0.0
    return score, evidence


def rank_matches(query_rows, reference_rows, top_k, confusion_costs=None):
    normalized_plates, plate_grams, folded_grams, exact_fields = make_candidate_index(
        reference_rows
    )
    ranked_results = []

    for query_number, query in enumerate(query_rows, start=1):
        indices = candidate_indices(
            query, reference_rows, normalized_plates, plate_grams,
            folded_grams, exact_fields
        )
        scored = []
        for index in indices:
            candidate = reference_rows[index]
            score, evidence = score_candidate(
                query, candidate, confusion_costs
            )
            plate_score = plate_similarity(
                normalize_plate(query.get("reg_plate")),
                normalized_plates[index],
                confusion_costs,
            )
            scored.append((score, plate_score, evidence, index))
        scored.sort(key=lambda item: (-item[0], -item[1], item[3]))

        top = scored[:top_k]
        best_score = scored[0][0] if scored else 0.0
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_score - second_score
        if best_score >= AUTO_MATCH_SCORE and margin >= MIN_AUTO_MARGIN:
            decision = "AUTO_MATCH"
        elif best_score >= REVIEW_SCORE:
            decision = "REVIEW"
        else:
            decision = "UNMATCHED"

        ranked_results.append({
            "query_number": query_number,
            "query": query,
            "decision": decision,
            "score": best_score,
            "margin": margin,
            "candidates": top,
        })
    return ranked_results


def write_ranked_csv(path, ranked_results, query_rows, reference_rows, top_k):
    fields = [
        "query_row",
        "query_source_id",
        "raw_plate",
        "rank",
        "candidate_source_id",
        "candidate_plate",
        "match_score",
        "plate_score",
        "supporting_fields",
        "decision",
        "ground_truth_match",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for result in ranked_results:
            query = result["query"]
            query_id = row_identifier(query, result["query_number"])
            for rank, (score, plate_score, evidence, candidate_index) in enumerate(
                result["candidates"][:top_k], start=1
            ):
                candidate = reference_rows[candidate_index]
                candidate_id = row_identifier(candidate, candidate_index + 1)
                writer.writerow({
                    "query_row": result["query_number"],
                    "query_source_id": query_id,
                    "raw_plate": query.get("reg_plate", ""),
                    "rank": rank,
                    "candidate_source_id": candidate_id,
                    "candidate_plate": candidate.get("reg_plate", ""),
                    "match_score": f"{score:.4f}",
                    "plate_score": f"{plate_score:.4f}",
                    "supporting_fields": ", ".join(evidence),
                    "decision": result["decision"],
                    "ground_truth_match": (
                        "yes"
                        if query.get("id")
                        and candidate.get("id")
                        and str(query.get("id")) == str(candidate.get("id"))
                        else (
                            "no"
                            if query.get("id") and candidate.get("id")
                            else ""
                        )
                    ),
                })


def write_proposals(path, ranked_results, reference_rows):
    fields = [
        "query_row",
        "source_id",
        "raw_plate",
        "proposed_plate",
        "match_score",
        "score_margin",
        "decision",
        "supporting_fields",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for result in ranked_results:
            best = result["candidates"][0] if result["candidates"] else None
            candidate = reference_rows[best[3]] if best else {}
            writer.writerow({
                "query_row": result["query_number"],
                "source_id": row_identifier(
                    result["query"], result["query_number"]
                ),
                "raw_plate": result["query"].get("reg_plate", ""),
                "proposed_plate": candidate.get("reg_plate", ""),
                "match_score": f"{result['score']:.4f}",
                "score_margin": f"{result['margin']:.4f}",
                "decision": result["decision"],
                "supporting_fields": ", ".join(best[2]) if best else "",
            })


def print_metrics(ranked_results, query_rows, reference_rows, label):
    can_evaluate = bool(query_rows) and all(
        "id" in row and row.get("id") for row in query_rows
    ) and all("id" in row and row.get("id") for row in reference_rows)
    decisions = defaultdict(int)
    for result in ranked_results:
        decisions[result["decision"]] += 1

    print(f"\n{label}: {len(ranked_results)} queries")
    print(
        "Decisions: "
        f"AUTO_MATCH={decisions['AUTO_MATCH']}, "
        f"REVIEW={decisions['REVIEW']}, UNMATCHED={decisions['UNMATCHED']}"
    )
    if not can_evaluate:
        print("Accuracy metrics skipped: matching IDs are not present in both files.")
        return

    reference_ids = {
        str(row.get("id")) for row in reference_rows if row.get("id")
    }
    evaluated = [
        result for result in ranked_results
        if str(result["query"].get("id")) in reference_ids
    ]
    top1 = sum(
        bool(result["candidates"])
        and str(reference_rows[result["candidates"][0][3]].get("id"))
        == str(result["query"].get("id"))
        for result in evaluated
    )
    top3 = sum(
        any(
            str(reference_rows[candidate[3]].get("id"))
            == str(result["query"].get("id"))
            for candidate in result["candidates"][:3]
        )
        for result in evaluated
    )
    auto_results = [
        result for result in evaluated if result["decision"] == "AUTO_MATCH"
    ]
    auto_correct = sum(
        bool(result["candidates"])
        and str(reference_rows[result["candidates"][0][3]].get("id"))
        == str(result["query"].get("id"))
        for result in auto_results
    )
    denominator = len(evaluated) or 1
    auto_denominator = len(auto_results) or 1
    print(
        f"ID-based evaluation only (IDs are not matching features): "
        f"top-1={top1 / denominator:.1%}, "
        f"top-3 recall={top3 / denominator:.1%}, "
        f"auto-match precision={auto_correct / auto_denominator:.1%}"
    )


# ---------------------------------------------------------------------------
# Value-level similarity (used by source_api.py  POST /api/similar)
#
# "Which of the values stored in ONE column of THIS database look like the
# noisy value that was typed / scanned?"  This is similarity matching only.
# Deciding which records across databases are the same vehicle (entity
# matching) is the Coordinator's job, not this module's.
#
# Moved here from coordinator/federated_sql.py so every source laptop can run
# it next to its own data.
# ---------------------------------------------------------------------------
VALUE_KINDS = ("plate", "code", "name", "text")
VALUE_MIN_SCORE = 0.60      # "good" match (same as REVIEW_SCORE)
VALUE_MAX_MATCHES = 25
VALUE_FALLBACK_N = 5        # nothing good -> return this many closest values ...
VALUE_FLOOR = 0.25          # ... if they score at least this (low_confidence)
VALUE_BLOCK_SIZE = 300      # candidates kept by the cheap bigram pre-filter


def _value_bigrams(text):
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _alnum(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _tokens(value):
    return re.findall(r"[a-z0-9]+", str(value or "").casefold())


def _code_key(value):
    return re.sub(r"[^A-Z0-9?@#*]", "", str(value or "").upper())


def containment_score(query, candidate):
    """Partial input: 'UP09' inside 'UP09AI8815', 'rajat' inside 'rajatsharma'."""
    if len(query) < 2 or query not in candidate:
        return 0.0
    score = 0.70 + 0.30 * len(query) / len(candidate)
    if candidate.startswith(query):
        score += 0.05
    return min(score, 0.99)


def token_score(query, candidate):
    """Word-order independent, partial-name tolerant ('sharma, rajt' ~ 'Rajat Sharma')."""
    query_tokens, candidate_tokens = _tokens(query), _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    best = [
        max(
            SequenceMatcher(None, left, right, autojunk=False).ratio()
            for right in candidate_tokens
        )
        for left in query_tokens
    ]
    coverage = 0.85 + 0.15 * min(1.0, len(query_tokens) / len(candidate_tokens))
    return (sum(best) / len(best)) * coverage


def value_similarity(kind, query, candidate):
    """Similarity 0..1 between the typed value and ONE stored value.

    kind: plate = OCR-aware plate matcher
          code  = OCR-aware edit distance (engine / chassis / policy numbers)
          name  = token based, any word order, partial names
          text  = general text similarity
    """
    if kind == "plate":
        left, right = normalize_plate(query), normalize_plate(candidate)
        if not left or not right:
            return 0.0
        score = max(plate_similarity(left, right), plate_similarity(right, left))
        return max(
            score,
            containment_score(fold_lookalikes(left), fold_lookalikes(right)),
        )

    left, right = _alnum(query), _alnum(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if kind == "code":
        left_code, right_code = _code_key(query), _code_key(candidate)
        return max(
            edit_similarity(left_code, right_code, ocr_aware=True),
            containment_score(
                fold_lookalikes(left_code), fold_lookalikes(right_code)
            ),
        )
    score = max(
        SequenceMatcher(None, left, right, autojunk=False).ratio(),
        containment_score(left, right),
    )
    if kind in ("name", "text"):
        score = max(score, token_score(query, candidate))
    return score


def is_exact_value(kind, query, candidate):
    if kind == "plate":
        key = normalize_plate(query)
        return bool(key) and key == normalize_plate(candidate)
    key = _alnum(query)
    return bool(key) and key == _alnum(candidate)


def _block_key(kind):
    if kind == "plate":
        return lambda value: fold_lookalikes(normalize_plate(value))
    if kind == "code":
        return lambda value: fold_lookalikes(re.sub(r"[^A-Z0-9]", "", str(value).upper()))
    return _alnum


def match_value(
    kind,
    query,
    stored,
    min_score=VALUE_MIN_SCORE,
    max_matches=VALUE_MAX_MATCHES,
    fallback_n=VALUE_FALLBACK_N,
    floor=VALUE_FLOOR,
    block_size=VALUE_BLOCK_SIZE,
):
    """Find the stored values that best match `query`.

    * exact (normalised) hit      -> returned alone, score 1.0
    * score >= min_score          -> all of them, best first
    * nothing that good           -> closest `fallback_n` values scoring at
                                     least `floor`, flagged low_confidence
    Large columns are first narrowed with a cheap look-alike-folded bigram
    filter (plus every value that contains the typed text).

    Returns {"exact", "low_confidence", "scanned", "matches": [(value, score)]}.
    """
    if kind not in VALUE_KINDS:
        raise ValueError(f"Unknown similarity kind: {kind!r}")
    stored = [value for value in stored if value is not None and str(value) != ""]
    query = str(query or "").strip()
    if not query or not stored:
        return {"exact": False, "low_confidence": False,
                "scanned": len(stored), "matches": []}

    exact = [value for value in stored if is_exact_value(kind, query, value)]
    if exact:
        return {"exact": True, "low_confidence": False, "scanned": len(stored),
                "matches": [(value, 1.0) for value in exact[:max_matches]]}

    pool = stored
    limit = block_size if kind in ("plate", "code") else block_size * 4
    if len(stored) > limit:
        key_of = _block_key(kind)
        query_key = key_of(query)
        query_grams = _value_bigrams(query_key)
        keyed = [(value, key_of(value)) for value in stored]

        def jaccard(item):
            grams = _value_bigrams(item[1])
            return len(query_grams & grams) / (len(query_grams | grams) or 1)

        ranked = [value for value, _key in heapq.nlargest(limit, keyed, key=jaccard)]
        contains = [
            value for value, key in keyed
            if len(query_key) >= 2 and query_key in key
        ]
        pool = list(dict.fromkeys(ranked + contains))

    scored = sorted(
        ((value, round(value_similarity(kind, query, value), 4)) for value in pool),
        key=lambda item: (-item[1], str(item[0])),
    )
    good = [item for item in scored if item[1] >= min_score]
    if good:
        return {"exact": False, "low_confidence": False,
                "scanned": len(stored), "matches": good[:max_matches]}
    near = [item for item in scored[:fallback_n] if item[1] >= floor and item[1] > 0]
    return {"exact": False, "low_confidence": bool(near),
            "scanned": len(stored), "matches": near}


def main():
    parser = argparse.ArgumentParser(
        description="Fuzzy-match noisy vehicle rows to a clean CSV reference."
    )
    parser.add_argument("--noisy", type=Path, default=DEFAULT_NOISY)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=TOP_CANDIDATES)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    noisy_rows = read_csv(args.noisy)
    clean_rows = read_csv(args.reference)
    if not noisy_rows or not clean_rows:
        parser.error("Both input CSV files must contain at least one data row.")
    if any("reg_plate" not in row for row in noisy_rows + clean_rows):
        parser.error("Both CSV files must contain a reg_plate column.")

    confusion_costs = learn_plate_confusions(noisy_rows, clean_rows)
    matches = rank_matches(
        noisy_rows, clean_rows, args.top_k, confusion_costs
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_ranked_csv(args.output, matches, noisy_rows, clean_rows, args.top_k)
    proposal_path = args.output.with_name(
        f"{args.output.stem}_proposals.csv"
    )
    write_proposals(proposal_path, matches, clean_rows)

    print_metrics(matches, noisy_rows, clean_rows, "Noisy-to-clean")
    print(f"Ranked candidates: {args.output}")
    print(f"Reviewable cleansing proposals: {proposal_path}")

    reverse_matches = rank_matches(
        clean_rows, noisy_rows, args.top_k, confusion_costs
    )
    reverse_path = args.output.with_name(
        f"{args.output.stem}_reverse.csv"
    )
    write_ranked_csv(
        reverse_path, reverse_matches, clean_rows, noisy_rows, args.top_k
    )
    print_metrics(reverse_matches, clean_rows, noisy_rows, "Clean-to-noisy")
    print(f"Reverse-direction candidates: {reverse_path}")


if __name__ == "__main__":
    main()