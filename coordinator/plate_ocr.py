"""Local license-plate text extraction using PaddleOCR.

PaddleOCR detects text in the uploaded image and reads it locally. Candidate
text is normalized and ranked here, then still requires human review before
searching or appending a vehicle.
"""

import re
import unicodedata

from werkzeug.datastructures import FileStorage

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_CANDIDATES = 10  # internal ranking depth
MAX_RESULTS = 3
IMAGE_SIGNATURES = {
    "jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "heic": lambda data: (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1")
    ),
}
PLATE_TEXT_PATTERN = re.compile(
    r"^[A-Z]{2}[0-9ODQILZSGBAT]{1,2}[A-Z0-9?@#*]{1,3}"
    r"[0-9ODQILZSGBAT?@#*]{1,4}$"
)
OCR_HOMOGLYPHS = str.maketrans({
    "А": "A",
    "В": "B",
    "Е": "E",
    "К": "K",
    "М": "M",
    "Н": "H",
    "О": "O",
    "Р": "P",
    "С": "C",
    "Т": "T",
    "Х": "X",
    "У": "Y",
    "І": "I",
    "Ј": "J",
})
OCR_CONFUSION_CLASSES = (
    frozenset("0OQD"),
    frozenset("1IL"),
    frozenset("2Z"),
    frozenset("5S"),
    frozenset("6G"),
    frozenset("8B"),
    frozenset("4A"),
    frozenset("7T"),
)
# Characters the OCR commonly swaps inside the two-letter state prefix.
PREFIX_ALTERNATES = {
    "0": "OD", "O": "D0Q", "D": "O0", "Q": "O",
    "1": "IL", "I": "1L", "L": "I1",
    "2": "Z", "Z": "2",
    "5": "S", "S": "5",
    "6": "G", "G": "6C",
    "8": "B", "B": "8",
    "4": "A", "A": "4",
    "7": "T", "T": "7",
    "M": "NH", "N": "MH", "H": "MN",
    "U": "V", "V": "U",
    "P": "R", "R": "P",
    "K": "X", "X": "K",
    "C": "GO", "E": "F", "F": "E",
}
SUPPORT_WEIGHT = 0.8
SUPPORT_CAP = 8
CONFIDENCE_WEIGHT = 3.0
STATE_PREFIX_BONUS = 1.5
MIN_ALTERNATE_VOTE_RATIO = 0.5  # alternates need >= half the best's votes
MAX_ALTERNATES = 2  # best reading + at most this many alternatives
CONSENSUS_MIN_VARIANTS = 3
CONSENSUS_MIN_CONFIDENCE = 0.2

class PlateOCRInputError(ValueError):
    """The uploaded image is not supported or contains no readable plate text."""


class PlateOCREngineError(RuntimeError):
    """PaddleOCR could not run successfully."""


_state_prefix_cache = None


def _state_prefixes():
    """State prefixes from input_repair, loaded lazily (empty if unavailable)."""
    global _state_prefix_cache
    if _state_prefix_cache is None:
        try:
            from input_repair import STATE_PREFIXES

            _state_prefix_cache = frozenset(
                str(prefix).upper() for prefix in STATE_PREFIXES
            )
        except Exception:
            _state_prefix_cache = frozenset()
    return _state_prefix_cache


def _image_format(data):
    for image_format, matches in IMAGE_SIGNATURES.items():
        if matches(data):
            return image_format
    return None


def _clean_candidate(text):
    text = unicodedata.normalize("NFKD", str(text).upper())
    text = text.translate(OCR_HOMOGLYPHS)
    return "".join(
        character
        for character in text
        if not unicodedata.combining(character)
        and (character.isalnum() or character in "?@#*")
    )


def _fix_state_prefix(candidate):
    """Repair a misread state prefix (e.g. '0D12..' -> 'OD12..')."""
    states = _state_prefixes()
    if not states or len(candidate) < 5 or candidate[:2] in states:
        return candidate
    first_options = [candidate[0], *PREFIX_ALTERNATES.get(candidate[0], "")]
    second_options = [candidate[1], *PREFIX_ALTERNATES.get(candidate[1], "")]
    best = None
    for first in first_options:
        for second in second_options:
            prefix = first + second
            if prefix not in states:
                continue
            changes = (first != candidate[0]) + (second != candidate[1])
            if best is None or changes < best[0]:
                best = (changes, prefix)
    return best[1] + candidate[2:] if best else candidate


def _plate_text_candidates(text):
    compact = _clean_candidate(text)
    matches = {}
    if any(character.isspace() for character in str(text)):
        for start in range(len(compact)):
            for end in range(start + 5, min(start + 17, len(compact) + 1)):
                candidate = compact[start:end]
                _record_with_state_fix(matches, candidate)
    _record_with_state_fix(matches, compact)

    return {
        candidate: score
        for candidate, score in matches.items()
        if not any(
            candidate != other
            and candidate in other
            and other_score >= score
            for other, other_score in matches.items()
        )
    }


def _record_with_state_fix(matches, candidate):
    _record_candidate(matches, candidate)
    fixed = _fix_state_prefix(candidate)
    if fixed != candidate:
        _record_candidate(matches, fixed)


def _record_candidate(matches, candidate):
    if not _looks_like_plate_text(candidate):
        return
    score = _plate_format_score(candidate)
    if score is not None and score <= 0:
        return
    if score is None and not _looks_like_generic_plate(candidate):
        return

    normalized_score = -1 if score is None else score
    matches[candidate] = max(
        normalized_score,
        matches.get(candidate, normalized_score),
    )
    corrected_candidates = (
        [
            (corrected, _plate_format_score(corrected))
            for corrected in _correct_plate_confusions(candidate)
        ]
        if len(candidate) >= 8
        else []
    )
    corrected_candidates = [
        (corrected, corrected_score)
        for corrected, corrected_score in corrected_candidates
        if corrected_score is not None and corrected_score > 0
    ]
    if corrected_candidates:
        corrected, corrected_score = min(
            corrected_candidates,
            key=lambda item: (
                -item[1],
                sum(a != b for a, b in zip(candidate, item[0])),
                item[0],
            ),
        )
        matches[corrected] = max(
            corrected_score,
            matches.get(corrected, corrected_score),
        )


def _looks_like_generic_plate(candidate):
    groups = re.findall(r"[A-Z]+|[0-9]+", candidate)
    return (
        len(candidate) >= 2
        and candidate[:2].isalpha()
        and 2 <= sum(character.isdigit() for character in candidate)
        and len(groups) <= 4
        and max(
            (len(group) for group in groups if group.isalpha()),
            default=0,
        ) <= 4
    )


def _correct_plate_confusions(candidate):
    digit_for_confusion = {
        "O": "0", "Q": "0", "D": "0",
        "I": "1", "L": "1",
        "Z": "2", "S": "5", "G": "6",
        "B": "8", "A": "4", "T": "7",
    }
    letter_for_confusion = {
        "0": "O", "1": "I", "2": "Z", "5": "S",
        "6": "G", "8": "B", "4": "A", "7": "T",
    }
    corrected = set()
    for district_length in (1, 2):
        district_start = 2
        series_start = district_start + district_length
        for series_length in (1, 2, 3):
            number_start = series_start + series_length
            if not 1 <= len(candidate) - number_start <= 4:
                continue
            chars = list(candidate)
            for position in range(district_start, series_start):
                chars[position] = digit_for_confusion.get(
                    chars[position], chars[position]
                )
            for position in range(series_start, number_start):
                chars[position] = letter_for_confusion.get(
                    chars[position], chars[position]
                )
            for position in range(number_start, len(candidate)):
                chars[position] = digit_for_confusion.get(
                    chars[position], chars[position]
                )
            corrected.add("".join(chars))
    return corrected


def _looks_like_plate_text(candidate):
    if not 5 <= len(candidate) <= 16:
        return False
    if sum(character.isalpha() for character in candidate) < 2:
        return False
    if max(
        (
            len(match.group())
            for match in re.finditer(r"[A-Z]+", candidate)
        ),
        default=0,
    ) > 4:
        return False
    digit_like_count = sum(
        character.isdigit()
        or any(character in group for group in OCR_CONFUSION_CLASSES)
        or character in "?@#*"
        for character in candidate
    )
    return digit_like_count >= 2


def _plate_format_score(candidate):
    if len(candidate) < 2 or not candidate[:2].isalpha():
        return None
    best_score = None
    for district_length in (1, 2):
        district_end = 2 + district_length
        district = candidate[2:district_end]
        if not any(
            character.isdigit()
            or any(character in group for group in OCR_CONFUSION_CLASSES)
            for character in district
        ):
            continue
        for series_length in (1, 2, 3):
            series_end = district_end + series_length
            series = candidate[district_end:series_end]
            number = candidate[series_end:]
            if not 1 <= len(number) <= 4:
                continue
            if not any(
                character.isdigit()
                or any(character in group for group in OCR_CONFUSION_CLASSES)
                for character in number
            ):
                continue
            errors = sum(character.isdigit() for character in series)
            errors += sum(
                not character.isdigit()
                and not any(
                    character in group
                    for group in OCR_CONFUSION_CLASSES
                )
                for character in district + number
            )
            score = len(number) - (2 * errors)
            if best_score is None or score > best_score:
                best_score = score
    return best_score


def _consensus_plates(observations):
    """Character-by-character weighted vote across same-length readings.

    observations: iterable of (plate, weight, variant).  Returns
    {consensus_plate: {variant: confidence}} for groups with enough
    independent variants to make a vote meaningful.
    """
    by_length = {}
    for plate, weight, variant in observations:
        by_length.setdefault(len(plate), []).append((plate, weight, variant))

    results = {}
    for length, group in by_length.items():
        variants = {variant for _plate, _weight, variant in group}
        if (
            len({plate for plate, _weight, _variant in group}) < 2
            or len(variants) < CONSENSUS_MIN_VARIANTS
        ):
            continue
        chars = []
        for position in range(length):
            tally = {}
            for plate, weight, _variant in group:
                tally[plate[position]] = (
                    tally.get(plate[position], 0.0) + weight
                )
            chars.append(
                max(tally.items(), key=lambda item: (item[1], item[0]))[0]
            )
        consensus = "".join(chars)
        supporters = {}
        for plate, weight, variant in group:
            supporters[variant] = max(supporters.get(variant, 0.0), weight)
        results[consensus] = supporters
    return results


def _entry_score(entry):
    support = len(entry["variants"])
    mean_confidence = sum(entry["variants"].values()) / max(support, 1)
    score = (
        entry["format_score"]
        + SUPPORT_WEIGHT * min(support, SUPPORT_CAP)
        + CONFIDENCE_WEIGHT * mean_confidence
    )
    if entry["plate"][:2] in _state_prefixes():
        score += STATE_PREFIX_BONUS
    return score


def _prune_alternatives(ordered):
    """Keep the best reading plus only well-supported, distinct alternatives.

    Drops readings that merely contain the best plate with extra characters
    (e.g. the 'IND' badge read together with the plate) or are a fragment of
    it, and readings seen in far fewer image variants than the best one.
    """
    if not ordered:
        return ordered
    best = ordered[0]
    best_plate = best["plate"]
    minimum_votes = max(2, int(len(best["variants"]) * MIN_ALTERNATE_VOTE_RATIO))
    kept = [best]
    for entry in ordered[1:]:
        plate = entry["plate"]
        if best_plate in plate or plate in best_plate:
            continue
        if len(entry["variants"]) < minimum_votes:
            continue
        kept.append(entry)
        if len(kept) >= MAX_ALTERNATES + 1:
            break
    return kept


def rank_ocr_candidates(raw_candidates, limit=MAX_CANDIDATES):
    ranked = {}
    observations = []
    for index, item in enumerate(raw_candidates):
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= confidence <= 1.0:
            continue
        variant = str(item.get("variant") or f"read-{index}")
        for text, format_score in _plate_text_candidates(
            item.get("text", "")
        ).items():
            entry = ranked.setdefault(text, {
                "plate": text,
                "confidence": 0.0,
                "format_score": format_score,
                "variants": {},
            })
            entry["format_score"] = max(entry["format_score"], format_score)
            entry["confidence"] = max(entry["confidence"], confidence)
            entry["variants"][variant] = max(
                entry["variants"].get(variant, 0.0), confidence
            )
            if format_score > 0 and confidence >= CONSENSUS_MIN_CONFIDENCE:
                observations.append((
                    text,
                    confidence * (1 + format_score / 4),
                    variant,
                ))

    for consensus, supporters in _consensus_plates(observations).items():
        format_score = _plate_format_score(consensus)
        if format_score is None or format_score <= 0:
            continue
        entry = ranked.setdefault(consensus, {
            "plate": consensus,
            "confidence": 0.0,
            "format_score": format_score,
            "variants": {},
        })
        mean_confidence = sum(
            min(weight, 1.0) for weight in supporters.values()
        ) / len(supporters)
        entry["confidence"] = max(entry["confidence"], mean_confidence)
        for variant in supporters:
            entry["variants"].setdefault(variant, mean_confidence)

    ordered = _prune_alternatives(sorted(
        ranked.values(),
        key=lambda item: (
            -_entry_score(item),
            -item["confidence"],
            -len(item["plate"]),
            item["plate"],
        ),
    ))[:limit]

    # Agreement-based confidence: a plate read the same way in most image
    # variants is trustworthy; a single 100% read among many is not.
    all_variants = {
        variant
        for entry in ranked.values()
        if entry["format_score"] > 0
        for variant in entry["variants"]
    }
    total_variants = max(len(all_variants), 1)
    results = []
    for item in ordered:
        votes = len(item["variants"])
        mean_confidence = sum(item["variants"].values()) / max(votes, 1)
        agreement = min(votes / total_variants, 1.0)
        results.append({
            "plate": item["plate"],
            "confidence": round(min(mean_confidence, 1.0) * agreement, 4),
            "ocr_confidence": item["confidence"],
            "votes": votes,
            "variants_total": total_variants,
        })
    return results


def recognize_plate_image(upload: FileStorage):
    """Run PaddleOCR on a validated image without persisting the upload."""
    data = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise PlateOCRInputError("Image must be 8 MB or smaller.")
    image_format = _image_format(data)
    if image_format is None:
        raise PlateOCRInputError(
            "Upload a valid JPEG, PNG, or HEIC image."
        )

    # Import separately from inference. If importing paddle_plate_reader fails,
    # PaddleOCRError would otherwise be unbound in the `except` clause and mask
    # the real import/dependency error with UnboundLocalError.
    try:
        from paddle_plate_reader import (
            PaddleOCRError,
            read_plate_with_paddle_ocr,
        )
    except ImportError as error:
        raise PlateOCREngineError(
            f"Could not import paddle_plate_reader or one of its dependencies: {error}"
        ) from error

    try:
        raw_candidates = read_plate_with_paddle_ocr(data, image_format)
    except PaddleOCRError as error:
        raise PlateOCREngineError(f"PaddleOCR failed: {error}") from error

    candidates = rank_ocr_candidates([
        {
            "text": item["text"],
            "confidence": item["confidence"],
            "variant": "paddleocr",
        }
        for item in raw_candidates
    ])
    if not candidates:
        raise PlateOCRInputError(
            "PaddleOCR found no plate-like text. Try a clearer image with the "
            "plate visible and readable."
        )
    for candidate in candidates:
        candidate["source"] = "paddleocr"
        candidate["needs_review"] = True
    return candidates[:MAX_RESULTS]