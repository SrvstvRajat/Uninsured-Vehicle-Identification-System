"""
Phase 3 — build THIS laptop's document index (used by source_api.py /api/docsearch).
Same script on every source laptop (M2–M5).

    python3 phase3/build_doc_index.py                     # unstructured/docs -> unstructured/index
    python3 phase3/build_doc_index.py --no-embeddings     # BM25 + identifiers only

Steps
  1. read every unstructured/docs/<doc_type>/<doc_id>.txt
  2. split into chunks of ~250 words (50-word overlap; short documents stay one chunk)
  3. tag each chunk: plates (also OCR-noisy ones like 'UP 09 AI 88I5'), phone numbers,
     FIR / policy / claim / challan / chassis / engine numbers, dates (normalised to
     YYYY-MM-DD from '01-06-2025', '1st June 2025', '01 Jun 2025' ...), cities
  4. embeddings with sentence-transformers all-MiniLM-L6-v2 (if installed; optional)
  5. write unstructured/index/chunks.jsonl, embeddings.npy, meta.json

source_api.py reloads the index automatically when chunks.jsonl changes.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

CHUNK_WORDS = 250
CHUNK_OVERLAP = 50
MODEL = "all-MiniLM-L6-v2"

# Plates as they appear in text: spaces / hyphens allowed, OCR letters in digit slots.
PLATE_TEXT_RE = re.compile(
    r"\b([A-Z]{2})[\s-]?([0-9OILSBZ]{1,2})[\s-]?([A-Z0-9]{1,3})[\s-]?([0-9OILSBZ]{3,4})\b",
    re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
ID_PATTERNS = {
    "fir_nos": re.compile(r"\bFIR/[A-Z0-9]+/\d{4}/\d+\b", re.I),
    "policy_nos": re.compile(r"\bPOL[-/]?[A-Z]*\d{3,}\b", re.I),     # POL-0000044, POL1001
    "claim_nos": re.compile(r"\bCLM\d{4,}\b", re.I),
    "challan_nos": re.compile(r"\bCH\d{5,}\b", re.I),
    "chassis": re.compile(r"\bCHS\d{6,}\b", re.I),
    "engines": re.compile(r"\bENG\d{6,}\b", re.I),
    "certificates": re.compile(r"\bSHR[-/]?\d{4,}\b", re.I),
}
CITIES = ["Delhi", "New Delhi", "Ghaziabad", "Noida", "Lucknow", "Meerut", "Gurugram",
          "Gurgaon", "Faridabad", "Mumbai", "Pune", "Bengaluru", "Bangalore", "Jaipur",
          "Chandigarh", "Ahmedabad", "Chennai", "Kolkata", "Bhopal", "Hyderabad"]
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda g: (int(g[0]), int(g[1]), int(g[2]))),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b"),
     lambda g: (int(g[2]), int(g[1]), int(g[0]))),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"),
     lambda g: (int(g[2]), MONTHS.get(g[1].lower()), int(g[0]))),
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"),
     lambda g: (int(g[2]), MONTHS.get(g[0].lower()), int(g[1]))),
]
STATE_CODES = set("AN AP AR AS BR CH CG DD DL DN GA GJ HR HP JK JH KA KL LA LD MH ML MN MP MZ NL "
                  "OD OR PB PY RJ SK TN TS TR UP UK WB".split())
OCR_TO_DIGIT = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def plate_tags(text: str) -> list[dict]:
    tags, seen = [], set()
    for m in PLATE_TEXT_RE.finditer(text):
        raw_state, _raw_district, raw_series, _raw_number = m.groups()
        # 'UP 09 AI 8815' / 'UP-09-AI-8815' must be in capitals (avoids 'on 09 Sep 2019');
        # only the compact form ('up09ai8815') may be lower case.
        spaced = bool(re.search(r"[\s-]", m.group(0)))
        capitals = raw_state.isupper() and raw_series.upper() == raw_series
        if spaced and not capitals and not (
                raw_state.upper() in STATE_CODES
                and raw_series.lower()[:3] not in MONTHS
                and not re.fullmatch(r"(19|20)\d\d", _raw_number)):
            continue
        state, district, series, number = (g.upper() for g in m.groups())
        if not state.isalpha():
            continue
        # keep the OCR letters (fuzzy matching handles them) but require a plate shape
        if sum(ch.isdigit() for ch in district.translate(OCR_TO_DIGIT) +
               number.translate(OCR_TO_DIGIT)) < 3:
            continue
        norm = state + district + series + number
        if norm not in seen:
            seen.add(norm)
            tags.append({"raw": m.group(0), "norm": norm})
    return tags


def date_tags(text: str) -> list[str]:
    found = set()
    for pattern, parts in DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                y, mo, d = parts(m.groups())
                if mo:
                    found.add(date(y, mo, d).isoformat())
            except (ValueError, TypeError):
                continue
    return sorted(found)


def tag_chunk(text: str) -> dict:
    return {
        "plates": plate_tags(text),
        "phones": sorted({m.group(1) for m in PHONE_RE.finditer(text)}),
        "ids": {k: sorted({m.group(0).upper() for m in rx.finditer(text)})
                for k, rx in ID_PATTERNS.items() if rx.search(text)},
        "dates": date_tags(text),
        "cities": sorted({c for c in CITIES if re.search(rf"\b{re.escape(c)}\b", text, re.I)}),
    }


def chunk_words(text: str) -> list[str]:
    words = text.split()
    if len(words) <= CHUNK_WORDS:
        return [text.strip()]
    step = CHUNK_WORDS - CHUNK_OVERLAP
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), step)
            if words[i:i + CHUNK_WORDS]]


def main():
    ap = argparse.ArgumentParser(description="Build this laptop's document index.")
    ap.add_argument("--docs", type=Path, default=Path("unstructured/docs"))
    ap.add_argument("--out", type=Path, default=Path("unstructured/index"))
    ap.add_argument("--no-embeddings", action="store_true")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    files = sorted(args.docs.rglob("*.txt"))
    if not files:
        raise SystemExit(f"No .txt documents under {args.docs}")
    chunks = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for no, part in enumerate(chunk_words(text)):
            chunks.append({"chunk_id": f"{path.stem}#{no}", "doc_id": path.stem,
                           "doc_type": path.parent.name, "chunk_no": no,
                           "file": str(path.relative_to(args.docs)), "text": part,
                           "tags": tag_chunk(part)})
    args.out.mkdir(parents=True, exist_ok=True)

    model_name = None
    if not args.no_embeddings:
        try:
            import numpy
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(args.model)
            vectors = model.encode([c["text"] for c in chunks], batch_size=64,
                                   normalize_embeddings=True, show_progress_bar=True)
            numpy.save(args.out / "embeddings.npy", numpy.asarray(vectors, dtype="float32"))
            model_name = args.model
        except Exception as exc:
            print(f"embeddings skipped ({exc!r}); /api/docsearch will use identifiers + BM25 "
                  "only. Install sentence-transformers to enable semantic search.")
    if model_name is None:
        stale = args.out / "embeddings.npy"
        if stale.exists():
            stale.unlink()

    with (args.out / "chunks.jsonl").open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    (args.out / "meta.json").write_text(json.dumps({
        "built_at": datetime.now().isoformat(timespec="seconds"), "documents": len(files),
        "chunks": len(chunks), "model": model_name}, indent=2))

    tagged = sum(bool(c["tags"]["plates"]) for c in chunks)
    by_type = {}
    for c in chunks:
        by_type[c["doc_type"]] = by_type.get(c["doc_type"], 0) + 1
    print(f"documents: {len(files)}  chunks: {len(chunks)}  with a plate tag: {tagged}")
    print(f"per type: {by_type}")
    print(f"semantic: {'on (' + model_name + ')' if model_name else 'off'}")
    print(f"index written to {args.out}/")


if __name__ == "__main__":
    main()
