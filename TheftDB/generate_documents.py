"""
Phase 3 — LLM-generated unstructured documents (FIRs, claim reports, challan notices ...).

Run on M1 (the coordinator) once, after the Phase 3 table data has been generated.
It writes each machine's documents into that machine's output folder; copy them to
the laptop with the rest of its data (PDF guide, Section 3.2 / 10.1).

HOW THE LLM IS USED (two safe stages)
  Stage 1  TEMPLATES  The LLM writes many differently-worded documents per type with
                      {placeholders} instead of identifiers (plate, names, dates ...).
                      Every template is validated: required placeholders present,
                      no unknown placeholders, and NO invented plate / phone / number.
  Stage 2  FILL       Python fills the templates with the REAL values from your tables
                      and adds deliberate noise (OCR-style plates, misspelt names,
                      mixed date formats). Because Python inserts every identifier,
                      the ground truth in manifest.csv is always exact.
  Optional REWRITE    --rewrite 0.3 lets the LLM paraphrase 30% of the filled documents
                      once more for extra variety. Each rewrite is checked: every
                      identifier must still be present exactly, and no new plate /
                      phone may appear; otherwise the template version is kept.

Every prompt and every raw LLM answer is saved under phase3_docs/ (Rubric 4).

PROVIDERS (choose with LLM_PROVIDER)
  anthropic   ANTHROPIC_API_KEY=...            LLM_MODEL (default claude-haiku-5-5)
  openai      OPENAI_API_KEY=...  OPENAI_BASE_URL (default https://api.openai.com/v1)
              -> also works with any OpenAI-compatible server, e.g. FREE, LOCAL, no key:
                 ollama pull qwen2.5:3b       (~2 GB download, ~3 GB RAM; qwen2.5:1.5b for 4 GB)
                 OPENAI_BASE_URL=http://localhost:11434/v1  LLM_MODEL=qwen2.5:3b  LLM_BATCH=3
  mock        no LLM, built-in sample templates (for testing the pipeline offline)

  Local models are slower: templates are requested in small batches (LLM_BATCH, default
  4 per call) and each call may take up to LLM_TIMEOUT seconds (default 600).

USAGE
  python3 phase3/generate_documents.py --data phase3_out --docs-root phase3_out \
          --templates-per-type 10 --seed 42
  python3 phase3/generate_documents.py ... --reuse-templates      # skip stage 1
  python3 phase3/generate_documents.py ... --rewrite 0.3          # optional stage 3

INPUT (written by the Phase 3 data generator; one CSV per table, columns as in the
PDF DDL; missing files simply mean that document type is skipped):
  <data>/M2_registration/ vehicles.csv owners.csv ownership_transfers.csv
  <data>/M3_insurance/    insurance_policies.csv customers.csv agents.csv branches.csv claims.csv
  <data>/M4_rto/          rto_records.csv rto_offices.csv fitness_certificates.csv challans.csv
  <data>/M5_theft/        theft_records.csv police_stations.csv firs.csv recoveries.csv

OUTPUT
  <docs-root>/<machine>/docs/<doc_type>/<doc_id>.txt
  <docs-root>/<machine>/manifest.csv      (ground truth: evaluation only, never used by search)
  phase3_docs/prompts/llm_templates_<doc_type>.md
  phase3_docs/generated/llm_raw_<doc_type>.txt
  phase3/templates/<doc_type>.json        (validated templates, reusable)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import string
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Document types: machine, required / optional placeholders, what they describe
# ---------------------------------------------------------------------------
DOC_TYPES = {
    "fir_narrative": {
        "machine": "M5_theft", "count": 150,
        "required": ["fir_no", "plate", "complainant", "theft_date"],
        "optional": ["station", "city", "filed_on", "phone", "vehicle", "area", "time"],
        "about": "a First Information Report (FIR) filed at an Indian police station by a "
                 "vehicle owner whose car was stolen; written in the formal, slightly "
                 "bureaucratic style of an Indian police record",
    },
    "recovery_report": {
        "machine": "M5_theft", "count": 60,
        "required": ["fir_no", "plate", "recovery_date"],
        "optional": ["location", "condition", "station", "vehicle", "theft_date"],
        "about": "a police report stating that a stolen vehicle was recovered, where it was "
                 "found and in what condition",
    },
    "news_article": {
        "machine": "M5_theft", "count": 40,
        "required": ["city", "month"],
        "optional": ["count", "vehicle", "plate", "area"],
        "about": "a short local Indian newspaper article about a rise in vehicle thefts in a "
                 "city; some articles mention one specific vehicle, most do not",
    },
    "claim_report": {
        "machine": "M3_insurance", "count": 150,
        "required": ["claim_no", "policy_no", "plate", "customer", "incident_date"],
        "optional": ["phone", "insurer", "claim_type", "amount", "city", "vehicle"],
        "about": "a motor insurance claim form narrative written by the policy holder to the "
                 "insurer. IMPORTANT: the same text is used for accident, theft, fire and flood "
                 "claims, so describe the incident only in general terms (a loss, the damage, "
                 "when and where it happened) and let {claim_type} say what kind it was; never "
                 "describe a collision, a theft, a fire or water specifically",
        # words that tie a claim text to ONE claim type (the type comes from {claim_type})
        "avoid": ["collid", "collision", "skid", "crash", "rear-end", "stole", "stolen", "theft",
                  "thief", "thieves", "burnt", "burned", "flame", "fire", "flood", "water",
                  "submerge", "rain", "fog"],
    },
    "surveyor_note": {
        "machine": "M3_insurance", "count": 80,
        "required": ["claim_no", "plate", "survey_date"],
        "optional": ["surveyor", "assessed_amount", "chassis", "engine", "vehicle", "insurer"],
        "about": "an insurance surveyor's inspection note on a claimed vehicle: verification "
                 "of chassis/engine numbers, damage assessment and recommendation",
    },
    "inspection_report": {
        "machine": "M4_rto", "count": 120,
        "required": ["plate", "inspection_date", "result"],
        "optional": ["office", "inspector", "defects", "vehicle", "expiry_date"],
        "about": "an RTO vehicle fitness inspection report with the result (PASS or FAIL) and "
                 "the defects observed",
    },
    "challan_notice": {
        "machine": "M4_rto", "count": 100,
        "required": ["challan_no", "plate", "offence", "challan_date"],
        "optional": ["location", "fine", "owner", "vehicle"],
        "about": "an Indian traffic e-challan notice sent to a vehicle owner for a traffic "
                 "offence, with the fine and how to pay it",
    },
    "sale_deed": {
        "machine": "M2_registration", "count": 100,
        "required": ["plate", "seller", "buyer", "sale_date"],
        "optional": ["seller_phone", "buyer_phone", "chassis", "engine", "city", "price",
                     "vehicle"],
        "about": "a used-car sale deed / sale agreement between a seller and a buyer in India",
    },
    "transfer_letter": {
        "machine": "M2_registration", "count": 60,
        "required": ["plate", "old_owner", "new_owner", "transfer_date"],
        "optional": ["city", "vehicle", "new_owner_phone"],
        "about": "a letter to the RTO requesting transfer of vehicle ownership from the old "
                 "owner to the new owner",
    },
}

DISTRACTOR_SHARE = 0.20         # extra documents about vehicles NOT in any database
PLATE_NOISE_SHARE = 0.25        # documents whose plate is written OCR-style
NAME_NOISE_SHARE = 0.10

ROOT = Path.cwd()
DOCS_DIR = ROOT / "phase3_docs"
# templates live next to this script: phase3/templates/ (phase3 layout) or
# templates/ (flat layout, e.g. the TheftDB folder)
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

STATE_CODES = ["DL", "UP", "HR", "MH", "KA", "RJ", "PB", "GJ", "TN", "WB", "MP", "TS"]
CITIES = ["Delhi", "Ghaziabad", "Noida", "Gurugram", "Meerut", "Faridabad", "Lucknow",
          "Jaipur", "Pune", "Mumbai", "Bengaluru", "Chandigarh"]
AREAS = ["Raj Nagar", "Indirapuram", "Sector 62", "Karol Bagh", "Lajpat Nagar", "Vaishali",
         "Kaushambi", "Rohini Sector 9", "Civil Lines", "Model Town", "Dwarka Sector 12",
         "Shastri Nagar", "Malviya Nagar", "Nehru Place"]
FIRST = ["Rahul", "Priya", "Amit", "Neha", "Vikas", "Pooja", "Sanjay", "Anjali", "Rohit",
         "Kavita", "Manoj", "Sunita", "Deepak", "Ritu", "Arjun", "Meena"]
LAST = ["Sharma", "Verma", "Gupta", "Singh", "Yadav", "Mehta", "Kumar", "Jain", "Agarwal",
        "Chauhan", "Malhotra", "Saxena"]
MAKES = [("Maruti", "Swift"), ("Hyundai", "Creta"), ("Tata", "Nexon"), ("Honda", "City"),
         ("Mahindra", "XUV700"), ("Kia", "Seltos"), ("Toyota", "Innova")]
COLORS = ["white", "silver", "grey", "red", "black", "blue"]
CONDITIONS = ["intact", "minor scratches", "damaged front bumper", "number plates removed",
              "stereo and battery missing", "partially stripped"]
DEFECTS_FAIL = ["worn front brake pads", "headlamp alignment out of range",
                "excessive smoke emission", "cracked windshield", "tyre tread below limit"]
SURVEYORS = ["R. K. Bansal", "S. Iyer", "M. Qureshi", "A. Pillai", "V. Rathore"]

PLATE_RE = re.compile(r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{3,4}\b", re.I)
PHONE_RE = re.compile(r"\b[6-9]\d{9}\b")
LONG_NUMBER_RE = re.compile(r"\d{4,}")
PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
MAX_PLACEHOLDER_USES = 3      # "collided with a nearby {vehicle}" = the car hits itself


# ---------------------------------------------------------------------------
# LLM client (stdlib only)
# ---------------------------------------------------------------------------
class LLMError(RuntimeError):
    pass


LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "600"))
LLM_BATCH = max(1, int(os.getenv("LLM_BATCH", "4")))


def _post_json(url, payload, headers, timeout=LLM_TIMEOUT):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as exc:
        raise LLMError(f"cannot reach {url}: {exc.reason}")


def call_llm(prompt: str, temperature: float = 0.9, max_tokens: int = 4000) -> str:
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise LLMError("Set ANTHROPIC_API_KEY (or choose LLM_PROVIDER=openai / mock).")
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"model": os.getenv("LLM_MODEL", "claude-haiku-5-5"), "max_tokens": max_tokens,
             "temperature": temperature,
             "messages": [{"role": "user", "content": prompt}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return "".join(block.get("text", "") for block in data.get("content", []))
    if provider == "openai":
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        data = _post_json(
            f"{base}/chat/completions",
            {"model": os.getenv("LLM_MODEL", "gpt-4o-mini"), "temperature": temperature,
             "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
            {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'none')}"})
        return data["choices"][0]["message"]["content"]
    if provider == "mock":
        return _mock_answer(prompt)
    raise LLMError(f"Unknown LLM_PROVIDER {provider!r} (anthropic | openai | mock).")


def _mock_answer(prompt: str) -> str:
    """Offline stand-in: returns simple templates so the pipeline can be tested."""
    doc_type = re.search(r"DOCUMENT TYPE: (\w+)", prompt)
    if doc_type is None:            # rewrite request: echo the document back unchanged
        return prompt.split("DOCUMENT:\n", 1)[-1].strip()
    spec = DOC_TYPES[doc_type.group(1)]
    fields = spec["required"] + spec["optional"][:3]
    body = " ".join(f"{f.replace('_', ' ').title()}: {{{f}}}." for f in fields)
    filler = ("This is an offline sample text used only to test the document pipeline. "
              "It describes the matter in plain words so that the search index has enough "
              "ordinary language to work with, without any real identifiers in it. ")
    return json.dumps([f"Mock template {i}. {filler}{body} {filler}" for i in range(1, 4)])


# ---------------------------------------------------------------------------
# Stage 1: templates
# ---------------------------------------------------------------------------
TEMPLATE_PROMPT = """You are writing realistic sample documents for a university database project.

DOCUMENT TYPE: {doc_type}
DESCRIPTION: {about}

Write {n} different documents of this type. Make them genuinely varied: different
structure, length (80-220 words), tone, level of detail and order of information, as
real documents written by different people would be. Use Indian context and wording.

Instead of concrete identifiers, use ONLY these placeholders, written exactly like this:
  Required in EVERY document: {required}
  Optional (use some of them, vary which): {optional}

Strict rules:
- Do NOT invent any vehicle registration number, phone number, FIR/policy/claim/challan
  number, chassis/engine number, person name or exact date. Those come ONLY from the
  placeholders. Do not write any number with 4 or more digits.
- You may invent harmless details: weather, what the witness saw, colour of a gate,
  street descriptions, times of day in words, general amounts in words.
- Use each placeholder at most twice. Do not use any other {{curly}} placeholders.

Return ONLY a JSON array of {n} strings (one document per string), no other text."""


def _extract_json_array(text: str):
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("no JSON array in the answer")
    return json.loads(text[start:end + 1])


def validate_template(template: str, spec: dict) -> list[str]:
    """Return the problems with one template (empty list = valid)."""
    problems = []
    used = set(PLACEHOLDER_RE.findall(template))
    allowed = set(spec["required"]) | set(spec["optional"])
    missing = [p for p in spec["required"] if p not in used]
    unknown = sorted(used - allowed)
    if missing:
        problems.append(f"missing required {missing}")
    if unknown:
        problems.append(f"unknown placeholders {unknown}")
    overused = sorted(p for p in used if template.count("{" + p + "}") > MAX_PLACEHOLDER_USES)
    if overused:
        problems.append(f"placeholder used more than {MAX_PLACEHOLDER_USES} times {overused}")
    bare = PLACEHOLDER_RE.sub("", template)
    hits = [w for w in spec.get("avoid", []) if re.search(rf"\b{w}", bare, re.I)]
    if hits:
        problems.append(f"describes one specific case ({', '.join(hits[:4])}) — must fit all")
    if PLATE_RE.search(bare):
        problems.append("contains an invented plate")
    if PHONE_RE.search(bare) or LONG_NUMBER_RE.search(bare):
        problems.append("contains an invented phone / long number")
    if not 40 <= len(bare.split()) <= 320:
        problems.append("length out of range")
    return problems


def build_templates(doc_type: str, n: int, max_rounds: int = 3) -> list[str]:
    spec = DOC_TYPES[doc_type]
    prompt = TEMPLATE_PROMPT.format(
        doc_type=doc_type, about=spec["about"], n=n,
        required=", ".join("{" + p + "}" for p in spec["required"]),
        optional=", ".join("{" + p + "}" for p in spec["optional"]))
    (DOCS_DIR / "prompts").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "generated").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "prompts" / f"llm_templates_{doc_type}.md").write_text(
        f"# Prompt — {doc_type}\n\nProvider: {os.getenv('LLM_PROVIDER', 'anthropic')}, "
        f"model: {os.getenv('LLM_MODEL', 'default')}, date: {datetime.now():%Y-%m-%d %H:%M}\n\n"
        f"```\n{prompt}\n```\n", encoding="utf-8")

    accepted, rejected, raw_log = [], [], []
    calls, max_calls = 0, max_rounds * max(1, -(-n // LLM_BATCH))   # retries included
    while len(accepted) < n and calls < max_calls:
        calls += 1
        ask = min(LLM_BATCH, n - len(accepted))
        batch_prompt = prompt.replace(f"Write {n} different", f"Write {ask} different") \
                             .replace(f"array of {n} strings", f"array of {ask} strings")
        print(f"    {doc_type}: LLM call {calls} (asking for {ask}, have {len(accepted)}/{n}) ...",
              flush=True)
        started = time.time()
        try:
            answer = call_llm(batch_prompt)
        except LLMError as exc:
            raw_log.append(f"=== call {calls}: ERROR {exc} ===\n")
            print(f"      failed: {exc}")
            continue
        raw_log.append(f"=== call {calls} ({time.time() - started:.0f}s) ===\n{answer}\n")
        try:
            candidates = _extract_json_array(answer)
        except (ValueError, json.JSONDecodeError) as exc:
            rejected.append(("(whole answer)", f"not a JSON array: {exc}"))
            continue
        for template in candidates:
            if not isinstance(template, str):
                continue
            problems = validate_template(template, spec)
            if problems:
                rejected.append((template[:80], "; ".join(problems)))
            elif template not in accepted:
                accepted.append(template)

    raw_log.append("=== rejected templates (validation) ===\n" + "\n".join(
        f"- {why}: {head}..." for head, why in rejected))
    (DOCS_DIR / "generated" / f"llm_raw_{doc_type}.txt").write_text(
        "\n".join(raw_log), encoding="utf-8")
    if not accepted:
        raise LLMError(f"No valid templates for {doc_type}; see phase3_docs/generated/"
                       f"llm_raw_{doc_type}.txt")
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    (TEMPLATE_DIR / f"{doc_type}.json").write_text(json.dumps(accepted, indent=2,
                                                              ensure_ascii=False),
                                                   encoding="utf-8")
    print(f"  {doc_type}: {len(accepted)} templates accepted, {len(rejected)} rejected")
    return accepted


# ---------------------------------------------------------------------------
# Noise (applied by Python, never by the LLM)
# ---------------------------------------------------------------------------
OCR_SWAP = {"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "O": "0", "I": "1"}


def noisy_plate(plate: str, rng: random.Random) -> str:
    """'UP09AI8815' -> 'UP 09 AI 88I5' / 'UP-09-AI-8815' / 'up09ai8815' ..."""
    match = re.fullmatch(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{1,4})", plate)
    parts = list(match.groups()) if match else [plate]
    text = rng.choice([" ", "-", " "]).join(parts) if match else plate
    chars = list(text)
    digit_positions = [i for i, ch in enumerate(chars) if ch in OCR_SWAP]
    for i in rng.sample(digit_positions, k=min(len(digit_positions), rng.choice([1, 1, 2]))):
        chars[i] = OCR_SWAP[chars[i]]
    text = "".join(chars)
    return text.lower() if rng.random() < 0.1 else text


def noisy_name(name: str, rng: random.Random) -> str:
    parts = name.split()
    if len(parts) >= 2 and rng.random() < 0.5:
        return f"{parts[-1]}, {' '.join(parts[:-1])}"
    if len(name) > 4:
        i = rng.randrange(1, len(name) - 1)
        return name[:i] + name[i + 1:]                  # drop one letter
    return name


def fmt_date(value, rng: random.Random) -> str:
    try:
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    day = d.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return rng.choice([d.strftime("%d-%m-%Y"), d.strftime("%d/%m/%Y"),
                       f"{day}{suffix} {d.strftime('%B %Y')}", d.strftime("%d %b %Y")])


def norm_plate(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


# ---------------------------------------------------------------------------
# Facts from the Phase 3 table CSVs
# ---------------------------------------------------------------------------
def read_csv(folder: Path, name: str) -> list[dict]:
    path = folder / f"{name}.csv"
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def index_by(rows, key):
    return {str(r.get(key)): r for r in rows}


class Facts:
    def __init__(self, data: Path):
        reg, ins, rto, thf = (data / "M2_registration", data / "M3_insurance",
                              data / "M4_rto", data / "M5_theft")
        self.vehicles = read_csv(reg, "vehicles")
        self.owners = index_by(read_csv(reg, "owners"), "owner_id")
        self.transfers = read_csv(reg, "ownership_transfers")
        self.policies = index_by(read_csv(ins, "insurance_policies"), "id")
        self.customers = index_by(read_csv(ins, "customers"), "customer_id")
        self.agents = index_by(read_csv(ins, "agents"), "agent_id")
        self.branches = index_by(read_csv(ins, "branches"), "branch_id")
        self.claims = read_csv(ins, "claims")
        self.rto_records = index_by(read_csv(rto, "rto_records"), "id")
        self.offices = index_by(read_csv(rto, "rto_offices"), "office_id")
        self.fitness = read_csv(rto, "fitness_certificates")
        self.challans = read_csv(rto, "challans")
        self.thefts = read_csv(thf, "theft_records")
        self.stations = index_by(read_csv(thf, "police_stations"), "station_id")
        self.firs = index_by(read_csv(thf, "firs"), "fir_id")
        self.recoveries = read_csv(thf, "recoveries")
        self.theft_by_id = index_by(self.thefts, "id")
        self.vehicle_by_id = index_by(self.vehicles, "id")
        self.vehicle_by_plate = {norm_plate(v.get("reg_plate")): v for v in self.vehicles}
        self.known_phones = {re.sub(r"\D", "", str(r.get(k) or ""))[-10:]
                             for rows, k in ((self.owners.values(), "phone"),
                                             (self.customers.values(), "phone"),
                                             (self.firs.values(), "complainant_phone"))
                             for r in rows if r.get(k)}
        self.known_plates = set(self.vehicle_by_plate) | {
            norm_plate(r.get("plate_no")) for r in self.thefts} | {
            norm_plate(p.get("vehicle_number")) for p in self.policies.values()} | {
            norm_plate(r.get("car_id")) for r in self.rto_records.values()}

    def vehicle_text(self, plate) -> str:
        v = self.vehicle_by_plate.get(norm_plate(plate))
        if not v:
            return "car"
        return " ".join(x for x in (str(v.get("color") or "").lower(), v.get("make"),
                                    v.get("model")) if x) or "car"

    def owner_of(self, plate):
        v = self.vehicle_by_plate.get(norm_plate(plate))
        return self.owners.get(str(v.get("owner_id"))) if v else None


def build_facts(doc_type: str, F: Facts, rng: random.Random) -> list[dict]:
    """One fact dict per document: placeholder values + ground-truth link."""
    out = []
    if doc_type == "fir_narrative":
        for t in F.thefts:
            fir = F.firs.get(str(t.get("fir_id")))
            if not fir:
                continue
            st = F.stations.get(str(fir.get("station_id")), {})
            out.append({"fir_no": fir["fir_no"], "plate": t["plate_no"],
                        "complainant": fir.get("complainant_name") or "the complainant",
                        "theft_date": t["theft_date"], "station": st.get("station_name", ""),
                        "city": st.get("city", ""), "filed_on": fir.get("filed_on", ""),
                        "phone": fir.get("complainant_phone", ""),
                        "vehicle": F.vehicle_text(t["plate_no"]), "area": rng.choice(AREAS),
                        "time": rng.choice(["around 2 AM", "late at night", "early morning",
                                            "between 11 PM and 6 AM", "in the afternoon"]),
                        "_link": ("theft_db", "firs", fir["fir_id"], t["plate_no"])})
    elif doc_type == "recovery_report":
        for r in F.recoveries:
            t = F.theft_by_id.get(str(r.get("theft_id")))
            fir = F.firs.get(str(t.get("fir_id"))) if t else None
            if not t or not fir:
                continue
            st = F.stations.get(str(fir.get("station_id")), {})
            out.append({"fir_no": fir["fir_no"], "plate": t["plate_no"],
                        "recovery_date": r["recovery_date"], "location": r.get("location", ""),
                        "condition": r.get("vehicle_condition") or rng.choice(CONDITIONS),
                        "station": st.get("station_name", ""),
                        "vehicle": F.vehicle_text(t["plate_no"]),
                        "theft_date": t.get("theft_date", ""),
                        "_link": ("theft_db", "recoveries", r["recovery_id"], t["plate_no"])})
    elif doc_type == "news_article":
        by_city_month = {}
        for t in F.thefts:
            fir = F.firs.get(str(t.get("fir_id")))
            city = F.stations.get(str(fir.get("station_id")), {}).get("city") if fir else None
            if city and t.get("theft_date"):
                by_city_month.setdefault((city, str(t["theft_date"])[:7]), []).append(t)
        for (city, month), items in by_city_month.items():
            pick = rng.choice(items)
            mention = rng.random() < 0.5
            out.append({"city": city,
                        "month": datetime.strptime(month, "%Y-%m").strftime("%B %Y"),
                        "count": str(len(items) + rng.randint(3, 15)),
                        "vehicle": F.vehicle_text(pick["plate_no"]),
                        "plate": pick["plate_no"] if mention else "",
                        "area": rng.choice(AREAS),
                        "_link": ("theft_db", "theft_records", pick["id"],
                                  pick["plate_no"] if mention else "")})
    elif doc_type in ("claim_report", "surveyor_note"):
        for c in F.claims:
            p = F.policies.get(str(c.get("policy_id")))
            if not p:
                continue
            cust = F.customers.get(str(p.get("customer_id")), {})
            agent = F.agents.get(str(p.get("agent_id")), {})
            branch = F.branches.get(str(agent.get("branch_id")), {})
            claim_no = c.get("claim_no") or f"CLM{int(c['claim_id']):06d}"
            v = F.vehicle_by_plate.get(norm_plate(p["vehicle_number"]), {})
            if doc_type == "claim_report":
                out.append({"claim_no": claim_no, "policy_no": p["policy_no"],
                            "plate": p["vehicle_number"],
                            "customer": cust.get("customer_name") or "the insured",
                            "incident_date": c["claim_date"], "phone": cust.get("phone", ""),
                            "insurer": p.get("insurer_name", ""),
                            "claim_type": c.get("claim_type", ""),
                            "amount": f"Rs. {float(c.get('amount') or 0):,.0f}",
                            "city": branch.get("city", ""),
                            "vehicle": F.vehicle_text(p["vehicle_number"]),
                            "_link": ("insurance_db", "claims", c["claim_id"],
                                      p["vehicle_number"])})
            else:
                survey = date.fromisoformat(str(c["claim_date"])[:10]) + timedelta(
                    days=rng.randint(2, 10))
                out.append({"claim_no": claim_no, "plate": p["vehicle_number"],
                            "survey_date": survey.isoformat(),
                            "surveyor": rng.choice(SURVEYORS),
                            "assessed_amount": f"Rs. {float(c.get('amount') or 0) * rng.uniform(0.6, 1.0):,.0f}",
                            "chassis": v.get("chassis_no", "as per RC"),
                            "engine": v.get("engine_no", "as per RC"),
                            "vehicle": F.vehicle_text(p["vehicle_number"]),
                            "insurer": p.get("insurer_name", ""),
                            "_link": ("insurance_db", "claims", c["claim_id"],
                                      p["vehicle_number"])})
    elif doc_type == "inspection_report":
        for f in F.fitness:
            r = F.rto_records.get(str(f.get("rto_record_id")))
            if not r:
                continue
            office = F.offices.get(str(r.get("office_id")), {})
            failed = str(f.get("result")).upper() == "FAIL"
            out.append({"plate": r["car_id"], "inspection_date": f["issue_date"],
                        "result": "FAIL" if failed else "PASS",
                        "office": office.get("office_name") or r.get("rto_office", ""),
                        "inspector": f.get("inspector") or "the inspecting officer",
                        "defects": ", ".join(rng.sample(DEFECTS_FAIL, 2)) if failed
                        else "no major defects",
                        "vehicle": F.vehicle_text(r["car_id"]),
                        "expiry_date": f.get("expiry_date", ""),
                        "_link": ("rto_db", "fitness_certificates", f["cert_id"], r["car_id"])})
    elif doc_type == "challan_notice":
        for ch in F.challans:
            r = F.rto_records.get(str(ch.get("rto_record_id")))
            if not r:
                continue
            owner = F.owner_of(r["car_id"]) or {}
            out.append({"challan_no": ch.get("challan_no") or f"CH{int(ch['challan_id']):07d}", "plate": r["car_id"],
                        "offence": ch["offence"], "challan_date": ch["challan_date"],
                        "location": ch.get("location", ""),
                        "fine": f"Rs. {float(ch.get('fine_amount') or 0):,.0f}",
                        "owner": owner.get("full_name", "the registered owner"),
                        "vehicle": F.vehicle_text(r["car_id"]),
                        "_link": ("rto_db", "challans", ch["challan_id"], r["car_id"])})
    elif doc_type in ("sale_deed", "transfer_letter"):
        for tr in F.transfers:
            v = F.vehicle_by_id.get(str(tr.get("vehicle_id")))
            seller = F.owners.get(str(tr.get("from_owner_id")))
            buyer = F.owners.get(str(tr.get("to_owner_id")))
            if not v or not seller or not buyer:
                continue
            if doc_type == "sale_deed":
                out.append({"plate": v["reg_plate"], "seller": seller["full_name"],
                            "buyer": buyer["full_name"], "sale_date": tr["transfer_date"],
                            "seller_phone": seller.get("phone", ""),
                            "buyer_phone": buyer.get("phone", ""),
                            "chassis": v.get("chassis_no", ""), "engine": v.get("engine_no", ""),
                            "city": buyer.get("city", ""),
                            "price": f"Rs. {rng.randrange(150000, 1500000, 5000):,}",
                            "vehicle": F.vehicle_text(v["reg_plate"]),
                            "_link": ("vehicle_registration_db", "ownership_transfers",
                                      tr["transfer_id"], v["reg_plate"])})
            else:
                out.append({"plate": v["reg_plate"], "old_owner": seller["full_name"],
                            "new_owner": buyer["full_name"], "transfer_date": tr["transfer_date"],
                            "city": buyer.get("city", ""), "vehicle": F.vehicle_text(v["reg_plate"]),
                            "new_owner_phone": buyer.get("phone", ""),
                            "_link": ("vehicle_registration_db", "ownership_transfers",
                                      tr["transfer_id"], v["reg_plate"])})
    rng.shuffle(out)
    return out


def distractor_facts(doc_type: str, F: Facts, rng: random.Random, n: int) -> list[dict]:
    """Realistic facts about vehicles/people that exist in NO database."""
    spec = DOC_TYPES[doc_type]
    facts = []
    rng = random.Random(rng.random() * 1e9 + 7919)   # own stream: never repeats the data generator

    def fresh_phone():
        while True:                                   # never a phone of a real person
            phone = str(rng.randint(6000000000, 9999999999))
            if phone not in F.known_phones:
                return phone

    while len(facts) < n:
        plate = (f"{rng.choice(STATE_CODES)}{rng.randint(1, 99):02d}"
                 f"{''.join(rng.choices(string.ascii_uppercase, k=2))}{rng.randint(1000, 9999)}")
        if norm_plate(plate) in F.known_plates:
            continue
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        other = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        day = date(2024, 1, 1) + timedelta(days=rng.randint(0, 700))
        make, model = rng.choice(MAKES)
        values = {
            "fir_no": f"FIR/XX{rng.randint(10, 99)}/{day.year}/{rng.randint(1, 9999):04d}",
            "plate": plate, "complainant": name, "theft_date": day.isoformat(),
            "station": f"{rng.choice(AREAS)} Police Station", "city": rng.choice(CITIES),
            "filed_on": day.isoformat(), "phone": fresh_phone(),
            "vehicle": f"{rng.choice(COLORS)} {make} {model}", "area": rng.choice(AREAS),
            "time": "late at night", "recovery_date": (day + timedelta(days=9)).isoformat(),
            "location": rng.choice(AREAS), "condition": rng.choice(CONDITIONS),
            "month": day.strftime("%B %Y"), "count": str(rng.randint(5, 40)),
            "claim_no": f"CLM9{rng.randint(10000, 99999)}", "policy_no": f"POLX{rng.randint(1000, 9999)}",
            "customer": name, "incident_date": day.isoformat(), "insurer": "an insurer",
            "claim_type": rng.choice(["accident", "theft", "flood"]), "amount": "Rs. 85,000",
            "survey_date": day.isoformat(), "surveyor": rng.choice(SURVEYORS),
            "assessed_amount": "Rs. 60,000", "chassis": "as per RC", "engine": "as per RC",
            "inspection_date": day.isoformat(), "result": rng.choice(["PASS", "FAIL"]),
            "office": f"RTO {rng.choice(CITIES)}", "inspector": rng.choice(SURVEYORS),
            "defects": "no major defects", "expiry_date": (day + timedelta(days=730)).isoformat(),
            "challan_no": f"CH9{rng.randint(100000, 999999)}", "offence": "over-speeding",
            "challan_date": day.isoformat(), "fine": "Rs. 2,000", "owner": name,
            "seller": name, "buyer": other, "sale_date": day.isoformat(),
            "seller_phone": fresh_phone(),
            "buyer_phone": fresh_phone(),
            "price": "Rs. 4,50,000", "old_owner": name, "new_owner": other,
            "transfer_date": day.isoformat(), "new_owner_phone": fresh_phone(),
        }
        fact = {k: values[k] for k in spec["required"] + spec["optional"] if k in values}
        fact["_link"] = ("", "", "", "")
        facts.append(fact)
    return facts


# ---------------------------------------------------------------------------
# Stage 2 (+ optional stage 3): fill, add noise, optionally rewrite
# ---------------------------------------------------------------------------
DATE_FIELDS = {"theft_date", "filed_on", "recovery_date", "incident_date", "survey_date",
               "inspection_date", "expiry_date", "challan_date", "sale_date", "transfer_date"}
NAME_FIELDS = {"complainant", "customer", "owner", "seller", "buyer", "old_owner", "new_owner"}

REWRITE_PROMPT = """Rewrite the document below so that it reads more naturally, as if written by a
different person. Keep the same meaning and roughly the same length.
You MUST keep these exact strings unchanged, character for character:
{keep}
Do NOT add any new vehicle number, phone number, ID number or person name.
Return ONLY the rewritten document.

DOCUMENT:
{doc}"""


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


def fill(template: str, fact: dict, rng: random.Random, is_distractor: bool):
    values, noise = {}, []
    for key, value in fact.items():
        if key.startswith("_"):
            continue
        value = "" if value is None else str(value)
        if key in DATE_FIELDS and value:
            value = fmt_date(value, rng)
        values[key] = value
    if "plate" in values and norm_plate(values["plate"]) and rng.random() < PLATE_NOISE_SHARE:
        values["plate"] = noisy_plate(norm_plate(values["plate"]), rng)
        noise.append("plate")
    for key in NAME_FIELDS & values.keys():
        if values[key] and rng.random() < NAME_NOISE_SHARE:
            values[key] = noisy_name(values[key], rng)
            noise.append(key)
    text = template.format_map(_SafeDict(values))
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    identifiers = [values[k] for k in ("plate", "fir_no", "claim_no", "policy_no", "challan_no",
                                       "phone", "seller_phone", "buyer_phone",
                                       "new_owner_phone", "chassis", "engine")
                   if values.get(k) and values[k] in text and len(values[k]) >= 6]
    return text, noise, identifiers


def rewrite_safely(text: str, identifiers: list[str]) -> tuple[str, bool]:
    try:
        answer = call_llm(REWRITE_PROMPT.format(
            keep="\n".join(f"  - {s}" for s in identifiers), doc=text),
            temperature=0.8, max_tokens=1200).strip()
    except LLMError as exc:
        print(f"    rewrite skipped: {exc}")
        return text, False
    if not all(s in answer for s in identifiers):
        return text, False
    allowed = {norm_plate(s) for s in identifiers}
    for found in PLATE_RE.findall(answer) + PHONE_RE.findall(answer):
        if norm_plate(found) not in allowed:
            return text, False                     # the LLM invented an identifier
    return answer, True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--data", type=Path, default=Path("phase3_out"))
    ap.add_argument("--docs-root", type=Path, default=Path("phase3_out"))
    ap.add_argument("--templates-per-type", type=int, default=10)
    ap.add_argument("--types", nargs="*", default=list(DOC_TYPES))
    ap.add_argument("--reuse-templates", action="store_true")
    ap.add_argument("--templates-only", action="store_true",
                    help="only ask the LLM for templates (no data needed); fill later "
                         "on each laptop with --reuse-templates")
    ap.add_argument("--rewrite", type=float, default=0.0,
                    help="share of documents paraphrased by the LLM (0..1)")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply document counts")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    unknown = [t for t in args.types if t not in DOC_TYPES]
    if unknown:
        sys.exit(f"Unknown document type(s) {unknown}. Choose from: {', '.join(DOC_TYPES)}")

    if args.templates_only:
        print(f"LLM provider: {os.getenv('LLM_PROVIDER', 'anthropic')}  "
              f"model: {os.getenv('LLM_MODEL', '(default)')}  (templates only)")
        for doc_type in args.types:
            path = TEMPLATE_DIR / f"{doc_type}.json"
            if args.reuse_templates and path.is_file():
                print(f"  {doc_type}: kept existing {path}")
                continue
            try:
                build_templates(doc_type, args.templates_per_type)
            except LLMError as exc:
                print(f"  {doc_type}: FAILED — {exc} (re-run later with --reuse-templates "
                      "to keep the types that succeeded)")
        print(f"\ntemplates in {TEMPLATE_DIR}/ — copy this folder (and phase3_docs/) to the "
              "laptops that fill the documents.")
        return

    F = Facts(args.data)
    if not F.vehicles and not F.thefts and not F.claims:
        sys.exit(f"No Phase 3 table CSVs found under {args.data}. Run the data generator first.")

    print(f"LLM provider: {os.getenv('LLM_PROVIDER', 'anthropic')}  "
          f"model: {os.getenv('LLM_MODEL', '(default)')}")
    manifests: dict[str, list[dict]] = {}
    for doc_type in args.types:
        spec = DOC_TYPES[doc_type]
        facts = build_facts(doc_type, F, rng)
        if not facts:
            print(f"  {doc_type}: no source rows, skipped")
            continue
        path = TEMPLATE_DIR / f"{doc_type}.json"
        if args.reuse_templates and path.is_file():
            templates = json.loads(path.read_text(encoding="utf-8"))
        elif args.reuse_templates:
            print(f"  {doc_type}: no templates — {path} is missing. Copy phase3/templates/ "
                  "from the laptop that ran the LLM (or run without --reuse-templates "
                  "where an LLM is available). Skipped.")
            continue
        else:
            templates = build_templates(doc_type, args.templates_per_type)

        n_real = min(len(facts), max(1, int(spec["count"] * args.scale)))
        n_dist = max(1, int(n_real * DISTRACTOR_SHARE))
        batch = [(f, False) for f in facts[:n_real]] + \
                [(f, True) for f in distractor_facts(doc_type, F, rng, n_dist)]
        rng.shuffle(batch)

        out_dir = args.docs_root / spec["machine"] / "docs" / doc_type
        out_dir.mkdir(parents=True, exist_ok=True)
        rewritten = 0
        for i, (fact, is_distractor) in enumerate(batch, 1):
            # use a template whose placeholders all have a value for this document
            # (e.g. news articles that mention no plate never get a {plate} template)
            usable = [n for n, t in enumerate(templates)
                      if all(str(fact.get(p) or "").strip() for p in PLACEHOLDER_RE.findall(t))]
            template_no = rng.choice(usable) if usable else rng.randrange(len(templates))
            text, noise, identifiers = fill(templates[template_no], fact, rng, is_distractor)
            did_rewrite = False
            if args.rewrite and rng.random() < args.rewrite and identifiers:
                text, did_rewrite = rewrite_safely(text, identifiers)
                rewritten += did_rewrite
            doc_id = f"{doc_type}_{i:04d}"
            (out_dir / f"{doc_id}.txt").write_text(text + "\n", encoding="utf-8")
            db, table, pk, plate = fact["_link"]
            if "{plate}" not in templates[template_no]:
                plate = ""          # the text does not name the vehicle (e.g. a general news item)
            manifests.setdefault(spec["machine"], []).append({
                "doc_id": doc_id, "doc_type": doc_type,
                "file": f"docs/{doc_type}/{doc_id}.txt",
                "is_distractor": int(is_distractor),
                "linked_db": db, "linked_table": table, "linked_pk": pk,
                "linked_plate": norm_plate(plate), "template_no": template_no,
                "noise": "|".join(noise), "llm_rewritten": int(did_rewrite)})
        print(f"  {doc_type}: {n_real} documents + {n_dist} distractors -> {out_dir}"
              + (f" ({rewritten} rewritten by LLM)" if args.rewrite else ""))

    fields = ["doc_id", "doc_type", "file", "is_distractor", "linked_db", "linked_table",
              "linked_pk", "linked_plate", "template_no", "noise", "llm_rewritten"]
    for machine, rows in manifests.items():
        path = args.docs_root / machine / "manifest.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(f"manifest: {path} ({len(rows)} documents)")


if __name__ == "__main__":
    main()
