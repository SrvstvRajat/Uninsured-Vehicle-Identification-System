"""
Position-aware correction for Indian vehicle registration plates.

Plate layout:  LL DD L{1,3} DDDD
               |  |  |      |
               |  |  |      +-- unique number (4 digits)
               |  |  +--------- series letters (1 to 3 letters)
               |  +------------ RTO / district code (2 digits)
               +--------------- state / UT code (2 letters)

Every position is either a LETTER slot or a DIGIT slot. A character that does
not belong in its slot is converted to its nearest look-alike for that slot,
e.g. S->5 / O->0 in digit slots and 5->S / 0->O in letter slots.
"""

import re

# Valid Indian state / UT codes (used only to flag whether the state part is plausible)
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

# Character found in a DIGIT slot -> nearest digit
TO_DIGIT = {
    "O": "0", "Q": "0", "D": "0", "U": "0", "@": "0",
    "I": "1", "L": "1", "|": "1", "!": "1",
    "Z": "2",
    "A": "4",
    "S": "5", "$": "5",
    "G": "6",
    "T": "7", "?": "7",
    "B": "8", "&": "8",
}

# Character found in a LETTER slot -> nearest letter
TO_LETTER = {
    "0": "O", "1": "I", "2": "Z", "4": "A", "5": "S",
    "6": "G", "7": "T", "8": "B",
    "$": "S", "&": "B", "@": "A", "|": "I", "!": "I", "?": "T",
}


def correct_plate(raw):
    """
    Position-aware correction of an Indian registration plate.

    Returns a dict:
        original   - value exactly as entered (never modified)
        cleaned    - after removing spaces/hyphens/dots and uppercasing
        corrected  - fully corrected plate, or None if it cannot be fitted
        changes    - list of (index, from_char, to_char, slot_type)
        valid      - True if corrected fits the pattern and the state code is known
    """
    original = raw or ""
    cleaned = re.sub(r"[\s\-.]", "", original.upper())

    result = {
        "original": original,
        "cleaned": cleaned,
        "corrected": None,
        "changes": [],
        "valid": False,
    }

    s = cleaned
    if not 9 <= len(s) <= 11:
        # Maybe stray punctuation was inserted; try dropping non-alphanumerics.
        stripped = re.sub(r"[^A-Z0-9]", "", s)
        if 9 <= len(stripped) <= 11:
            s = stripped
        else:
            return result

    series_len = len(s) - 8                       # 1, 2 or 3 series letters
    layout = "LLDD" + "L" * series_len + "DDDD"

    out, changes = [], []
    for i, (ch, slot) in enumerate(zip(s, layout)):
        if slot == "L":
            new = ch if ch.isalpha() else TO_LETTER.get(ch)
        else:
            new = ch if ch.isdigit() else TO_DIGIT.get(ch)

        if new is None:                           # unknown symbol, cannot fix safely
            return result
        if new != ch:
            changes.append((i, ch, new, "letter" if slot == "L" else "digit"))
        out.append(new)

    corrected = "".join(out)
    result["corrected"] = corrected
    result["changes"] = changes
    result["valid"] = corrected[:2] in STATE_CODES
    return result


if __name__ == "__main__":
    # Quick self-test
    for sample in ["UP&8oBqSs44", "up 80 bq 5544", "MH12AB1234", "DL1CA0O12"]:
        r = correct_plate(sample)
        print(f"{sample!r:>16} -> {r['corrected']}  valid={r['valid']}  changes={r['changes']}")
