# """
# Position-aware correction for Indian vehicle registration plates.

# Plate layout:  LL DD L{1,3} DDDD
#                |  |  |      |
#                |  |  |      +-- unique number (4 digits)
#                |  |  +--------- series letters (1 to 3 letters)
#                |  +------------ RTO / district code (2 digits)
#                +--------------- state / UT code (2 letters)

# Every position is either a LETTER slot or a DIGIT slot. A character that does
# not belong in its slot is converted to its nearest look-alike for that slot,
# e.g. S->5 / O->0 in digit slots and 5->S / 0->O in letter slots.
# """

# import re

# # Valid Indian state / UT codes (used only to flag whether the state part is plausible)
# STATE_CODES = {
#     "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ",
#     "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
#     "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
#     "UP", "WB",
# }

# # Character found in a DIGIT slot -> nearest digit
# TO_DIGIT = {
#     "O": "0", "Q": "0", "D": "0", "U": "0", "@": "0",
#     "I": "1", "L": "1", "|": "1", "!": "1",
#     "Z": "2",
#     "A": "4",
#     "S": "5", "$": "5",
#     "G": "6",
#     "T": "7", "?": "7",
#     "B": "8", "&": "8",
# }

# # Character found in a LETTER slot -> nearest letter
# TO_LETTER = {
#     "0": "O", "1": "I", "2": "Z", "4": "A", "5": "S",
#     "6": "G", "7": "T", "8": "B",
#     "$": "S", "&": "B", "@": "A", "|": "I", "!": "I", "?": "T",
# }


# def correct_plate(raw):
#     """
#     Position-aware correction of an Indian registration plate.

#     Returns a dict:
#         original   - value exactly as entered (never modified)
#         cleaned    - after removing spaces/hyphens/dots and uppercasing
#         corrected  - fully corrected plate, or None if it cannot be fitted
#         changes    - list of (index, from_char, to_char, slot_type)
#         valid      - True if corrected fits the pattern and the state code is known
#     """
#     original = raw or ""
#     cleaned = re.sub(r"[\s\-.]", "", original.upper())

#     result = {
#         "original": original,
#         "cleaned": cleaned,
#         "corrected": None,
#         "changes": [],
#         "valid": False,
#     }

#     s = cleaned
#     if not 9 <= len(s) <= 11:
#         # Maybe stray punctuation was inserted; try dropping non-alphanumerics.
#         stripped = re.sub(r"[^A-Z0-9]", "", s)
#         if 9 <= len(stripped) <= 11:
#             s = stripped
#         else:
#             return result

#     series_len = len(s) - 8                       # 1, 2 or 3 series letters
#     layout = "LLDD" + "L" * series_len + "DDDD"

#     out, changes = [], []
#     for i, (ch, slot) in enumerate(zip(s, layout)):
#         if slot == "L":
#             new = ch if ch.isalpha() else TO_LETTER.get(ch)
#         else:
#             new = ch if ch.isdigit() else TO_DIGIT.get(ch)

#         if new is None:                           # unknown symbol, cannot fix safely
#             return result
#         if new != ch:
#             changes.append((i, ch, new, "letter" if slot == "L" else "digit"))
#         out.append(new)

#     corrected = "".join(out)
#     result["corrected"] = corrected
#     result["changes"] = changes
#     result["valid"] = corrected[:2] in STATE_CODES
#     return result


# if __name__ == "__main__":
#     # Quick self-test
#     for sample in ["UP&8oBqSs44", "up 80 bq 5544", "MH12AB1234", "DL1CA0O12"]:
#         r = correct_plate(sample)
#         print(f"{sample!r:>16} -> {r['corrected']}  valid={r['valid']}  changes={r['changes']}")

"""
Position-aware correction for Indian vehicle registration plates.

Plate layout:  LL DD L{1,3} DDDD
               |  |  |      |
               |  |  |      +-- unique number (4 digits)
               |  |  +--------- series letters (1 to 3 letters)
               |  +------------ RTO / district code (2 digits)
               +--------------- state / UT code (2 letters)

Every position is either a LETTER slot or a DIGIT slot.
  * A letter found in a DIGIT slot becomes its nearest look-alike digit (S->5, T->7, A->4 ...).
  * A digit found in a LETTER slot becomes its nearest look-alike letter (0->O, 5->S ...).
  * A special character is converted according to the slot it sits in
    (e.g. '&' -> 8 in a digit slot, '&' -> B in a letter slot).

Each character maps to an ORDERED list of look-alikes. The first one is used for
the primary correction; the others are used to build alternative variants that
the app ranks against the real database.
"""

import re

# Valid Indian state / UT codes (used only to flag whether the state part is plausible)
STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ",
    "HP", "HR", "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP",
    "MZ", "NL", "OD", "OR", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK",
    "UP", "WB",
}

# ---------------------------------------------------------------------------
# Character found in a DIGIT slot -> look-alike digits (best guess first)
# ---------------------------------------------------------------------------
TO_DIGIT = {
    # letters
    "A": ["4"],          "B": ["8"],          "C": ["0"],
    "D": ["0"],          "E": ["3"],          "F": ["7", "4"],
    "G": ["6"],          "H": ["4"],          "I": ["1"],
    "J": ["1"],          "K": ["4"],          "L": ["1"],
    "M": ["4"],          "N": ["1"],          "O": ["0"],
    "P": ["9"],          "Q": ["0"],          "R": ["2", "8"],
    "S": ["5"],          "T": ["7"],          "U": ["0"],
    "V": ["7"],          "W": ["1"],          "X": ["4"],
    "Y": ["7"],          "Z": ["2"],
    # special characters
    "@": ["0", "8", "9"], "&": ["8", "6", "0"], "$": ["5"],
    "%": ["9", "0", "8"], "#": ["4", "7"],      "!": ["1"],
    "|": ["1"],           "?": ["7", "2"],      "*": ["8", "4"],
    "/": ["1", "7"],      "\\": ["1"],          "(": ["0", "6"],
    ")": ["0", "1"],      "[": ["1", "0"],      "]": ["1", "0"],
    "{": ["1", "0"],      "}": ["1", "0"],      "+": ["4", "7"],
    "=": ["3", "5"],      "<": ["4", "6"],      ">": ["7", "2"],
    "^": ["4", "7"],      "~": ["2", "7"],      "_": ["1", "2"],
    ":": ["1"],           ";": ["1"],           ",": ["1"],
    "'": ["1"],           '"': ["1"],           "`": ["1"],
}

# ---------------------------------------------------------------------------
# Character found in a LETTER slot -> look-alike letters (best guess first)
# ---------------------------------------------------------------------------
TO_LETTER = {
    # digits
    "0": ["O", "D", "Q"], "1": ["I", "L"], "2": ["Z"],      "3": ["E"],
    "4": ["A"],           "5": ["S"],      "6": ["G"],      "7": ["T"],
    "8": ["B"],           "9": ["P", "G"],
    # special characters
    "@": ["A", "O"],      "&": ["B", "S"], "$": ["S"],      "%": ["X", "O", "S"],
    "#": ["H", "M"],      "!": ["I"],      "|": ["I", "L"], "?": ["T", "Z"],
    "*": ["X", "K"],      "/": ["I", "L"], "\\": ["I", "L"],"(": ["C", "O"],
    ")": ["O", "D"],      "[": ["C", "L"], "]": ["I", "J"], "{": ["C", "L"],
    "}": ["I", "J"],      "+": ["T", "X"], "=": ["E", "S"], "<": ["K", "C"],
    ">": ["X", "V"],      "^": ["A", "V"], "~": ["N", "Z"], "_": ["L", "U"],
    ":": ["I"],           ";": ["I"],      ",": ["I"],      "'": ["I"],
    '"': ["I"],           "`": ["I"],
}

# Fallbacks so that no unknown character ever blocks a correction
DEFAULT_DIGIT = "0"
DEFAULT_LETTER = "X"

MAX_VARIANTS = 25

# A plate that already looks valid (1-2 digit district, 1-4 digit number) is left alone,
# so genuine plates such as DL1CAB1234 are never "corrected" into something else.
PLATE_PATTERN = r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}"


def _options_for(ch, slot):
    """Return the ordered list of acceptable characters for `ch` in `slot`."""
    if slot == "L":
        if ch.isalpha():
            return [ch]
        return TO_LETTER.get(ch, [DEFAULT_LETTER])
    if ch.isdigit():
        return [ch]
    return TO_DIGIT.get(ch, [DEFAULT_DIGIT])


def correct_plate(raw):
    """
    Position-aware correction of an Indian registration plate.

    Returns a dict:
        original   - value exactly as entered (never modified)
        cleaned    - after removing spaces/hyphens/dots and uppercasing
        pattern_ok - True if `cleaned` already matches LL DD L{1,3} DDDD
        corrected  - primary corrected plate, or None if length cannot fit a plate
        variants   - primary plus alternative corrections (for database matching)
        changes    - list of (index, from_char, to_char, slot_type)
        valid      - True if corrected fits the pattern and the state code is known
        layout     - slot layout used, e.g. 'LLDDLLDDDD'
    """
    original = raw or ""
    cleaned = re.sub(r"[\s\-.]", "", original.upper())

    result = {
        "original": original,
        "cleaned": cleaned,
        "pattern_ok": bool(re.fullmatch(PLATE_PATTERN, cleaned)),
        "corrected": None,
        "variants": [],
        "changes": [],
        "valid": False,
        "layout": "",
    }

    if result["pattern_ok"]:
        result["corrected"] = cleaned
        result["variants"] = [cleaned]
        result["valid"] = cleaned[:2] in STATE_CODES
        return result

    s = cleaned
    if not 9 <= len(s) <= 11:
        # Stray punctuation may have inflated the length; try dropping it.
        stripped = re.sub(r"[^A-Z0-9]", "", s)
        if 9 <= len(stripped) <= 11:
            s = stripped
        else:
            return result

    series_len = len(s) - 8                       # 1, 2 or 3 series letters
    layout = "LLDD" + "L" * series_len + "DDDD"
    result["layout"] = layout

    options = [_options_for(ch, slot) for ch, slot in zip(s, layout)]

    # Primary correction: best option at every position
    primary = [opts[0] for opts in options]
    changes = [
        (i, ch, primary[i], "letter" if layout[i] == "L" else "digit")
        for i, ch in enumerate(s) if primary[i] != ch
    ]

    # Alternatives: change ONE position at a time to its next-best look-alike
    variants = ["".join(primary)]
    for i, opts in enumerate(options):
        for alt in opts[1:]:
            v = primary.copy()
            v[i] = alt
            v = "".join(v)
            if v not in variants:
                variants.append(v)
            if len(variants) >= MAX_VARIANTS:
                break
        if len(variants) >= MAX_VARIANTS:
            break

    corrected = variants[0]
    result["corrected"] = corrected
    result["variants"] = variants
    result["changes"] = changes
    result["valid"] = corrected[:2] in STATE_CODES
    return result


if __name__ == "__main__":
    for sample in ["UP&8oBqSs44", "RJ@o%%ASDF", "up 80 bq 5544", "MH12AB1234"]:
        r = correct_plate(sample)
        print(f"{sample!r:>16} -> {r['corrected']}  valid={r['valid']}  "
              f"pattern_ok={r['pattern_ok']}")
        for c in r["changes"]:
            print("     ", c)
