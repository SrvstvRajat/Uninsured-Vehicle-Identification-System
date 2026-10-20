from flask import Flask, request, render_template_string, redirect, url_for
from werkzeug.utils import secure_filename

from mediator import query_vehicle, list_candidate_plates, normalize_plate
from fuzzy_match import plate_similarity
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
        @media (max-width: 640px) {
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

        <form method="get">
            <input name="plate" placeholder="Enter vehicle plate"
                   value="{{ plate or '' }}" autofocus>
            <button type="submit">Search</button>
        </form>

        <form method="post" action="/scan" enctype="multipart/form-data">
            <input type="file" name="plate_image"
                   accept="image/jpeg,image/png,image/heic" required>
            <button type="submit">Read plate with OCR</button>
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

        {% if fuzzy_candidates %}
            <div class="reported-note warn">
                <strong>Fuzzy plate candidates (suggestions, not proof of identity):</strong>
                <ul>
                {% for item in fuzzy_candidates %}
                    <li>
                        <strong>{{ item.plate }}</strong> — similarity {{ '%.1f'|format(item.score * 100) }}%
                        <a href="/?plate={{ item.plate|urlencode }}&confirmed=1">Open this vehicle</a>
                    </li>
                {% endfor %}
                </ul>
                {% if fuzzy_best and not fuzzy_auto %}
                    <p>No candidate passed both the similarity and ambiguity checks. Please verify the plate manually.</p>
                {% endif %}
            </div>
        {% endif %}

        {% if error_message %}
            <div class="error">{{ error_message }}</div>
        {% endif %}

        {% if plate %}
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

    try:
        if plate:
            fuzzy_candidates = _rank_plate_candidates(plate)
            fuzzy_best, fuzzy_auto = _fuzzy_decision(fuzzy_candidates)

            exact = bool(
                fuzzy_candidates
                and normalize_plate(fuzzy_candidates[0]["plate"]) == normalize_plate(plate)
                and fuzzy_candidates[0]["score"] >= 0.999
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
            else:
                # Keep the raw query visible and ask the user to select a candidate.
                result = {
                    "plate": plate,
                    "found": False,
                    "message": (
                        "No exact registration was confirmed. Review the fuzzy "
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
        fuzzy_candidates = _rank_plate_candidates(query)
        fuzzy_best, fuzzy_auto = _fuzzy_decision(fuzzy_candidates)

        # Only run Vehicle 360 automatically when the best fuzzy match is strong
        # and sufficiently separated from the runner-up. Otherwise show suggestions.
        result = None
        match_score = None
        if fuzzy_auto:
            result = query_vehicle(fuzzy_best)
            match_score = fuzzy_candidates[0]["score"]
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