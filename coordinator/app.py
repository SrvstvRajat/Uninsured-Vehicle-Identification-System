# # from flask import Flask, request, render_template_string

# # from mediator import query_vehicle

# # app = Flask(__name__)

# Minimum similarity score required before a fuzzy match can be auto-selected.
FUZZY_MIN_SCORE = 0.60
FUZZY_MIN_MARGIN = 0.07
FUZZY_TOP_K = 5

from flask import Flask, request, render_template_string, redirect, url_for
from werkzeug.utils import secure_filename

import time

from mediator import (query_vehicle, list_candidate_plates, normalize_plate,
                      list_vehicle_profiles)
from fuzzy_match import plate_similarity
from detail_match import (rank_with_details, decide, DETAIL_FIELDS,
                          SECTIONS, DETAIL_LABELS)
from plate_ocr import (recognize_plate_image, MAX_IMAGE_BYTES,
                       PlateOCRInputError, PlateOCREngineError)
from reporting import report_flags
from sql_console import sql_bp          # <-- NEW: federated SQL console

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_IMAGE_BYTES + 1024 * 1024
app.register_blueprint(sql_bp)          # <-- NEW: adds /sql and /sql/run

TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Federated Vehicle Lookup</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: linear-gradient(135deg, #1e3a5f 0%, #4a6fa5 100%);
            min-height: 100vh;
            margin: 0;
            display: flex;
            justify-content: center;
            padding: 60px 20px;
        }
        .card {
            background: #fff;
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            padding: 40px;
            max-width: 760px;
            width: 100%;
        }
        h2 {
            margin-top: 0;
            color: #1e3a5f;
            font-size: 1.6rem;
        }
        .architecture {
            color: #667085;
            font-size: 0.85rem;
            margin-top: -10px;
            margin-bottom: 20px;
        }
        form { display: flex; gap: 10px; margin: 24px 0; }
        input {
            flex: 1;
            padding: 12px 14px;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            font-size: 1rem;
        }
        input:focus {
            outline: none;
            border-color: #4a6fa5;
        }
        button {
            padding: 12px 24px;
            background: #1e3a5f;
            color: #fff;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
        }
        .error {
            background: #fdecea;
            border: 1px solid #f5c2c0;
            color: #a33;
            padding: 14px 18px;
            border-radius: 8px;
        }
        .reported-note {
            background: #eef4ff;
            border: 1px solid #c7d9f5;
            color: #1e3a5f;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.82rem;
            margin-bottom: 16px;
        }
        .reported-note.warn {
            background: #fff8e1;
            border-color: #f0e0a8;
            color: #8a6d1c;
        }
        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 15px;
            border-bottom: 2px solid #eef1f4;
            padding-bottom: 14px;
            margin-bottom: 18px;
        }
        .result-header h3 {
            margin: 0;
            color: #333;
            font-size: 1.15rem;
        }
        .badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 700;
        }
        .badge-stolen { background: #fdecea; color: #c0392b; }
        .badge-clear { background: #eafaf0; color: #1e8449; }
        .badge-warn { background: #fff8e1; color: #b8860b; }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px 24px;
            margin-bottom: 20px;
        }
        .field-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #8a94a3;
            margin-bottom: 3px;
        }
        .field-value {
            font-size: 0.98rem;
            color: #222;
            font-weight: 500;
        }
        .trust-wrap { margin-bottom: 20px; }
        .trust-bar-bg {
            background: #eef1f4;
            border-radius: 6px;
            height: 10px;
            overflow: hidden;
            margin-top: 6px;
        }
        .trust-bar-fill {
            height: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, #4a6fa5, #1e3a5f);
        }
        .flags { margin-top: 6px; }
        .flag-chip {
            display: inline-block;
            background: #fdecea;
            color: #a33;
            border: 1px solid #f5c2c0;
            padding: 5px 12px;
            border-radius: 16px;
            font-size: 0.82rem;
            margin: 4px 6px 0 0;
        }
        .source-box {
            margin-top: 22px;
            padding-top: 18px;
            border-top: 1px solid #eef1f4;
        }
        .source-row {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            font-size: 0.88rem;
        }
        .available { color: #1e8449; }
        .unavailable { color: #c0392b; }
        .search-form { display: block; margin: 24px 0; }
        .search-form .row { display: flex; gap: 10px; }
        .detail-box { margin-top: 12px; }
        .detail-box summary {
            cursor: pointer; color: #1e3a5f; font-weight: 600; font-size: 0.9rem;
        }
        .src-grid {
            display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
            margin-top: 12px;
        }
        .src-card {
            border: 1px solid #d9e2ef; border-radius: 10px; margin: 0;
            padding: 8px 12px 12px; background: #fafcff; min-width: 0;
        }
        .src-card legend {
            font-weight: 700; font-size: 0.82rem; color: #1e3a5f;
            padding: 0 6px;
        }
        .src-vehicles  { border-left: 4px solid #4a6fa5; }
        .src-insurance { border-left: 4px solid #2e9e6b; }
        .src-rto       { border-left: 4px solid #d9962b; }
        .src-theft     { border-left: 4px solid #c0392b; }
        .src-card label {
            display: block; font-size: 0.72rem; color: #667085;
            margin-top: 8px; text-transform: uppercase; letter-spacing: .04em;
        }
        .src-card input {
            width: 100%; margin-top: 3px; padding: 9px 10px; font-size: 0.9rem;
        }
        .clear-btn {
            background: #e8eef7; color: #1e3a5f; padding: 8px 14px;
            font-size: 0.82rem; margin-top: 12px;
        }
        .hint { color: #667085; font-size: 0.78rem; margin-top: 6px; }
        .cand-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 8px; }
        .cand-table th, .cand-table td {
            text-align: left; padding: 6px 8px; border-bottom: 1px solid #e3e8ef;
            vertical-align: top;
        }
        .chip { display: inline-block; padding: 2px 8px; border-radius: 12px;
                font-size: 0.74rem; margin: 1px 3px 1px 0; }
        .chip.match { background: #eafaf0; color: #1e8449; }
        .chip.partial { background: #fff8e1; color: #8a6d1c; }
        .chip.mismatch { background: #fdecea; color: #a33; }
        .identified { background: #eafaf0; border-color: #b7e4c7; color: #1e5631; }
        @media (max-width: 640px) {
            .src-grid { grid-template-columns: 1fr; }
            .card { padding: 24px 18px; }
            form { flex-direction: column; }
            button { width: 100%; }
            .grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="card">
        <h2>🚗 Federated Vehicle Lookup</h2>
        <div class="architecture">
            Mediation / Federated Virtual Integration — live query across
            independent vehicle, insurance, RTO and theft databases.
            Plate lookup supports local PaddleOCR and OCR-aware fuzzy suggestions.
        </div>

        <a href="/sql" style="display:block; text-align:center; margin-bottom:18px;
           padding:12px; background:#e8eef7; color:#1e3a5f; border-radius:8px;
           font-weight:600; text-decoration:none;">
            &#128269; Open Federated SQL Console &rarr;
        </a>

        <form method="get" action="/" class="search-form">
            <div class="row">
                <input name="plate" placeholder="Enter vehicle plate (full, partial or unclear, e.g. DL0?AB10?7)"
                       value="{{ plate or '' }}" autofocus>
                <button type="submit">Search</button>
            </div>
            <details class="detail-box" {% if details %}open{% endif %}>
                <summary>Plate unclear? Add details from any of the four databases</summary>
                <div class="src-grid">
                {% for sec in sections %}
                    <fieldset class="src-card src-{{ sec.key }}">
                        <legend>{{ sec.icon }} {{ sec.title }}</legend>
                        {% for field, label in sec.fields %}
                            <label for="f_{{ field }}">{{ label }}</label>
                            <input id="f_{{ field }}" name="{{ field }}"
                                   {% if field_options.get(field) %}list="dl_{{ field }}"{% endif %}
                                   placeholder="{{ 'Pick or type' if field_options.get(field) else 'Type to enter' }}"
                                   value="{{ (details or {}).get(field, '') }}" autocomplete="off">
                            {% if field_options.get(field) %}
                                <datalist id="dl_{{ field }}">
                                    {% for opt in field_options[field] %}<option value="{{ opt }}">{% endfor %}
                                </datalist>
                            {% endif %}
                        {% endfor %}
                    </fieldset>
                {% endfor %}
                </div>
                <div class="hint">Use "?" for plate characters you cannot read. Click a field to pick from the
                    values found in that database, or just type your own. Leave blank anything you don't know &mdash;
                    the plate and all filled fields are combined to find the one registration that agrees with them.</div>
                <button type="button" class="clear-btn"
                    onclick="document.querySelectorAll('.src-card input').forEach(function(i){i.value='';})">Clear details</button>
            </details>
        </form>

        <form method="post" action="/scan" enctype="multipart/form-data" class="search-form">
            <div class="row">
                <input type="file" name="plate_image"
                       accept="image/jpeg,image/png,image/heic" required>
                <button type="submit">Read plate with OCR</button>
            </div>
            <div class="hint">After the plate is read, add details from the four databases
                in the search box above to confirm the exact vehicle.</div>
        </form>

        {% if ocr_candidates %}
            <div class="reported-note">
                <strong>OCR readings — verify against the image:</strong>
                <ul>
                {% for item in ocr_candidates %}
                    <li>{{ item.plate }} — OCR confidence {{ '%.0f'|format(item.confidence * 100) }}%
                        <a href="/?plate={{ item.plate|urlencode }}">Search this reading</a>
                    </li>
                {% endfor %}
                </ul>
            </div>
        {% endif %}

        {% if identified_by %}
            <div class="reported-note identified">
                <strong>Vehicle identified: {{ plate_resolved }}</strong>
                — matched on {{ identified_by }}.
                Review the evidence below before acting on it.
            </div>
        {% endif %}

        {% if fuzzy_candidates %}
            <div class="reported-note warn">
                <strong>Candidate registrations (suggestions, not proof of identity):</strong>
                <table class="cand-table">
                    <tr><th>Plate</th><th>Score</th>{% if details %}<th>Details vs. registry</th>{% endif %}<th></th></tr>
                {% for item in fuzzy_candidates %}
                    <tr>
                        <td><strong>{{ item.plate }}</strong></td>
                        <td>{{ '%.1f'|format(item.score * 100) }}%</td>
                        {% if details %}
                        <td>
                            {% for field, v in (item.fields or {}).items() %}
                                <span class="chip {{ v.status }}">
                                    {{ field_labels.get(field, field) }}:
                                    {{ v.stored or '—' }}
                                    {% if v.status == 'match' %}✓{% elif v.status == 'mismatch' %}✗{% else %}~{% endif %}
                                </span>
                            {% endfor %}
                        </td>
                        {% endif %}
                        <td><a href="/?plate={{ item.plate|urlencode }}&confirmed=1">Open this vehicle</a></td>
                    </tr>
                {% endfor %}
                </table>
                {% if fuzzy_best and not fuzzy_auto %}
                    <p>{{ decision_reason or 'No candidate passed both the similarity and ambiguity checks.' }}
                       Please verify manually{% if details %} or add another detail{% endif %}.</p>
                {% endif %}
            </div>
        {% endif %}

        {% if error_message %}
            <div class="error">{{ error_message }}</div>
        {% endif %}

        {% if plate or details %}
            {% if match_score is not none %}
                <p class="reported-note">Selected registration similarity: {{ '%.1f'|format(match_score * 100) }}%.</p>
            {% endif %}
            {% if result and result.get('found') %}

                {% if reported_count %}
                    <div class="reported-note">
                        ⚑ {{ reported_count }} new flag(s) reported to the Ministry
                        of Transport for this lookup.
                    </div>
                {% elif reported_count is none %}
                    <div class="reported-note warn">
                        ⚠ Ministry of Transport reporting is currently unavailable
                        (mot_db unreachable). The lookup result below is unaffected.
                    </div>
                {% endif %}

                <div class="result-header">
                    <h3>{{ result.get('make') or '' }}
                        {{ result.get('model') or '' }}
                        — {{ result.get('plate') or plate }}</h3>

                    {% set decision = result.get('decision', '') %}
                    {% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %}
                        <span class="badge badge-stolen">⚠ {{ decision }}</span>
                    {% elif decision == 'OK — INSURED AND CLEAR' %}
                        <span class="badge badge-clear">CLEAR</span>
                    {% else %}
                        <span class="badge badge-warn">FLAGGED</span>
                    {% endif %}
                </div>

                <div class="grid">
                    <div><div class="field-label">Owner</div>
                        <div class="field-value">{{ result.get('owner') or '—' }}</div></div>
                    <div><div class="field-label">Color</div>
                        <div class="field-value">{{ result.get('color') or '—' }}</div></div>
                    <div><div class="field-label">Insurer</div>
                        <div class="field-value">{{ result.get('insurer') or '—' }}</div></div>
                    <div><div class="field-label">Registration Date</div>
                        <div class="field-value">{{ result.get('registration_date') or '—' }}</div></div>
                    <div><div class="field-label">Policy Start</div>
                        <div class="field-value">{{ result.get('policy_start_date') or '—' }}</div></div>
                    <div><div class="field-label">Policy End</div>
                        <div class="field-value">{{ result.get('policy_end_date') or '—' }}</div></div>
                    <div><div class="field-label">RTO Office</div>
                        <div class="field-value">{{ result.get('rto_office') or '—' }}</div></div>
                    <div><div class="field-label">Theft Status</div>
                        <div class="field-value">{{ result.get('theft_status') or '—' }}</div></div>
                </div>

                <div class="trust-wrap">
                    <div class="field-label">
                        Trust Score: {{ result.get('trust_score', 0) }}/100
                    </div>
                    <div class="trust-bar-bg">
                        <div class="trust-bar-fill"
                             style="width: {{ result.get('trust_score', 0) }}%;"></div>
                    </div>
                </div>

                <div>
                    <div class="field-label">Decision</div>
                    <div class="field-value">{{ result.get('decision') }}</div>
                </div>

                <div style="margin-top: 16px;">
                    <div class="field-label">Flags</div>
                    <div class="flags">
                        {% if result.get('flags') %}
                            {% for flag in result['flags'] %}
                                <span class="flag-chip">{{ flag }}</span>
                            {% endfor %}
                        {% else %}
                            <span>No flags raised</span>
                        {% endif %}
                    </div>
                </div>

                <div class="source-box">
                    <div class="field-label">Live Source Status</div>
                    {% for source, status in result.get('source_status', {}).items() %}
                        <div class="source-row">
                            <span>{{ source }}</span>
                            {% if status.get('available') %}
                                <span class="available">● AVAILABLE</span>
                            {% else %}
                                <span class="unavailable">● UNAVAILABLE</span>
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>

            {% else %}
                <div class="error">
                    {{ (result.get('message') if result else None) or 'No record found.' }}
                </div>

                {% if result and result.get('source_status') %}
                    <div class="source-box">
                        <div class="field-label">Live Source Status</div>
                        {% for source, status in result.get('source_status', {}).items() %}
                            <div class="source-row">
                                <span>{{ source }}</span>
                                {% if status.get('available') %}
                                    <span class="available">● AVAILABLE</span>
                                {% else %}
                                    <span class="unavailable">● UNAVAILABLE</span>
                                {% endif %}
                            </div>
                        {% endfor %}
                    </div>
                {% endif %}
            {% endif %}
        {% endif %}
    </div>
</body>
</html>
"""

ERROR_TEMPLATE = """
<!doctype html>
<html>
<head><title>Federated Vehicle Lookup — Error</title></head>
<body style="font-family: sans-serif; padding: 60px; text-align: center; color: #333;">
    <h2>Something went wrong on this lookup</h2>
    <p>Please try the search again. If this keeps happening, one of the
    source databases may be down.</p>
    <p><a href="/">Back to search</a></p>
</body>
</html>
"""


def _rank_plate_candidates(query, limit=FUZZY_TOP_K):
    """Compare the query with live plate identifiers discovered from sources."""
    query_key = normalize_plate(query) or ""
    if not query_key:
        return []

    scores = {}
    for raw_plate in list_candidate_plates():
        canonical = normalize_plate(raw_plate)
        if not canonical:
            continue
        score = plate_similarity(query_key, canonical)
        if canonical not in scores or score > scores[canonical]:
            scores[canonical] = score

    return [
        {"plate": plate, "score": score}
        for plate, score in sorted(
            scores.items(), key=lambda item: (-item[1], item[0])
        )[:limit]
    ]


def _fuzzy_decision(candidates):
    """Auto-select only a strong, unambiguous candidate; otherwise review."""
    if not candidates:
        return None, False
    best_score = candidates[0]["score"]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    safe = (
        best_score >= FUZZY_MIN_SCORE
        and best_score - second_score >= FUZZY_MIN_MARGIN
    )
    return candidates[0]["plate"], safe


_OPTIONS_TTL = 300
_options_cache = {"at": 0.0, "data": {}}
STATIC_OPTIONS = {
    "policy_status": ["Active", "Expired", "No policy"],
    "renewal_status": ["Valid", "Lapsed", "No RTO record"],
    "theft_status": ["Stolen", "Recovered", "Shredded", "No theft record"],
}
OPTION_FIELDS = ("make", "model", "color", "insurer_name", "rto_office",
                 "registration_year", "theft_year")


def _field_options():
    """Dropdown values per field, taken from the live sources (cached 5 min).

    Only distinct *values* are cached for the dropdowns - never vehicle rows.
    """
    now = time.time()
    if _options_cache["data"] and now - _options_cache["at"] < _OPTIONS_TTL:
        return _options_cache["data"]
    options = {k: list(v) for k, v in STATIC_OPTIONS.items()}
    try:
        profiles = list_vehicle_profiles()
    except Exception:
        profiles = []
    for field in OPTION_FIELDS:
        values = {
            str(p[field]).strip() for p in profiles
            if p.get(field) and not str(p[field]).startswith("No ")
        }
        if values:
            options[field] = sorted(values, key=str.casefold)
    if profiles:                       # don't cache an outage
        _options_cache.update(at=now, data=options)
    return options


@app.context_processor
def _inject_form_data():
    return {"sections": SECTIONS, "field_options": _field_options(),
            "field_labels": DETAIL_LABELS}


def _read_details(source):
    """Optional operator-supplied details (make/model/color/owner/engine/chassis)."""
    return {
        field: (source.get(field) or "").strip()[:60]
        for field in DETAIL_FIELDS
        if (source.get(field) or "").strip()
    }


def _rank_unified(query, details, limit=FUZZY_TOP_K):
    """Rank registrations by plate alone, or plate + details when provided.

    Returns (candidates, best_plate, auto_ok, reason, used_details).
    """
    if details:
        rows = list_vehicle_profiles()
        if rows:
            ranked = rank_with_details(
                normalize_plate(query) or "", details, rows, limit
            )
            best, auto, reason = decide(ranked, used_details=True)
            return ranked, best, auto, reason, True
        # Registration DB unreachable: fall back to plate-only ranking.
    candidates = _rank_plate_candidates(query, limit)
    best, auto = _fuzzy_decision(candidates)
    return candidates, best, auto, None, False


def _describe_evidence(candidate):
    fields = [f for f, v in (candidate.get("fields") or {}).items()
              if v["status"] == "match"]
    return "plate + " + ", ".join(
        DETAIL_LABELS.get(f, f) for f in fields
    ) if fields else "plate"


@app.route("/", methods=["GET"])
def home():
    plate = request.args.get("plate", "").strip()
    confirmed = request.args.get("confirmed") == "1"
    result = None
    reported_count = 0
    ocr_candidates = []
    fuzzy_candidates = []
    fuzzy_best = None
    fuzzy_auto = False
    match_score = None
    error_message = None
    resolved_plate = plate
    details = _read_details(request.args)
    decision_reason = None
    identified_by = None

    try:
        if plate or details:
            fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
                _rank_unified(plate, details)
            )

            top = fuzzy_candidates[0] if fuzzy_candidates else None
            exact = bool(
                top
                and plate
                and normalize_plate(top["plate"]) == normalize_plate(plate)
                and top.get("plate_score", top["score"]) >= 0.999
                and not any(v["status"] == "mismatch"
                            for v in (top.get("fields") or {}).values())
            )

            # Never silently replace a typed plate with a fuzzy guess.
            # Exact plate or explicit user selection may run the full federated lookup.
            if exact:
                resolved_plate = fuzzy_candidates[0]["plate"]
                match_score = 1.0
                result = query_vehicle(resolved_plate)
            elif confirmed:
                selected = normalize_plate(plate)
                result = query_vehicle(selected)
                resolved_plate = selected
                match_score = 1.0
            elif fuzzy_auto:
                resolved_plate = fuzzy_best
                match_score = fuzzy_candidates[0]["score"]
                result = query_vehicle(resolved_plate)
                if used:
                    identified_by = _describe_evidence(fuzzy_candidates[0])
            else:
                # Keep the raw query visible and ask the user to select a candidate.
                result = {
                    "plate": plate,
                    "found": False,
                    "message": (
                        "No exact registration was confirmed. Review the "
                        "candidates above and select the correct plate."
                    ),
                }

            # Reporting is only triggered for an exact match or explicit selection.
            # An automatically suggested fuzzy candidate is displayed but not written back.
            if result and result.get("found") and (exact or confirmed):
                reported_count = report_flags(result, reported_by="live-lookup-ui")

    except Exception as exc:
        print(f"[app] lookup failed for plate={plate!r}: {exc}")
        error_message = (
            "Could not complete the lookup. Check source availability and try again."
        )

    return render_template_string(
        TEMPLATE,
        plate=plate,
        result=result,
        reported_count=reported_count,
        ocr_candidates=ocr_candidates,
        fuzzy_candidates=fuzzy_candidates,
        fuzzy_best=fuzzy_best,
        fuzzy_auto=fuzzy_auto,
        match_score=match_score,
        error_message=error_message,
        details=details,
        decision_reason=decision_reason,
        identified_by=identified_by,
        plate_resolved=resolved_plate,
    )


@app.route("/scan", methods=["POST"])
def scan_plate_image():
    upload = request.files.get("plate_image")
    if upload is None or not upload.filename:
        return render_template_string(
            TEMPLATE, plate="", result=None, reported_count=0,
            ocr_candidates=[], fuzzy_candidates=[], fuzzy_best=None,
            fuzzy_auto=False, match_score=None,
            error_message="Choose an image of a registration plate first.",
        ), 400

    try:
        # recognize_plate_image validates file signature/size and returns ranked OCR readings.
        ocr_candidates = recognize_plate_image(upload)
        if not ocr_candidates:
            raise PlateOCRInputError(
                "No plausible registration plate text was found. Try a clearer image."
            )

        # Use the best OCR reading as the search query; do not report/write flags here.
        query = ocr_candidates[0]["plate"]
        details = _read_details(request.form)
        fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
            _rank_unified(query, details)
        )

        # Only run Vehicle 360 automatically when the best fuzzy match is strong
        # and sufficiently separated from the runner-up. Otherwise show suggestions.
        result = None
        match_score = None
        identified_by = None
        if fuzzy_auto:
            result = query_vehicle(fuzzy_best)
            match_score = fuzzy_candidates[0]["score"]
            if used:
                identified_by = _describe_evidence(fuzzy_candidates[0])
        else:
            result = {
                "plate": query,
                "found": False,
                "message": (
                    "OCR completed, but no unique high-confidence registration "
                    "match was found. Verify the image and select a candidate."
                ),
            }

        return render_template_string(
            TEMPLATE,
            plate=query,
            result=result,
            reported_count=0,
            ocr_candidates=ocr_candidates,
            fuzzy_candidates=fuzzy_candidates,
            fuzzy_best=fuzzy_best,
            fuzzy_auto=fuzzy_auto,
            match_score=match_score,
            error_message=None,
            details=details,
            decision_reason=decision_reason,
            identified_by=identified_by,
            plate_resolved=fuzzy_best,
        )

    except PlateOCRInputError as exc:
        message = str(exc)
    except PlateOCREngineError as exc:
        print(f"[app] OCR engine failed: {exc}")
        message = "OCR could not run. Confirm PaddleOCR is installed on the Coordinator."
    except Exception as exc:
        print(f"[app] OCR/fuzzy lookup failed: {exc}")
        message = "OCR or candidate matching failed. Check the Coordinator logs."

    return render_template_string(
        TEMPLATE,
        plate="",
        result=None,
        reported_count=0,
        ocr_candidates=[],
        fuzzy_candidates=[],
        fuzzy_best=None,
        fuzzy_auto=False,
        match_score=None,
        error_message=message,
    ), 400


@app.errorhandler(413)
def upload_too_large(_error):
    return render_template_string(
        TEMPLATE, plate="", result=None, reported_count=0,
        ocr_candidates=[], fuzzy_candidates=[], fuzzy_best=None,
        fuzzy_auto=False, match_score=None,
        error_message="Image upload is too large. Maximum allowed size is 8 MB.",
    ), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)