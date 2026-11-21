"""
Phase 3 — check THIS laptop's source API end to end and save the responses as evidence.
Same script on every source laptop. Run while source_api.py is running.

    python3 phase3/check_source_api.py --plate UP09AI8815 --terms "who owns it" "ownership history"
    python3 phase3/check_source_api.py --seed-table owners --seed-column phone --value 9876543210

Calls /api/health, /api/schema, /api/context (from the seed) and /api/docsearch (with the
identifiers the context returned) and writes every JSON answer to phase3/evidence/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

HUB = {"vehicles": ("vehicles", "reg_plate"), "insurance": ("insurance_policies", "vehicle_number"),
       "rto": ("rto_records", "car_id"), "theft": ("theft_records", "plate_no")}
PORTS = {"vehicles": 5101, "insurance": 5102, "rto": 5103, "theft": 5104}


def call(base, path, token, payload=None):
    req = urllib.request.Request(
        base + path, method="POST" if payload is not None else "GET",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--source", default=os.getenv("SOURCE_NAME", "vehicles"))
    ap.add_argument("--base", default=None, help="default http://127.0.0.1:<source port>")
    ap.add_argument("--plate", help="seed: a plate stored in this source's hub table")
    ap.add_argument("--seed-table")
    ap.add_argument("--seed-column")
    ap.add_argument("--value")
    ap.add_argument("--match", default="exact", choices=["exact", "similar"])
    ap.add_argument("--terms", nargs="*", default=[])
    ap.add_argument("--depth", type=int, default=2)
    args = ap.parse_args()

    token = os.getenv(f"{args.source.upper()}_API_TOKEN") or os.getenv("SOURCE_API_TOKEN", "")
    base = args.base or f"http://127.0.0.1:{PORTS.get(args.source, 5101)}"
    out = Path(__file__).resolve().parent / "evidence"     # next to this script
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def save(name, data):
        path = out / f"{args.source}_{name}_{stamp}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    status, health = call(base, "/api/health", token)
    print(f"health  : HTTP {status} {health}")
    status, schema = call(base, "/api/schema", token)
    if status != 200:
        sys.exit(f"/api/schema failed: HTTP {status} {schema}")
    print(f"tables  : {list(schema['tables'])}")
    print(f"FKs     : {len(schema['fk_graph'])}")
    for fk in schema["fk_graph"]:
        print(f"          {fk['child']} -> {fk['parent']}")
    print(f"docs    : {schema['documents']}")
    print(f"saved   : {save('schema', schema)}")

    if args.plate:
        table, column = HUB[args.source]
        value = args.plate
    elif args.seed_table and args.seed_column and args.value:
        table, column, value = args.seed_table, args.seed_column, args.value
    else:
        print("\n(no seed given: use --plate or --seed-table/--seed-column/--value)")
        return
    request = {"seeds": [{"table": table, "column": column, "values": [value]}],
               "match": args.match, "query_terms": args.terms, "max_depth": args.depth}
    status, ctx = call(base, "/api/context", token, request)
    if status != 200:
        sys.exit(f"/api/context failed: HTTP {status} {ctx}")
    print(f"\ncontext : {ctx['stats']}  intents={ctx['intents']}")
    for node in ctx["nodes"][:15]:
        print(f"  hop {node['hop']} rel {node['relevance']:.2f} {node['id']:<28} "
              f"via {node['via'] or 'SEED'}")
    print(f"ids     : { {k: v for k, v in ctx['identifiers'].items() if k != 'dates'} }")
    print(f"saved   : {save('context', {'request': request, 'response': ctx})}")

    ids = {k: v for k, v in ctx["identifiers"].items() if k != "dates"}
    dates = sorted(d["value"] for d in ctx["identifiers"].get("dates", [])
                   if "birth" not in d["column"])           # events only, not birthdays
    doc_request = {"identifiers": ids, "keywords": args.terms,
                   "places": ids.get("cities", [])[:5], "k": 5}
    if dates:
        doc_request["date_window"] = [dates[0], dates[-1]]
    status, docs = call(base, "/api/docsearch", token, doc_request)
    if status != 200:
        print(f"\ndocsearch: HTTP {status} {docs.get('error')}")
        return
    print(f"\ndocs    : {docs['stats']}")
    for doc in docs["docs"]:
        print(f"  {doc['doc_id']:<24} {doc['score']:.3f}  {'; '.join(doc['matched_on'])[:90]}")
        print(f"      {doc['snippet'][:150]}")
    print(f"saved   : {save('docsearch', {'request': doc_request, 'response': docs})}")


if __name__ == "__main__":
    main()
