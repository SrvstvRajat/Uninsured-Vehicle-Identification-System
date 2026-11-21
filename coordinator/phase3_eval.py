"""
Phase 3 — evaluation (run on M1, the coordinator, with the source laptops running).

    python3 phase3_eval.py --manifests phase3/eval/manifests --auto 20
    python3 phase3_eval.py --manifests phase3/eval/manifests --queries phase3/eval/queries.json
    python3 phase3_eval.py --manifests phase3/eval/manifests --auto-phone 25 \
            --registration-data phase3/eval/M2_registration

Ground truth: copy each laptop's unstructured/manifest.csv to
phase3/eval/manifests/<source>.csv (e.g. vehicles.csv). The manifests are used
ONLY here, never by the search.

--auto N builds N questions from the manifests (vehicles that have documents),
phrased for the document type, e.g. "Ownership history of UP09AI8815".
--queries reads [{"id": "Q1", "query": "...", "plate": "optional chosen plate"}].
--auto-phone N asks about an owner by PHONE only ("What vehicles does the person with
phone 98... own?"). The question shares no identifier with most documents, so only
context discovery (phone -> owner -> vehicles -> plates) can find them. Ground truth:
M2's generated owners.csv + vehicles.csv (copy phase3/data/M2_registration from M2).

For every question it runs the full pipeline (context discovery rounds 1 + 2,
then document search) and reports:
  context      rows per source, rounds, cross-database links, intents covered
  recall@k     expected documents (about this vehicle) that were returned
  precision@k  returned documents that belong to the context (this vehicle or a
               vehicle of the same owner)
  distractors  documents about vehicles in no database that were returned
  baseline     the same search with the query words only (no context)
Writes phase3/evidence/eval_<time>.csv and .md (a table for the report).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from context_engine import discover
from mediator import normalize_plate
from unstructured import search_documents

PHRASES = {
    "sale_deed": "Ownership history of {plate}",
    "transfer_letter": "Who owned {plate} before and when was it sold?",
    "claim_report": "Is {plate} insured and has any claim been made?",
    "surveyor_note": "Insurance claim and damage assessment for {plate}",
    "inspection_report": "Show fitness and inspection status of {plate}",
    "challan_notice": "Show challans and fines of {plate}",
    "fir_narrative": "Was {plate} ever stolen? Show the FIR",
    "recovery_report": "Was the stolen vehicle {plate} recovered?",
    "news_article": "Any news about the theft of {plate}?",
}


def load_manifests(folder: Path):
    docs = {}
    for path in sorted(folder.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                row["source_file"] = path.stem
                docs[row["doc_id"]] = row
    return docs


def auto_queries(manifest: dict, n: int, seed: int):
    by_plate = defaultdict(set)
    for doc in manifest.values():
        if doc.get("is_distractor") == "0" and doc.get("linked_plate"):
            by_plate[doc["linked_plate"]].add(doc["doc_type"])
    plates = sorted(by_plate)
    random.Random(seed).shuffle(plates)
    out = []
    for i, plate in enumerate(plates[:n], 1):
        doc_type = sorted(by_plate[plate])[0]
        out.append({"id": f"A{i:02d}", "query": PHRASES.get(doc_type, "Tell me about {plate}")
                    .format(plate=plate), "plate": plate})
    return out


def auto_phone_queries(manifest: dict, folder: Path, n: int, seed: int):
    """Phone-only questions; expected = documents about every vehicle of that owner."""
    with (folder / "owners.csv").open(newline="", encoding="utf-8") as handle:
        phone = {r["owner_id"]: r["phone"] for r in csv.DictReader(handle)}
    plates_of = defaultdict(set)
    with (folder / "vehicles.csv").open(newline="", encoding="utf-8") as handle:
        for r in csv.DictReader(handle):
            plates_of[r["owner_id"]].add(normalize_plate(r["reg_plate"]))
    documented = {d["linked_plate"] for d in manifest.values() if d.get("is_distractor") == "0"}
    owners = sorted(o for o, plates in plates_of.items() if plates & documented)
    random.Random(seed).shuffle(owners)
    return [{"id": f"P{i:02d}", "plates": sorted(plates_of[o]),
             "query": f"What vehicles does the person with phone {phone[o]} own, "
                      "and what is their ownership history?"}
            for i, o in enumerate(owners[:n], 1)]


def score(returned: list[str], manifest: dict, entity_plates: set, context_plates: set):
    expected = {d for d, row in manifest.items() if row.get("is_distractor") == "0"
                and row.get("linked_plate") in entity_plates}
    relevant = {d for d, row in manifest.items() if row.get("is_distractor") == "0"
                and row.get("linked_plate") in context_plates}
    distractors = [d for d in returned if manifest.get(d, {}).get("is_distractor") == "1"]
    hits = [d for d in returned if d in relevant]
    return {
        "expected": len(expected),
        "recall": (len(expected & set(returned)) / len(expected)) if expected else None,
        "precision": (len(hits) / len(returned)) if returned else None,
        "returned": len(returned), "distractors": len(distractors),
    }


def fmt(value):
    return "—" if value is None else f"{value:.2f}"


def main():
    ap = argparse.ArgumentParser(description="Phase 3 evaluation.")
    ap.add_argument("--manifests", type=Path, default=Path("phase3/eval/manifests"))
    ap.add_argument("--queries", type=Path)
    ap.add_argument("--auto", type=int, default=0)
    ap.add_argument("--auto-phone", type=int, default=0)
    ap.add_argument("--registration-data", type=Path, default=Path("phase3/eval/M2_registration"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    manifest = load_manifests(args.manifests) if args.manifests.is_dir() else {}
    if not manifest:
        print(f"(no manifests in {args.manifests}: document metrics will be empty)")
    queries = json.loads(args.queries.read_text()) if args.queries else []
    if args.auto:
        queries += auto_queries(manifest, args.auto, args.seed)
    if args.auto_phone:
        queries += auto_phone_queries(manifest, args.registration_data, args.auto_phone, args.seed)
    if not queries:
        raise SystemExit("No queries: use --auto N (with manifests) or --queries file.json")

    rows = []
    for q in queries:
        ctx = discover(q["query"], plate=q.get("plate"))
        if ctx["status"] != "ok":
            rows.append({"id": q["id"], "query": q["query"], "status": ctx["status"]})
            print(f"{q['id']}  {ctx['status']:9s} {q['query']}")
            continue
        entity_plates = {normalize_plate(l["stored_plate"]) for l in ctx["entity_links"]}
        if ctx.get("vehicle"):
            entity_plates.add(ctx["vehicle"]["vehicle_key"])
        if q.get("plates"):                     # ground truth given with the question
            entity_plates = set(q["plates"])
        context_plates = {normalize_plate(p) for p in ctx["identifiers"].get("plates", [])}
        k = max(args.k, 2 * len(q.get("plates", [])))      # an owner may have several cars
        with_ctx = search_documents(ctx, k=k)
        baseline = search_documents(ctx, k=k, use_context=False)
        s_ctx = score([d["doc_id"] for d in with_ctx["docs"]], manifest, entity_plates,
                      context_plates)
        s_base = score([d["doc_id"] for d in baseline["docs"]], manifest, entity_plates,
                       context_plates)
        per_source = defaultdict(int)
        for node in ctx["nodes"]:
            per_source[node["source"]] += 1
        row = {
            "id": q["id"], "query": q["query"], "status": "ok",
            "vehicle": ctx["vehicle"]["vehicle_key"] if ctx.get("vehicle") else "",
            "context_rows": len(ctx["nodes"]), "pruned": ctx.get("pruned_nodes", 0),
            "per_source": dict(per_source),
            "round2_rows": sum(1 for n in ctx["nodes"] if n["round"] == 2),
            "cross_links": len(ctx["cross_links"]),
            "intents": ",".join(ctx["intents"]),
            "intents_covered": sum(ctx["coverage"].values()),
            "expected_docs": s_ctx["expected"],
            "recall": s_ctx["recall"], "precision": s_ctx["precision"],
            "distractors": s_ctx["distractors"],
            "base_recall": s_base["recall"], "base_precision": s_base["precision"],
            "base_distractors": s_base["distractors"],
            "ms": ctx["elapsed_ms"] + with_ctx["elapsed_ms"],
        }
        rows.append(row)
        print(f"{q['id']}  rows {row['context_rows']:>3} (r2 {row['round2_rows']:>2})  "
              f"recall {fmt(row['recall'])}  precision {fmt(row['precision'])}  "
              f"| baseline {fmt(row['base_recall'])} / {fmt(row['base_precision'])}  "
              f"{row['ms']:.0f} ms  {q['query']}")

    ok = [r for r in rows if r["status"] == "ok"]

    def mean(key):
        vals = [r[key] for r in ok if r.get(key) is not None]
        return statistics.mean(vals) if vals else None

    summary = {k: mean(k) for k in ("recall", "precision", "base_recall", "base_precision",
                                    "context_rows", "round2_rows", "ms")}
    summary["distractors"] = sum(r["distractors"] for r in ok)
    summary["base_distractors"] = sum(r["base_distractors"] for r in ok)

    out = Path("phase3/evidence")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fields = ["id", "query", "status", "vehicle", "context_rows", "pruned", "round2_rows",
              "cross_links", "intents", "intents_covered", "expected_docs", "recall",
              "precision", "distractors", "base_recall", "base_precision",
              "base_distractors", "ms", "per_source"]
    with (out / f"eval_{stamp}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    md = ["| Query | Context rows (round 2) | Recall@%d | Precision@%d | Baseline R / P |"
          % (args.k, args.k), "|---|---|---|---|---|"]
    for r in ok:
        md.append(f"| {r['query']} | {r['context_rows']} ({r['round2_rows']}) | "
                  f"{fmt(r['recall'])} | {fmt(r['precision'])} | "
                  f"{fmt(r['base_recall'])} / {fmt(r['base_precision'])} |")
    md.append(f"| **Mean** | {fmt(summary['context_rows'])} ({fmt(summary['round2_rows'])}) | "
              f"**{fmt(summary['recall'])}** | **{fmt(summary['precision'])}** | "
              f"{fmt(summary['base_recall'])} / {fmt(summary['base_precision'])} |")
    md.append(f"\nDistractor documents returned: with context {summary['distractors']}, "
              f"baseline {summary['base_distractors']}. Mean time {fmt(summary['ms'])} ms.")
    (out / f"eval_{stamp}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n" + "\n".join(md))
    print(f"\nsaved: {out}/eval_{stamp}.csv and .md")


if __name__ == "__main__":
    main()
