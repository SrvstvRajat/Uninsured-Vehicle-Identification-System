# """
# Phase 3 — Context engine (Coordinator, M1).

# Turns a user query into a QUERY CONTEXT accumulated from all source databases:

#   A. understand   plates (with OCR-aware corrections), phones, FIR / policy / chassis /
#                   engine numbers, person names, intents (insurance, theft, ownership ...)
#   B. resolve      Phase 2: similarity on the sources + entity matching here -> the vehicle,
#                   and how EACH source stores its plate (e.g. insurance: 'UP09AI88L5')
#   C. round 1      federate a sub-query to every source: POST /api/context with that
#                   source's own seed. Each database walks ITS OWN FK -> PK graph and
#                   returns only rows relevant to the query (it discovers its own context).
#   D. round 2      identifiers discovered in round 1 (owner phone, owner name, other
#                   vehicles of the owner ...) are sent to the OTHER databases, which
#                   reach context the plate alone cannot (beyond the query result).
#   E. accumulate   merge everything, keep the most relevant rows (and the best row of
#                   every requested intent), build identifiers / places / date window.

# The coordinator never opens MySQL to a source laptop: every call is REST
# (source_client.py). Sources that still run the Phase 2 source_api.py, or that
# have not created their Phase 3 tables yet, degrade gracefully: their Phase 2
# record (from entity matching) is used as their context.
# """

# from __future__ import annotations

# import re
# import time
# from concurrent.futures import ThreadPoolExecutor
# from datetime import date, timedelta
# from typing import Optional

# from config import SOURCE_NAMES
# from mediator import build_result, identify, normalize_plate
# from plate_correct import correct_plate
# from source_client import SOURCE_TABLES, SourceError, context as source_context

# SOURCES = ("vehicles", "insurance", "rto", "theft")
# DEFAULT_DEPTH = 2
# MAX_CONTEXT_NODES = 40
# ROUND2_PENALTY = 0.80          # one extra cross-database hop
# NAME_LINK_PENALTY = 0.85       # names repeat (many "Amit Agarwal"s): weaker than a phone
# MAX_SEED_VALUES = 10
# CHOOSE_MIN_SCORE = 0.60
# MAX_OTHER_VEHICLES = 5         # other vehicles of the owner followed into other databases        # look-alikes below this are not offered (Phase 2 review score)

# # Same intent vocabulary as source_api.py (sources boost their intent tables).
# INTENT_LEXICON = {
#     "insurance": ["insured", "insurance", "policy", "cover", "expired", "premium", "uninsured"],
#     "claim": ["claim", "claims", "damage", "accident", "settled", "surveyor"],
#     "theft": ["stolen", "theft", "fir", "police", "missing", "recovered", "found", "station"],
#     "scrap": ["scrapped", "shredded", "scrap", "yard"],
#     "ownership": ["owner", "owned", "owns", "sold", "transfer", "bought", "history", "seller",
#                   "buyer"],
#     "dealer": ["dealer", "purchase", "showroom"],
#     "vehicle": ["model", "make", "fuel", "body", "seating", "spec"],
#     "compliance": ["challan", "fine", "offence", "fitness", "puc", "pollution", "traffic"],
#     "registration": ["registration", "renewal", "rto", "office", "registered"],
#     "agent": ["agent", "branch"],
# }
# # Which (source, table) rows answer which intent — used to keep the best row per intent.
# INTENT_TABLES = {
#     "insurance": {("insurance", "insurance_policies"), ("insurance", "customers")},
#     "claim": {("insurance", "claims")},
#     "agent": {("insurance", "agents"), ("insurance", "branches")},
#     "theft": {("theft", "theft_records"), ("theft", "firs"), ("theft", "recoveries"),
#               ("theft", "police_stations")},
#     "scrap": {("theft", "shredding_certificates")},
#     "ownership": {("vehicles", "owners"), ("vehicles", "ownership_transfers")},
#     "dealer": {("vehicles", "dealers")},
#     "vehicle": {("vehicles", "vehicle_models"), ("vehicles", "vehicles")},
#     "compliance": {("rto", "challans"), ("rto", "fitness_certificates"),
#                    ("rto", "puc_certificates")},
#     "registration": {("rto", "rto_records"), ("rto", "rto_offices")},
# }
# # Round 2: identifier discovered somewhere -> where else it can be looked up.
# #   (identifier, target source, table, column, match)
# CROSS_LINKS = (
#     ("phones", "vehicles", "owners", "phone", "exact"),
#     ("phones", "insurance", "customers", "phone", "exact"),
#     ("phones", "theft", "firs", "complainant_phone", "exact"),
#     ("fir_nos", "theft", "firs", "fir_no", "exact"),
#     ("policy_nos", "insurance", "insurance_policies", "policy_no", "exact"),
#     ("names", "vehicles", "owners", "full_name", "similar"),
#     ("names", "insurance", "customers", "customer_name", "similar"),
#     ("names", "theft", "firs", "complainant_name", "similar"),
# )
# STOPWORDS = set("""a an the is was were are be been of for to in on at by with and or not it its
# this that these those what which who whom whose when where how why does do did has have had
# any all show me tell give find list there their his her him he she they them my our your
# about from into than then also if ever still yet please can could would should get got""".split())

# STATE_CODES = set("AN AP AR AS BR CH CG DD DL DN GA GJ HR HP JK JH KA KL LA LD MH ML MN MP MZ "
#                   "NL OD OR PB PY RJ SK TN TS TR UP UK WB".split())
# PLATE_QUERY_RE = re.compile(
#     r"\b([A-Za-z]{2})[\s-]?([0-9OoIl]{1,2})[\s-]?([A-Za-z0-9]{1,3})[\s-]?([0-9OoIlSsBb@#*?]{3,4})\b")
# PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
# ID_RES = {
#     "fir_nos": re.compile(r"\bFIR/[A-Z0-9]+/\d{4}/\d+\b", re.I),
#     "policy_nos": re.compile(r"\bPOL[-/]?[A-Z]*\d{3,}\b", re.I),     # POL-0000044, POL1001
#     "chassis": re.compile(r"\bCHS\d{6,}\b", re.I),
#     "engines": re.compile(r"\bENG\d{6,}\b", re.I),
#     "claim_nos": re.compile(r"\bCLM\d{4,}\b", re.I),
# }
# NAME_RE = re.compile(r"\b(?:owned by|owner|customer|complainant|named|by|of)\s+"
#                      r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})")


# # ---------------------------------------------------------------------------
# # A. understand the query
# # ---------------------------------------------------------------------------
# def parse_query(text: str) -> dict:
#     text = text or ""
#     found = {"plates": [], "plate_variants": [], "phones": [], "names": [],
#              "fir_nos": [], "policy_nos": [], "chassis": [], "engines": [], "claim_nos": []}
#     consumed = []
#     for key, rx in ID_RES.items():
#         for m in rx.finditer(text):
#             value = m.group(0).upper()
#             if value not in found[key]:
#                 found[key].append(value)
#             consumed.append(m.group(0))
#     for m in PHONE_RE.finditer(text):
#         if m.group(1) not in found["phones"]:
#             found["phones"].append(m.group(1))
#         consumed.append(m.group(0))
#     for m in PLATE_QUERY_RE.finditer(text):
#         raw = m.group(0)
#         if m.group(1).upper() not in STATE_CODES or any(raw in c for c in consumed):
#             continue
#         correction = correct_plate(raw)
#         if not (correction.get("pattern_ok") or correction.get("corrected")):
#             continue
#         key = normalize_plate(correction.get("cleaned") or raw)
#         if key and key not in found["plates"]:
#             found["plates"].append(key)
#             for variant in [key] + list(correction.get("variants") or []):
#                 variant = normalize_plate(variant)
#                 if variant and variant not in found["plate_variants"]:
#                     found["plate_variants"].append(variant)
#         consumed.append(raw)
#     for m in NAME_RE.finditer(text):
#         name = m.group(1).strip()
#         if name not in found["names"]:
#             found["names"].append(name)

#     rest = text
#     for piece in consumed:
#         rest = rest.replace(piece, " ")
#     words = [w for w in re.findall(r"[a-z]+", rest.lower()) if len(w) >= 3]
#     terms = [w for w in dict.fromkeys(words) if w not in STOPWORDS]
#     intents = [i for i, lex in INTENT_LEXICON.items() if set(terms) & set(lex)]
#     found.update(terms=terms, intents=intents, text=text)
#     return found


# # ---------------------------------------------------------------------------
# # helpers
# # ---------------------------------------------------------------------------
# def _call(source: str, payload: dict) -> dict:
#     """POST /api/context on one source; never raises (status in the result)."""
#     t0 = time.perf_counter()
#     try:
#         data = source_context(source, payload)
#         return {"ok": True, "data": data, "status": "ok",
#                 "ms": round((time.perf_counter() - t0) * 1000, 1)}
#     except SourceError as exc:
#         status = ("phase2_api" if exc.status == 404 else
#                   "not_served" if exc.status == 400 else "unreachable")
#         return {"ok": False, "data": None, "status": status, "error": str(exc),
#                 "ms": round((time.perf_counter() - t0) * 1000, 1)}
#     except Exception as exc:
#         return {"ok": False, "data": None, "status": "error", "error": str(exc),
#                 "ms": round((time.perf_counter() - t0) * 1000, 1)}


# def _payload(seeds, match, parsed, depth):
#     return {"seeds": seeds, "match": match, "query_terms": parsed["terms"],
#             "intents": parsed["intents"], "max_depth": depth}


# def _run_calls(jobs: list[dict]) -> list[dict]:
#     """jobs: [{"source", "payload", ...}] -> same dicts with "result" filled, in parallel."""
#     if not jobs:
#         return jobs
#     with ThreadPoolExecutor(max_workers=min(len(jobs), 12)) as pool:
#         for job, result in zip(jobs, pool.map(lambda j: _call(j["source"], j["payload"]), jobs)):
#             job["result"] = result
#     return jobs


# def _phase2_nodes(source: str, entity: dict) -> list[dict]:
#     """Context for a source that cannot run /api/context: its Phase 2 record."""
#     row = (entity or {}).get("records", {}).get(source)
#     if not row:
#         return []
#     table = SOURCE_TABLES[source][0]
#     return [{"id": f"{table}:{row.get('id')}", "table": table, "hop": 0, "relevance": 1.0,
#              "via": "Phase 2 record (entity matching)", "row": row, "why": {}}]


# # ---------------------------------------------------------------------------
# # main entry point
# # ---------------------------------------------------------------------------
# def discover(query: str, plate: Optional[str] = None, details: Optional[dict] = None,
#              depth: int = DEFAULT_DEPTH, round2: bool = True) -> dict:
#     """Build the query context. `plate` = a plate the operator picked from candidates."""
#     t_start = time.perf_counter()
#     parsed = parse_query(query)
#     if plate:
#         key = normalize_plate(plate)
#         parsed["plates"] = [key] + [p for p in parsed["plates"] if p != key]
#         parsed["plate_variants"] = [key]
#     out = {"query": query, "parsed": parsed, "intents": parsed["intents"],
#            "status": "ok", "message": None, "candidates": [], "vehicle": None,
#            "entity_links": [], "calls": [], "nodes": [], "edges": [], "cross_links": [],
#            "identifiers": {}, "places": [], "date_window": None, "description": ""}

#     # ---------------- B. resolve the vehicle (Phase 2 entity matching)
#     entity = None
#     if parsed["plate_variants"]:
#         outcome = identify(parsed["plate_variants"], details or {})
#         candidates = [c for c in outcome["candidates"] if c["score"] >= CHOOSE_MIN_SCORE]
#         out["candidates"] = [{"plate": c["plate"], "score": round(c["score"], 3),
#                               "sources": c["sources"]} for c in candidates]
#         chosen = None
#         if plate:
#             chosen = next((c for c in candidates if c["plate"] == normalize_plate(plate)), None)
#         elif outcome["auto"] or (candidates and candidates[0]["plate_score"] >= 0.999
#                                  and candidates[0]["plate"] in parsed["plate_variants"]):
#             chosen = candidates[0]
#         if chosen is None and candidates and not (parsed["phones"] or parsed["fir_nos"]
#                                                   or parsed["policy_nos"]):
#             out.update(status="choose",
#                        message="Several registered vehicles look like this plate and none "
#                                "is clearly the best. Pick the right one.")
#             out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
#             return out
#         if chosen is not None:
#             entity = chosen["entity"]
#             out["vehicle"] = build_result(chosen["plate"], entity, outcome["source_status"])
#             out["entity_links"] = out["vehicle"].get("entity_links", [])
#         elif not candidates and not any(parsed[k] for k in
#                                         ("phones", "fir_nos", "policy_nos", "names")):
#             down = [SOURCE_NAMES.get(src, src) for src, st in outcome["source_status"].items()
#                     if not st["available"]]
#             if len(down) == len(outcome["source_status"]):
#                 out.update(status="unavailable",
#                            message="No source database could be reached: "
#                                    + ", ".join(down) + ". Is source_api.py running there?")
#             else:
#                 out.update(status="not_found",
#                            message="No vehicle with a similar plate in any source database"
#                                    + (f" (unreachable: {', '.join(down)})." if down else "."))
#             out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
#             return out

#     # ---------------- C. round 1: every source discovers its own context
#     jobs, used_seeds = [], set()
#     for source in SOURCES:
#         seeds = []
#         link = (entity or {}).get("links", {}).get(source)
#         if link and link.get("value"):
#             table, _db, column = SOURCE_TABLES[source]
#             seeds.append({"table": table, "column": column, "values": [link["value"]]})
#             used_seeds.add((source, table, column, normalize_plate(link["value"])))
#         for key, tgt_source, table, column, match in CROSS_LINKS:  # identifiers typed by user
#             if tgt_source != source or match != "exact" or not parsed.get(key):
#                 continue
#             seeds.append({"table": table, "column": column,
#                           "values": parsed[key][:MAX_SEED_VALUES]})
#             used_seeds.update((source, table, column, str(v)) for v in parsed[key])
#         if seeds:
#             jobs.append({"round": 1, "source": source, "seeds": seeds,
#                          "payload": _payload(seeds, "exact", parsed, depth)})
#         if parsed["names"] and not entity:
#             for key, tgt_source, table, column, match in CROSS_LINKS:
#                 if key == "names" and tgt_source == source:
#                     s = [{"table": table, "column": column, "values": parsed["names"]}]
#                     jobs.append({"round": 1, "source": source, "seeds": s,
#                                  "payload": _payload(s, "similar", parsed, depth)})
#     _run_calls(jobs)

#     nodes: dict[str, dict] = {}
#     edges: list[dict] = []

#     def absorb(job, factor=1.0, link=None):
#         result = job["result"]
#         data = result.get("data") or {}
#         job_nodes = data.get("nodes") or []
#         if not result["ok"] and job["round"] == 1 and result["status"] in (
#                 "phase2_api", "not_served"):
#             job_nodes = _phase2_nodes(job["source"], entity)      # degrade gracefully
#             result["fallback"] = bool(job_nodes)
#         for node in job_nodes:
#             key = f"{job['source']}:{node['id']}"
#             relevance = round(node["relevance"] * factor, 4)
#             if key in nodes and nodes[key]["relevance"] >= relevance:
#                 continue
#             nodes[key] = dict(node, key=key, source=job["source"], round=job["round"],
#                               relevance=relevance, link=link)
#         for edge in data.get("edges") or []:
#             edges.append(dict(edge, source=job["source"]))
#         out["calls"].append({
#             "round": job["round"], "source": job["source"],
#             "machine": SOURCE_NAMES.get(job["source"], job["source"]),
#             "seeds": job["seeds"], "match": job["payload"]["match"],
#             "status": result["status"] + (" (Phase 2 record used)" if result.get("fallback")
#                                           else ""),
#             "error": result.get("error"), "ms": result["ms"],
#             "rows": len(job_nodes), "stats": data.get("stats"),
#             "fk_graph": data.get("fk_graph"), "link": link})
#         return data.get("identifiers") or {}

#     origin_ids: dict[str, dict] = {}       # identifier value -> sources it came from
#     for job in jobs:
#         ids = absorb(job)
#         for key, values in ids.items():
#             if key == "dates":
#                 continue
#             for value in values:
#                 origin_ids.setdefault(key, {}).setdefault(value, set()).add(job["source"])
#     # sources with an entity record but no seed call at all (should not happen) / unreachable
#     for source in SOURCES:
#         if not any(j["source"] == source for j in jobs) and (entity or {}).get(
#                 "records", {}).get(source):
#             for node in _phase2_nodes(source, entity):
#                 key = f"{source}:{node['id']}"
#                 nodes[key] = dict(node, key=key, source=source, round=1, link=None)

#     # ---------------- D. round 2: discovered identifiers -> the OTHER databases
#     if round2:
#         jobs2 = []
#         have_phone = bool(origin_ids.get("phones"))
#         for key, tgt_source, table, column, match in CROSS_LINKS:
#             if key == "names" and have_phone:
#                 continue                      # a phone identifies a person; a name does not
#             values = []
#             for value, origins in origin_ids.get(key, {}).items():
#                 if tgt_source in origins:
#                     continue                  # that source already walked from it
#                 if (tgt_source, table, column, str(value)) in used_seeds:
#                     continue
#                 values.append(value)
#             if not values:
#                 continue
#             seeds = [{"table": table, "column": column, "values": values[:MAX_SEED_VALUES]}]
#             for value in values:
#                 used_seeds.add((tgt_source, table, column, str(value)))
#             jobs2.append({"round": 2, "source": tgt_source, "seeds": seeds,
#                           "link": {"identifier": key, "values": values[:MAX_SEED_VALUES],
#                                    "from": sorted({o for v in values
#                                                    for o in origin_ids[key][v]}),
#                                    "match": match},
#                           "payload": _payload(seeds, match, parsed, max(1, depth - 1))})
#         # other vehicles of the owner -> their records elsewhere (ownership questions only).
#         # Each is resolved with Phase 2 entity matching, so a database that stores that
#         # car under a noisy plate (e.g. 'DL16KF68O2') is still reached, and a neighbouring
#         # plate (one digit different) is never mistaken for it.
#         if "ownership" in parsed["intents"]:
#             main = {normalize_plate(l.get("value")) for l in
#                     (entity or {}).get("links", {}).values()}
#             others = [p for p, o in origin_ids.get("plates", {}).items()
#                       if "vehicles" in o and p not in main][:MAX_OTHER_VEHICLES]
#             stored = {source: [] for source in ("insurance", "rto", "theft")}
#             for other in others:
#                 try:
#                     resolved = identify([other])
#                 except Exception:
#                     continue
#                 match = next((c for c in resolved["candidates"] if c["plate"] == other), None)
#                 for source, link in ((match or {}).get("entity", {}).get("links") or {}).items():
#                     if source in stored and link.get("value"):
#                         stored[source].append(link["value"])
#             for source, values in stored.items():
#                 if not values:
#                     continue
#                 table, _db, column = SOURCE_TABLES[source]
#                 seeds = [{"table": table, "column": column, "values": values[:MAX_SEED_VALUES]}]
#                 jobs2.append({"round": 2, "source": source, "seeds": seeds,
#                               "link": {"identifier": "plates (other vehicles of the owner)",
#                                        "values": values[:MAX_SEED_VALUES], "from": ["vehicles"],
#                                        "match": "entity matching"},
#                               "payload": _payload(seeds, "exact", parsed, 1)})
#         _run_calls(jobs2)
#         for job in jobs2:
#             factor = ROUND2_PENALTY * (NAME_LINK_PENALTY if job["link"]["identifier"] == "names"
#                                        else 1.0)
#             absorb(job, factor=factor, link=job["link"])
#             found = (job["result"].get("data") or {}).get("stats", {}).get("rows_returned", 0)
#             out["cross_links"].append(dict(job["link"], target=job["source"],
#                                            target_table=job["seeds"][0]["table"],
#                                            target_column=job["seeds"][0]["column"],
#                                            status=job["result"]["status"], rows=found))

#     # ---------------- E. accumulate + prune
#     ranked = sorted(nodes.values(), key=lambda n: (-n["relevance"], n["round"], n["hop"]))
#     keep = ranked[:MAX_CONTEXT_NODES]
#     kept_keys = {n["key"] for n in keep}
#     for intent in parsed["intents"]:              # never lose the best row of an intent
#         wanted = INTENT_TABLES.get(intent, set())
#         best = next((n for n in ranked if (n["source"], n["table"]) in wanted), None)
#         if best and best["key"] not in kept_keys:
#             keep.append(best)
#             kept_keys.add(best["key"])
#     out["nodes"] = keep
#     out["pruned_nodes"] = len(nodes) - len(keep)
#     kept_ids = {(n["source"], n["id"]) for n in keep}
#     out["edges"] = [e for e in edges if (e["source"], e["from"]) in kept_ids
#                     and (e["source"], e["to"]) in kept_ids]
#     out["coverage"] = {i: any((n["source"], n["table"]) in INTENT_TABLES.get(i, set())
#                               for n in keep) for i in parsed["intents"]}
#     _summarise(out, keep, parsed, entity)
#     out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
#     return out


# # ---------------------------------------------------------------------------
# # context summary used by the document search
# # ---------------------------------------------------------------------------
# PLATE_COLUMNS = {"reg_plate", "vehicle_number", "car_id", "plate_no", "vehicle_plate"}
# PERSON_COLUMNS = {"full_name", "customer_name", "complainant_name", "owner_name"}
# PERSON_TABLES = {"owners", "customers", "firs", "vehicles"}   # not agents, dealers, stations
# ID_COLUMNS = {"fir_no": "fir_nos", "policy_no": "policy_nos", "chassis_no": "chassis",
#               "engine_no": "engines", "certificate_no": "certificates",
#               "claim_no": "claim_nos"}


# def _summarise(out: dict, nodes: list[dict], parsed: dict, entity: Optional[dict]):
#     ids = {k: [] for k in ("plates", "phones", "names", "fir_nos", "policy_nos", "chassis",
#                            "engines", "certificates", "claim_nos")}

#     def add(key, value):
#         value = str(value or "").strip()
#         if value and value not in ids[key]:
#             ids[key].append(value)

#     for key in ids:                                   # typed by the user
#         for value in parsed.get(key, []):
#             add(key, value)
#     for link in (entity or {}).get("links", {}).values():
#         add("plates", normalize_plate(link.get("value")))   # every stored spelling
#     places, event_dates = [], []
#     for node in nodes:
#         for column, value in node["row"].items():
#             if value in (None, ""):
#                 continue
#             if column in PLATE_COLUMNS:
#                 add("plates", normalize_plate(value))
#             elif "phone" in column:
#                 if node["table"] in PERSON_TABLES:
#                     add("phones", re.sub(r"\D", "", str(value))[-10:])
#             elif column in PERSON_COLUMNS:
#                 if node["table"] in PERSON_TABLES:
#                     add("names", value)
#             elif column in ID_COLUMNS:
#                 add(ID_COLUMNS[column], value)
#             elif column in ("city", "location", "rto_office") and value not in places:
#                 places.append(str(value))
#             elif re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(value)) and "birth" not in column \
#                     and node["table"] != "vehicle_models":
#                 event_dates.append(str(value)[:10])
#     out["identifiers"] = {k: v for k, v in ids.items() if v}
#     out["places"] = places[:10]
#     if event_dates:
#         lo = date.fromisoformat(min(event_dates)) - timedelta(days=30)
#         hi = date.fromisoformat(max(event_dates)) + timedelta(days=90)
#         out["date_window"] = [lo.isoformat(), hi.isoformat()]
#     vehicle = out.get("vehicle") or {}
#     desc = " ".join(str(vehicle.get(k) or "") for k in ("color", "make", "model")).strip()
#     out["description"] = " ".join(x for x in [desc] + parsed["intents"] + parsed["terms"][:8] if x)



"""
Phase 3 — Context engine (Coordinator, M1).

Turns a user query into a QUERY CONTEXT accumulated from all source databases:

  A. understand   plates (with OCR-aware corrections), phones, FIR / policy / chassis /
                  engine numbers, person names, intents (insurance, theft, ownership ...)
  B. resolve      Phase 2: similarity on the sources + entity matching here -> the vehicle,
                  and how EACH source stores its plate (e.g. insurance: 'UP09AI88L5')
  C. round 1      federate a sub-query to every source: POST /api/context with that
                  source's own seed. Each database walks ITS OWN FK -> PK graph and
                  returns only rows relevant to the query (it discovers its own context).
  D. round 2      identifiers discovered in round 1 (owner phone, owner name, other
                  vehicles of the owner ...) are sent to the OTHER databases, which
                  reach context the plate alone cannot (beyond the query result).
  E. accumulate   merge everything, keep the most relevant rows (and the best row of
                  every requested intent), build identifiers / places / date window.

The coordinator never opens MySQL to a source laptop: every call is REST
(source_client.py). Sources that still run the Phase 2 source_api.py, or that
have not created their Phase 3 tables yet, degrade gracefully: their Phase 2
record (from entity matching) is used as their context.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Optional

from config import SOURCE_NAMES
from mediator import build_result, identify, normalize_plate
from plate_correct import correct_plate
from source_client import SOURCE_TABLES, SourceError, context as source_context

SOURCES = ("vehicles", "insurance", "rto", "theft")
DEFAULT_DEPTH = 2
MAX_CONTEXT_NODES = 40
ROUND2_PENALTY = 0.80          # one extra cross-database hop
NAME_LINK_PENALTY = 0.85       # names repeat (many "Amit Agarwal"s): weaker than a phone
MAX_SEED_VALUES = 10
CHOOSE_MIN_SCORE = 0.60
MAX_OTHER_VEHICLES = 5         # other vehicles of the owner followed into other databases        # look-alikes below this are not offered (Phase 2 review score)

# Same intent vocabulary as source_api.py (sources boost their intent tables).
INTENT_LEXICON = {
    "insurance": ["insured", "insurance", "policy", "cover", "expired", "premium", "uninsured"],
    "claim": ["claim", "claims", "damage", "accident", "settled", "surveyor"],
    "theft": ["stolen", "theft", "fir", "police", "missing", "recovered", "found", "station"],
    "scrap": ["scrapped", "shredded", "scrap", "yard"],
    "ownership": ["owner", "owned", "owns", "sold", "transfer", "bought", "history", "seller",
                  "buyer"],
    "dealer": ["dealer", "purchase", "showroom"],
    "vehicle": ["model", "make", "fuel", "body", "seating", "spec"],
    "compliance": ["challan", "fine", "offence", "fitness", "puc", "pollution", "traffic"],
    "registration": ["registration", "renewal", "rto", "office", "registered"],
    "agent": ["agent", "branch"],
}
# Which (source, table) rows answer which intent — used to keep the best row per intent.
INTENT_TABLES = {
    "insurance": {("insurance", "insurance_policies"), ("insurance", "customers")},
    "claim": {("insurance", "claims")},
    "agent": {("insurance", "agents"), ("insurance", "branches")},
    "theft": {("theft", "theft_records"), ("theft", "firs"), ("theft", "recoveries"),
              ("theft", "police_stations")},
    "scrap": {("theft", "shredding_certificates")},
    "ownership": {("vehicles", "owners"), ("vehicles", "ownership_transfers")},
    "dealer": {("vehicles", "dealers")},
    "vehicle": {("vehicles", "vehicle_models"), ("vehicles", "vehicles")},
    "compliance": {("rto", "challans"), ("rto", "fitness_certificates"),
                   ("rto", "puc_certificates")},
    "registration": {("rto", "rto_records"), ("rto", "rto_offices")},
}
# Round 2: identifier discovered somewhere -> where else it can be looked up.
#   (identifier, target source, table, column, match)
CROSS_LINKS = (
    ("phones", "vehicles", "owners", "phone", "exact"),
    ("phones", "insurance", "customers", "phone", "exact"),
    ("phones", "theft", "firs", "complainant_phone", "exact"),
    ("fir_nos", "theft", "firs", "fir_no", "exact"),
    ("policy_nos", "insurance", "insurance_policies", "policy_no", "exact"),
    ("names", "vehicles", "owners", "full_name", "similar"),
    ("names", "insurance", "customers", "customer_name", "similar"),
    ("names", "theft", "firs", "complainant_name", "similar"),
)
STOPWORDS = set("""a an the is was were are be been of for to in on at by with and or not it its
this that these those what which who whom whose when where how why does do did has have had
any all show me tell give find list there their his her him he she they them my our your
about from into than then also if ever still yet please can could would should get got""".split())

STATE_CODES = set("AN AP AR AS BR CH CG DD DL DN GA GJ HR HP JK JH KA KL LA LD MH ML MN MP MZ "
                  "NL OD OR PB PY RJ SK TN TS TR UP UK WB".split())
PLATE_QUERY_RE = re.compile(
    r"\b([A-Za-z]{2})[\s-]?([0-9OoIl]{1,2})[\s-]?([A-Za-z0-9]{1,3})[\s-]?([0-9OoIlSsBb@#*?]{3,4})\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)")
ID_RES = {
    "fir_nos": re.compile(r"\bFIR/[A-Z0-9]+/\d{4}/\d+\b", re.I),
    "policy_nos": re.compile(r"\bPOL[-/]?[A-Z]*\d{3,}\b", re.I),     # POL-0000044, POL1001
    "chassis": re.compile(r"\bCHS\d{6,}\b", re.I),
    "engines": re.compile(r"\bENG\d{6,}\b", re.I),
    "claim_nos": re.compile(r"\bCLM\d{4,}\b", re.I),
}
NAME_RE = re.compile(r"\b(?:owned by|owner|customer|complainant|named|by|of|for|about|against|"
                     r"regarding|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")
# Fallback: any run of 2-3 Capitalised words ("Simran Kapoor's red Maruti ...", no trigger word).
NAME_ANY_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2})(?:['\u2019]s)?\b")
# Capitalised words that are NOT person names (months, cities, car makes, query openers ...).
NOT_NAME_WORDS = set("""january february march april may june july august september october november
december monday tuesday wednesday thursday friday saturday sunday delhi noida gurugram gurgaon
ghaziabad faridabad lucknow meerut mumbai pune chennai kolkata jaipur bengaluru hyderabad
maruti suzuki hyundai tata mahindra honda toyota kia ford renault nissan skoda volkswagen mg
baleno swift creta nexon city verna innova polo punto alto wagonr dzire seltos thar fir police
station complaint theft record records vehicle insurance policy claim registration transfer
show tell give find list what which who whom when where how does did has have any was were
the this that there please also are lajpat nagar vaishali""".split())


# ---------------------------------------------------------------------------
# A. understand the query
# ---------------------------------------------------------------------------
def parse_query(text: str) -> dict:
    text = text or ""
    found = {"plates": [], "plate_variants": [], "phones": [], "names": [],
             "fir_nos": [], "policy_nos": [], "chassis": [], "engines": [], "claim_nos": []}
    consumed = []
    for key, rx in ID_RES.items():
        for m in rx.finditer(text):
            value = m.group(0).upper()
            if value not in found[key]:
                found[key].append(value)
            consumed.append(m.group(0))
    for m in PHONE_RE.finditer(text):
        if m.group(1) not in found["phones"]:
            found["phones"].append(m.group(1))
        consumed.append(m.group(0))
    for m in PLATE_QUERY_RE.finditer(text):
        raw = m.group(0)
        if m.group(1).upper() not in STATE_CODES or any(raw in c for c in consumed):
            continue
        correction = correct_plate(raw)
        if not (correction.get("pattern_ok") or correction.get("corrected")):
            continue
        key = normalize_plate(correction.get("cleaned") or raw)
        if key and key not in found["plates"]:
            found["plates"].append(key)
            for variant in [key] + list(correction.get("variants") or []):
                variant = normalize_plate(variant)
                if variant and variant not in found["plate_variants"]:
                    found["plate_variants"].append(variant)
        consumed.append(raw)
    def _clean_name(raw):
        words = [w for w in raw.split() if w.lower() not in NOT_NAME_WORDS]
        return " ".join(words)

    for rx in (NAME_RE, NAME_ANY_RE):          # trigger-word names first, then any capitalised run
        for m in rx.finditer(text):
            name = _clean_name(m.group(1).strip())
            if name and name.lower() not in {n.lower() for n in found["names"]} \
                    and not any(name.lower() in n.lower() for n in found["names"]):
                found["names"].append(name)

    rest = text
    for piece in consumed:
        rest = rest.replace(piece, " ")
    words = [w for w in re.findall(r"[a-z]+", rest.lower()) if len(w) >= 3]
    terms = [w for w in dict.fromkeys(words) if w not in STOPWORDS]
    intents = [i for i, lex in INTENT_LEXICON.items() if set(terms) & set(lex)]
    found.update(terms=terms, intents=intents, text=text)
    return found


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _call(source: str, payload: dict) -> dict:
    """POST /api/context on one source; never raises (status in the result)."""
    t0 = time.perf_counter()
    try:
        data = source_context(source, payload)
        return {"ok": True, "data": data, "status": "ok",
                "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except SourceError as exc:
        status = ("phase2_api" if exc.status == 404 else
                  "not_served" if exc.status == 400 else "unreachable")
        return {"ok": False, "data": None, "status": status, "error": str(exc),
                "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "data": None, "status": "error", "error": str(exc),
                "ms": round((time.perf_counter() - t0) * 1000, 1)}


def _payload(seeds, match, parsed, depth):
    return {"seeds": seeds, "match": match, "query_terms": parsed["terms"],
            "intents": parsed["intents"], "max_depth": depth}


def _run_calls(jobs: list[dict]) -> list[dict]:
    """jobs: [{"source", "payload", ...}] -> same dicts with "result" filled, in parallel."""
    if not jobs:
        return jobs
    with ThreadPoolExecutor(max_workers=min(len(jobs), 12)) as pool:
        for job, result in zip(jobs, pool.map(lambda j: _call(j["source"], j["payload"]), jobs)):
            job["result"] = result
    return jobs


def _phase2_nodes(source: str, entity: dict) -> list[dict]:
    """Context for a source that cannot run /api/context: its Phase 2 record."""
    row = (entity or {}).get("records", {}).get(source)
    if not row:
        return []
    table = SOURCE_TABLES[source][0]
    return [{"id": f"{table}:{row.get('id')}", "table": table, "hop": 0, "relevance": 1.0,
             "via": "Phase 2 record (entity matching)", "row": row, "why": {}}]


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
def discover(query: str, plate: Optional[str] = None, details: Optional[dict] = None,
             depth: int = DEFAULT_DEPTH, round2: bool = True) -> dict:
    """Build the query context. `plate` = a plate the operator picked from candidates."""
    t_start = time.perf_counter()
    parsed = parse_query(query)
    if plate:
        key = normalize_plate(plate)
        parsed["plates"] = [key] + [p for p in parsed["plates"] if p != key]
        parsed["plate_variants"] = [key]
    out = {"query": query, "parsed": parsed, "intents": parsed["intents"],
           "status": "ok", "message": None, "candidates": [], "vehicle": None,
           "entity_links": [], "calls": [], "nodes": [], "edges": [], "cross_links": [],
           "identifiers": {}, "places": [], "date_window": None, "description": ""}

    # ---------------- B. resolve the vehicle (Phase 2 entity matching)
    entity = None
    if parsed["plate_variants"]:
        outcome = identify(parsed["plate_variants"], details or {})
        candidates = [c for c in outcome["candidates"] if c["score"] >= CHOOSE_MIN_SCORE]
        out["candidates"] = [{"plate": c["plate"], "score": round(c["score"], 3),
                              "sources": c["sources"]} for c in candidates]
        chosen = None
        if plate:
            chosen = next((c for c in candidates if c["plate"] == normalize_plate(plate)), None)
        elif outcome["auto"] or (candidates and candidates[0]["plate_score"] >= 0.999
                                 and candidates[0]["plate"] in parsed["plate_variants"]):
            chosen = candidates[0]
        if chosen is None and candidates and not (parsed["phones"] or parsed["fir_nos"]
                                                  or parsed["policy_nos"]):
            out.update(status="choose",
                       message="Several registered vehicles look like this plate and none "
                               "is clearly the best. Pick the right one.")
            out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            return out
        if chosen is not None:
            entity = chosen["entity"]
            out["vehicle"] = build_result(chosen["plate"], entity, outcome["source_status"])
            out["entity_links"] = out["vehicle"].get("entity_links", [])
        elif not candidates and not any(parsed[k] for k in
                                        ("phones", "fir_nos", "policy_nos", "names")):
            down = [SOURCE_NAMES.get(src, src) for src, st in outcome["source_status"].items()
                    if not st["available"]]
            if len(down) == len(outcome["source_status"]):
                out.update(status="unavailable",
                           message="No source database could be reached: "
                                   + ", ".join(down) + ". Is source_api.py running there?")
            else:
                out.update(status="not_found",
                           message="No vehicle with a similar plate in any source database"
                                   + (f" (unreachable: {', '.join(down)})." if down else "."))
            out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
            return out

    # ---------------- C. round 1: every source discovers its own context
    jobs, used_seeds = [], set()
    for source in SOURCES:
        seeds = []
        link = (entity or {}).get("links", {}).get(source)
        if link and link.get("value"):
            table, _db, column = SOURCE_TABLES[source]
            seeds.append({"table": table, "column": column, "values": [link["value"]]})
            used_seeds.add((source, table, column, normalize_plate(link["value"])))
        for key, tgt_source, table, column, match in CROSS_LINKS:  # identifiers typed by user
            if tgt_source != source or match != "exact" or not parsed.get(key):
                continue
            seeds.append({"table": table, "column": column,
                          "values": parsed[key][:MAX_SEED_VALUES]})
            used_seeds.update((source, table, column, str(v)) for v in parsed[key])
        if seeds:
            jobs.append({"round": 1, "source": source, "seeds": seeds,
                         "payload": _payload(seeds, "exact", parsed, depth)})
        if parsed["names"] and not entity:
            for key, tgt_source, table, column, match in CROSS_LINKS:
                if key == "names" and tgt_source == source:
                    s = [{"table": table, "column": column, "values": parsed["names"]}]
                    jobs.append({"round": 1, "source": source, "seeds": s,
                                 "payload": _payload(s, "similar", parsed, depth)})
    _run_calls(jobs)

    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def absorb(job, factor=1.0, link=None):
        result = job["result"]
        data = result.get("data") or {}
        job_nodes = data.get("nodes") or []
        if not result["ok"] and job["round"] == 1 and result["status"] in (
                "phase2_api", "not_served"):
            job_nodes = _phase2_nodes(job["source"], entity)      # degrade gracefully
            result["fallback"] = bool(job_nodes)
        for node in job_nodes:
            key = f"{job['source']}:{node['id']}"
            relevance = round(node["relevance"] * factor, 4)
            if key in nodes and nodes[key]["relevance"] >= relevance:
                continue
            nodes[key] = dict(node, key=key, source=job["source"], round=job["round"],
                              relevance=relevance, link=link)
        for edge in data.get("edges") or []:
            edges.append(dict(edge, source=job["source"]))
        out["calls"].append({
            "round": job["round"], "source": job["source"],
            "machine": SOURCE_NAMES.get(job["source"], job["source"]),
            "seeds": job["seeds"], "match": job["payload"]["match"],
            "status": result["status"] + (" (Phase 2 record used)" if result.get("fallback")
                                          else ""),
            "error": result.get("error"), "ms": result["ms"],
            "rows": len(job_nodes), "stats": data.get("stats"),
            "fk_graph": data.get("fk_graph"), "link": link})
        return data.get("identifiers") or {}

    origin_ids: dict[str, dict] = {}       # identifier value -> sources it came from
    for job in jobs:
        ids = absorb(job)
        for key, values in ids.items():
            if key == "dates":
                continue
            for value in values:
                origin_ids.setdefault(key, {}).setdefault(value, set()).add(job["source"])
    # sources with an entity record but no seed call at all (should not happen) / unreachable
    for source in SOURCES:
        if not any(j["source"] == source for j in jobs) and (entity or {}).get(
                "records", {}).get(source):
            for node in _phase2_nodes(source, entity):
                key = f"{source}:{node['id']}"
                nodes[key] = dict(node, key=key, source=source, round=1, link=None)

    # ---------------- D. round 2: discovered identifiers -> the OTHER databases
    if round2:
        jobs2 = []
        have_phone = bool(origin_ids.get("phones"))
        for key, tgt_source, table, column, match in CROSS_LINKS:
            if key == "names" and have_phone:
                continue                      # a phone identifies a person; a name does not
            values = []
            for value, origins in origin_ids.get(key, {}).items():
                if tgt_source in origins:
                    continue                  # that source already walked from it
                if (tgt_source, table, column, str(value)) in used_seeds:
                    continue
                values.append(value)
            if not values:
                continue
            seeds = [{"table": table, "column": column, "values": values[:MAX_SEED_VALUES]}]
            for value in values:
                used_seeds.add((tgt_source, table, column, str(value)))
            jobs2.append({"round": 2, "source": tgt_source, "seeds": seeds,
                          "link": {"identifier": key, "values": values[:MAX_SEED_VALUES],
                                   "from": sorted({o for v in values
                                                   for o in origin_ids[key][v]}),
                                   "match": match},
                          "payload": _payload(seeds, match, parsed, max(1, depth - 1))})
        # other vehicles of the owner -> their records elsewhere (ownership questions only).
        # Each is resolved with Phase 2 entity matching, so a database that stores that
        # car under a noisy plate (e.g. 'DL16KF68O2') is still reached, and a neighbouring
        # plate (one digit different) is never mistaken for it.
        if "ownership" in parsed["intents"]:
            main = {normalize_plate(l.get("value")) for l in
                    (entity or {}).get("links", {}).values()}
            others = [p for p, o in origin_ids.get("plates", {}).items()
                      if "vehicles" in o and p not in main][:MAX_OTHER_VEHICLES]
            stored = {source: [] for source in ("insurance", "rto", "theft")}
            for other in others:
                try:
                    resolved = identify([other])
                except Exception:
                    continue
                match = next((c for c in resolved["candidates"] if c["plate"] == other), None)
                for source, link in ((match or {}).get("entity", {}).get("links") or {}).items():
                    if source in stored and link.get("value"):
                        stored[source].append(link["value"])
            for source, values in stored.items():
                if not values:
                    continue
                table, _db, column = SOURCE_TABLES[source]
                seeds = [{"table": table, "column": column, "values": values[:MAX_SEED_VALUES]}]
                jobs2.append({"round": 2, "source": source, "seeds": seeds,
                              "link": {"identifier": "plates (other vehicles of the owner)",
                                       "values": values[:MAX_SEED_VALUES], "from": ["vehicles"],
                                       "match": "entity matching"},
                              "payload": _payload(seeds, "exact", parsed, 1)})
        _run_calls(jobs2)
        for job in jobs2:
            factor = ROUND2_PENALTY * (NAME_LINK_PENALTY if job["link"]["identifier"] == "names"
                                       else 1.0)
            absorb(job, factor=factor, link=job["link"])
            found = (job["result"].get("data") or {}).get("stats", {}).get("rows_returned", 0)
            out["cross_links"].append(dict(job["link"], target=job["source"],
                                           target_table=job["seeds"][0]["table"],
                                           target_column=job["seeds"][0]["column"],
                                           status=job["result"]["status"], rows=found))

    # ---------------- E. accumulate + prune
    ranked = sorted(nodes.values(), key=lambda n: (-n["relevance"], n["round"], n["hop"]))
    keep = ranked[:MAX_CONTEXT_NODES]
    kept_keys = {n["key"] for n in keep}
    for intent in parsed["intents"]:              # never lose the best row of an intent
        wanted = INTENT_TABLES.get(intent, set())
        best = next((n for n in ranked if (n["source"], n["table"]) in wanted), None)
        if best and best["key"] not in kept_keys:
            keep.append(best)
            kept_keys.add(best["key"])
    out["nodes"] = keep
    out["pruned_nodes"] = len(nodes) - len(keep)
    kept_ids = {(n["source"], n["id"]) for n in keep}
    out["edges"] = [e for e in edges if (e["source"], e["from"]) in kept_ids
                    and (e["source"], e["to"]) in kept_ids]
    out["coverage"] = {i: any((n["source"], n["table"]) in INTENT_TABLES.get(i, set())
                              for n in keep) for i in parsed["intents"]}
    _summarise(out, keep, parsed, entity)
    out["elapsed_ms"] = round((time.perf_counter() - t_start) * 1000, 1)
    return out


# ---------------------------------------------------------------------------
# context summary used by the document search
# ---------------------------------------------------------------------------
PLATE_COLUMNS = {"reg_plate", "vehicle_number", "car_id", "plate_no", "vehicle_plate"}
PERSON_COLUMNS = {"full_name", "customer_name", "complainant_name", "owner_name"}
PERSON_TABLES = {"owners", "customers", "firs", "vehicles"}   # not agents, dealers, stations
ID_COLUMNS = {"fir_no": "fir_nos", "policy_no": "policy_nos", "chassis_no": "chassis",
              "engine_no": "engines", "certificate_no": "certificates",
              "claim_no": "claim_nos"}


def _summarise(out: dict, nodes: list[dict], parsed: dict, entity: Optional[dict]):
    ids = {k: [] for k in ("plates", "phones", "names", "fir_nos", "policy_nos", "chassis",
                           "engines", "certificates", "claim_nos")}

    def add(key, value):
        value = str(value or "").strip()
        if value and value not in ids[key]:
            ids[key].append(value)

    for key in ids:                                   # typed by the user
        for value in parsed.get(key, []):
            add(key, value)
    for link in (entity or {}).get("links", {}).values():
        add("plates", normalize_plate(link.get("value")))   # every stored spelling
    places, event_dates = [], []
    for node in nodes:
        for column, value in node["row"].items():
            if value in (None, ""):
                continue
            if column in PLATE_COLUMNS:
                add("plates", normalize_plate(value))
            elif "phone" in column:
                if node["table"] in PERSON_TABLES:
                    add("phones", re.sub(r"\D", "", str(value))[-10:])
            elif column in PERSON_COLUMNS:
                if node["table"] in PERSON_TABLES:
                    add("names", value)
            elif column in ID_COLUMNS:
                add(ID_COLUMNS[column], value)
            elif column in ("city", "location", "rto_office") and value not in places:
                places.append(str(value))
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(value)) and "birth" not in column \
                    and node["table"] != "vehicle_models":
                event_dates.append(str(value)[:10])
    out["identifiers"] = {k: v for k, v in ids.items() if v}
    out["places"] = places[:10]
    if event_dates:
        lo = date.fromisoformat(min(event_dates)) - timedelta(days=30)
        hi = date.fromisoformat(max(event_dates)) + timedelta(days=90)
        out["date_window"] = [lo.isoformat(), hi.isoformat()]
    vehicle = out.get("vehicle") or {}
    desc = " ".join(str(vehicle.get(k) or "") for k in ("color", "make", "model")).strip()
    out["description"] = " ".join(x for x in [desc] + parsed["intents"] + parsed["terms"][:8] if x)