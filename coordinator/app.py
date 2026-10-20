# # from flask import Flask, request, render_template_string

# # from mediator import query_vehicle

# # app = Flask(__name__)

# # TEMPLATE = """
# # <!doctype html>
# # <html>
# # <head>
# #     <title>Federated Vehicle Lookup</title>
# #     <meta name="viewport" content="width=device-width, initial-scale=1">
# #     <style>
# #         * { box-sizing: border-box; }
# #         body {
# #             font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
# #             background: linear-gradient(135deg, #1e3a5f 0%, #4a6fa5 100%);
# #             min-height: 100vh;
# #             margin: 0;
# #             display: flex;
# #             justify-content: center;
# #             padding: 60px 20px;
# #         }
# #         .card {
# #             background: #fff;
# #             border-radius: 14px;
# #             box-shadow: 0 10px 30px rgba(0,0,0,0.15);
# #             padding: 40px;
# #             max-width: 760px;
# #             width: 100%;
# #         }
# #         h2 {
# #             margin-top: 0;
# #             color: #1e3a5f;
# #             font-size: 1.6rem;
# #         }
# #         .architecture {
# #             color: #667085;
# #             font-size: 0.85rem;
# #             margin-top: -10px;
# #             margin-bottom: 20px;
# #         }
# #         form { display: flex; gap: 10px; margin: 24px 0; }
# #         input {
# #             flex: 1;
# #             padding: 12px 14px;
# #             border: 1px solid #d0d7de;
# #             border-radius: 8px;
# #             font-size: 1rem;
# #         }
# #         input:focus {
# #             outline: none;
# #             border-color: #4a6fa5;
# #         }
# #         button {
# #             padding: 12px 24px;
# #             background: #1e3a5f;
# #             color: #fff;
# #             border: none;
# #             border-radius: 8px;
# #             font-size: 1rem;
# #             font-weight: 600;
# #             cursor: pointer;
# #         }
# #         .error {
# #             background: #fdecea;
# #             border: 1px solid #f5c2c0;
# #             color: #a33;
# #             padding: 14px 18px;
# #             border-radius: 8px;
# #         }
# #         .result-header {
# #             display: flex;
# #             justify-content: space-between;
# #             align-items: center;
# #             gap: 15px;
# #             border-bottom: 2px solid #eef1f4;
# #             padding-bottom: 14px;
# #             margin-bottom: 18px;
# #         }
# #         .result-header h3 {
# #             margin: 0;
# #             color: #333;
# #             font-size: 1.15rem;
# #         }
# #         .badge {
# #             display: inline-block;
# #             padding: 6px 14px;
# #             border-radius: 20px;
# #             font-size: 0.8rem;
# #             font-weight: 700;
# #         }
# #         .badge-stolen { background: #fdecea; color: #c0392b; }
# #         .badge-clear { background: #eafaf0; color: #1e8449; }
# #         .badge-warn { background: #fff8e1; color: #b8860b; }
# #         .grid {
# #             display: grid;
# #             grid-template-columns: 1fr 1fr;
# #             gap: 14px 24px;
# #             margin-bottom: 20px;
# #         }
# #         .field-label {
# #             font-size: 0.75rem;
# #             text-transform: uppercase;
# #             letter-spacing: 0.05em;
# #             color: #8a94a3;
# #             margin-bottom: 3px;
# #         }
# #         .field-value {
# #             font-size: 0.98rem;
# #             color: #222;
# #             font-weight: 500;
# #         }
# #         .trust-wrap { margin-bottom: 20px; }
# #         .trust-bar-bg {
# #             background: #eef1f4;
# #             border-radius: 6px;
# #             height: 10px;
# #             overflow: hidden;
# #             margin-top: 6px;
# #         }
# #         .trust-bar-fill {
# #             height: 100%;
# #             border-radius: 6px;
# #             background: linear-gradient(90deg, #4a6fa5, #1e3a5f);
# #         }
# #         .flags { margin-top: 6px; }
# #         .flag-chip {
# #             display: inline-block;
# #             background: #fdecea;
# #             color: #a33;
# #             border: 1px solid #f5c2c0;
# #             padding: 5px 12px;
# #             border-radius: 16px;
# #             font-size: 0.82rem;
# #             margin: 4px 6px 0 0;
# #         }
# #         .source-box {
# #             margin-top: 22px;
# #             padding-top: 18px;
# #             border-top: 1px solid #eef1f4;
# #         }
# #         .source-row {
# #             display: flex;
# #             justify-content: space-between;
# #             padding: 5px 0;
# #             font-size: 0.88rem;
# #         }
# #         .available { color: #1e8449; }
# #         .unavailable { color: #c0392b; }
# #         @media (max-width: 640px) {
# #             .card { padding: 24px 18px; }
# #             form { flex-direction: column; }
# #             button { width: 100%; }
# #             .grid { grid-template-columns: 1fr; }
# #         }
# #     </style>
# # </head>
# # <body>
# #     <div class="card">
# #         <h2>🚗 Federated Vehicle Lookup</h2>
# #         <div class="architecture">
# #             Mediation / Federated Virtual Integration — live query across
# #             independent vehicle, insurance, RTO and theft databases.
# #         </div>

# #         <form method="get">
# #             <input name="plate" placeholder="Enter vehicle plate"
# #                    value="{{ plate or '' }}" autofocus>
# #             <button type="submit">Search</button>
# #         </form>

# #         {% if plate %}
# #             {% if result and result.get('found') %}
# #                 <div class="result-header">
# #                     <h3>{{ result.get('make') or '' }}
# #                         {{ result.get('model') or '' }}
# #                         — {{ result.get('plate') or plate }}</h3>

# #                     {% set decision = result.get('decision', '') %}
# #                     {% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %}
# #                         <span class="badge badge-stolen">⚠ {{ decision }}</span>
# #                     {% elif decision == 'OK — INSURED AND CLEAR' %}
# #                         <span class="badge badge-clear">CLEAR</span>
# #                     {% else %}
# #                         <span class="badge badge-warn">FLAGGED</span>
# #                     {% endif %}
# #                 </div>

# #                 <div class="grid">
# #                     <div><div class="field-label">Owner</div>
# #                         <div class="field-value">{{ result.get('owner') or '—' }}</div></div>
# #                     <div><div class="field-label">Color</div>
# #                         <div class="field-value">{{ result.get('color') or '—' }}</div></div>
# #                     <div><div class="field-label">Insurer</div>
# #                         <div class="field-value">{{ result.get('insurer') or '—' }}</div></div>
# #                     <div><div class="field-label">Registration Date</div>
# #                         <div class="field-value">{{ result.get('registration_date') or '—' }}</div></div>
# #                     <div><div class="field-label">Policy Start</div>
# #                         <div class="field-value">{{ result.get('policy_start_date') or '—' }}</div></div>
# #                     <div><div class="field-label">Policy End</div>
# #                         <div class="field-value">{{ result.get('policy_end_date') or '—' }}</div></div>
# #                     <div><div class="field-label">RTO Office</div>
# #                         <div class="field-value">{{ result.get('rto_office') or '—' }}</div></div>
# #                     <div><div class="field-label">Theft Status</div>
# #                         <div class="field-value">{{ result.get('theft_status') or '—' }}</div></div>
# #                 </div>

# #                 <div class="trust-wrap">
# #                     <div class="field-label">
# #                         Trust Score: {{ result.get('trust_score', 0) }}/100
# #                     </div>
# #                     <div class="trust-bar-bg">
# #                         <div class="trust-bar-fill"
# #                              style="width: {{ result.get('trust_score', 0) }}%;"></div>
# #                     </div>
# #                 </div>

# #                 <div>
# #                     <div class="field-label">Decision</div>
# #                     <div class="field-value">{{ result.get('decision') }}</div>
# #                 </div>

# #                 <div style="margin-top: 16px;">
# #                     <div class="field-label">Flags</div>
# #                     <div class="flags">
# #                         {% if result.get('flags') %}
# #                             {% for flag in result['flags'] %}
# #                                 <span class="flag-chip">{{ flag }}</span>
# #                             {% endfor %}
# #                         {% else %}
# #                             <span>No flags raised</span>
# #                         {% endif %}
# #                     </div>
# #                 </div>

# #                 <div class="source-box">
# #                     <div class="field-label">Live Source Status</div>
# #                     {% for source, status in result.get('source_status', {}).items() %}
# #                         <div class="source-row">
# #                             <span>{{ source }}</span>
# #                             {% if status.get('available') %}
# #                                 <span class="available">● AVAILABLE</span>
# #                             {% else %}
# #                                 <span class="unavailable">● UNAVAILABLE</span>
# #                             {% endif %}
# #                         </div>
# #                     {% endfor %}
# #                 </div>

# #             {% else %}
# #                 <div class="error">
# #                     {{ result.get('message', 'No record found.') }}
# #                 </div>
# #             {% endif %}
# #         {% endif %}
# #     </div>
# # </body>
# # </html>
# # """


# # @app.route("/")
# # def home():
# #     plate = request.args.get("plate", "").strip()
# #     result = query_vehicle(plate) if plate else None

# #     return render_template_string(
# #         TEMPLATE,
# #         plate=plate,
# #         result=result,
# #     )


# # if __name__ == "__main__":
# #     app.run(host="0.0.0.0", port=5001, debug=False)


# from flask import Flask, request, render_template_string

# from mediator import query_vehicle
# from reporting import report_flags

# app = Flask(__name__)

# TEMPLATE = """
# <!doctype html>
# <html>
# <head>
#     <title>Federated Vehicle Lookup</title>
#     <meta name="viewport" content="width=device-width, initial-scale=1">
#     <style>
#         * { box-sizing: border-box; }
#         body {
#             font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
#             background: linear-gradient(135deg, #1e3a5f 0%, #4a6fa5 100%);
#             min-height: 100vh;
#             margin: 0;
#             display: flex;
#             justify-content: center;
#             padding: 60px 20px;
#         }
#         .card {
#             background: #fff;
#             border-radius: 14px;
#             box-shadow: 0 10px 30px rgba(0,0,0,0.15);
#             padding: 40px;
#             max-width: 760px;
#             width: 100%;
#         }
#         h2 {
#             margin-top: 0;
#             color: #1e3a5f;
#             font-size: 1.6rem;
#         }
#         .architecture {
#             color: #667085;
#             font-size: 0.85rem;
#             margin-top: -10px;
#             margin-bottom: 20px;
#         }
#         form { display: flex; gap: 10px; margin: 24px 0; }
#         input {
#             flex: 1;
#             padding: 12px 14px;
#             border: 1px solid #d0d7de;
#             border-radius: 8px;
#             font-size: 1rem;
#         }
#         input:focus {
#             outline: none;
#             border-color: #4a6fa5;
#         }
#         button {
#             padding: 12px 24px;
#             background: #1e3a5f;
#             color: #fff;
#             border: none;
#             border-radius: 8px;
#             font-size: 1rem;
#             font-weight: 600;
#             cursor: pointer;
#         }
#         .error {
#             background: #fdecea;
#             border: 1px solid #f5c2c0;
#             color: #a33;
#             padding: 14px 18px;
#             border-radius: 8px;
#         }
#         .reported-note {
#             background: #eef4ff;
#             border: 1px solid #c7d9f5;
#             color: #1e3a5f;
#             padding: 10px 14px;
#             border-radius: 8px;
#             font-size: 0.82rem;
#             margin-bottom: 16px;
#         }
#         .reported-note.warn {
#             background: #fff8e1;
#             border-color: #f0e0a8;
#             color: #8a6d1c;
#         }
#         .result-header {
#             display: flex;
#             justify-content: space-between;
#             align-items: center;
#             gap: 15px;
#             border-bottom: 2px solid #eef1f4;
#             padding-bottom: 14px;
#             margin-bottom: 18px;
#         }
#         .result-header h3 {
#             margin: 0;
#             color: #333;
#             font-size: 1.15rem;
#         }
#         .badge {
#             display: inline-block;
#             padding: 6px 14px;
#             border-radius: 20px;
#             font-size: 0.8rem;
#             font-weight: 700;
#         }
#         .badge-stolen { background: #fdecea; color: #c0392b; }
#         .badge-clear { background: #eafaf0; color: #1e8449; }
#         .badge-warn { background: #fff8e1; color: #b8860b; }
#         .grid {
#             display: grid;
#             grid-template-columns: 1fr 1fr;
#             gap: 14px 24px;
#             margin-bottom: 20px;
#         }
#         .field-label {
#             font-size: 0.75rem;
#             text-transform: uppercase;
#             letter-spacing: 0.05em;
#             color: #8a94a3;
#             margin-bottom: 3px;
#         }
#         .field-value {
#             font-size: 0.98rem;
#             color: #222;
#             font-weight: 500;
#         }
#         .trust-wrap { margin-bottom: 20px; }
#         .trust-bar-bg {
#             background: #eef1f4;
#             border-radius: 6px;
#             height: 10px;
#             overflow: hidden;
#             margin-top: 6px;
#         }
#         .trust-bar-fill {
#             height: 100%;
#             border-radius: 6px;
#             background: linear-gradient(90deg, #4a6fa5, #1e3a5f);
#         }
#         .flags { margin-top: 6px; }
#         .flag-chip {
#             display: inline-block;
#             background: #fdecea;
#             color: #a33;
#             border: 1px solid #f5c2c0;
#             padding: 5px 12px;
#             border-radius: 16px;
#             font-size: 0.82rem;
#             margin: 4px 6px 0 0;
#         }
#         .source-box {
#             margin-top: 22px;
#             padding-top: 18px;
#             border-top: 1px solid #eef1f4;
#         }
#         .source-row {
#             display: flex;
#             justify-content: space-between;
#             padding: 5px 0;
#             font-size: 0.88rem;
#         }
#         .available { color: #1e8449; }
#         .unavailable { color: #c0392b; }
#         @media (max-width: 640px) {
#             .card { padding: 24px 18px; }
#             form { flex-direction: column; }
#             button { width: 100%; }
#             .grid { grid-template-columns: 1fr; }
#         }
#     </style>
# </head>
# <body>
#     <div class="card">
#         <h2>🚗 Federated Vehicle Lookup</h2>
#         <div class="architecture">
#             Mediation / Federated Virtual Integration — live query across
#             independent vehicle, insurance, RTO and theft databases.
#         </div>

#         <form method="get">
#             <input name="plate" placeholder="Enter vehicle plate"
#                    value="{{ plate or '' }}" autofocus>
#             <button type="submit">Search</button>
#         </form>

#         {% if plate %}
#             {% if result and result.get('found') %}

#                 {% if reported_count %}
#                     <div class="reported-note">
#                         ⚑ {{ reported_count }} new flag(s) reported to the Ministry
#                         of Transport for this lookup.
#                     </div>
#                 {% elif reported_count is none %}
#                     <div class="reported-note warn">
#                         ⚠ Ministry of Transport reporting is currently unavailable
#                         (mot_db unreachable). The lookup result below is unaffected.
#                     </div>
#                 {% endif %}

#                 <div class="result-header">
#                     <h3>{{ result.get('make') or '' }}
#                         {{ result.get('model') or '' }}
#                         — {{ result.get('plate') or plate }}</h3>

#                     {% set decision = result.get('decision', '') %}
#                     {% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %}
#                         <span class="badge badge-stolen">⚠ {{ decision }}</span>
#                     {% elif decision == 'OK — INSURED AND CLEAR' %}
#                         <span class="badge badge-clear">CLEAR</span>
#                     {% else %}
#                         <span class="badge badge-warn">FLAGGED</span>
#                     {% endif %}
#                 </div>

#                 <div class="grid">
#                     <div><div class="field-label">Owner</div>
#                         <div class="field-value">{{ result.get('owner') or '—' }}</div></div>
#                     <div><div class="field-label">Color</div>
#                         <div class="field-value">{{ result.get('color') or '—' }}</div></div>
#                     <div><div class="field-label">Insurer</div>
#                         <div class="field-value">{{ result.get('insurer') or '—' }}</div></div>
#                     <div><div class="field-label">Registration Date</div>
#                         <div class="field-value">{{ result.get('registration_date') or '—' }}</div></div>
#                     <div><div class="field-label">Policy Start</div>
#                         <div class="field-value">{{ result.get('policy_start_date') or '—' }}</div></div>
#                     <div><div class="field-label">Policy End</div>
#                         <div class="field-value">{{ result.get('policy_end_date') or '—' }}</div></div>
#                     <div><div class="field-label">RTO Office</div>
#                         <div class="field-value">{{ result.get('rto_office') or '—' }}</div></div>
#                     <div><div class="field-label">Theft Status</div>
#                         <div class="field-value">{{ result.get('theft_status') or '—' }}</div></div>
#                 </div>

#                 <div class="trust-wrap">
#                     <div class="field-label">
#                         Trust Score: {{ result.get('trust_score', 0) }}/100
#                     </div>
#                     <div class="trust-bar-bg">
#                         <div class="trust-bar-fill"
#                              style="width: {{ result.get('trust_score', 0) }}%;"></div>
#                     </div>
#                 </div>

#                 <div>
#                     <div class="field-label">Decision</div>
#                     <div class="field-value">{{ result.get('decision') }}</div>
#                 </div>

#                 <div style="margin-top: 16px;">
#                     <div class="field-label">Flags</div>
#                     <div class="flags">
#                         {% if result.get('flags') %}
#                             {% for flag in result['flags'] %}
#                                 <span class="flag-chip">{{ flag }}</span>
#                             {% endfor %}
#                         {% else %}
#                             <span>No flags raised</span>
#                         {% endif %}
#                     </div>
#                 </div>

#                 <div class="source-box">
#                     <div class="field-label">Live Source Status</div>
#                     {% for source, status in result.get('source_status', {}).items() %}
#                         <div class="source-row">
#                             <span>{{ source }}</span>
#                             {% if status.get('available') %}
#                                 <span class="available">● AVAILABLE</span>
#                             {% else %}
#                                 <span class="unavailable">● UNAVAILABLE</span>
#                             {% endif %}
#                         </div>
#                     {% endfor %}
#                 </div>

#             {% else %}
#                 <div class="error">
#                     {{ result.get('message', 'No record found.') }}
#                 </div>
#             {% endif %}
#         {% endif %}
#     </div>
# </body>
# </html>
# """

# ERROR_TEMPLATE = """
# <!doctype html>
# <html>
# <head><title>Federated Vehicle Lookup — Error</title></head>
# <body style="font-family: sans-serif; padding: 60px; text-align: center; color: #333;">
#     <h2>Something went wrong on this lookup</h2>
#     <p>Please try the search again. If this keeps happening, one of the
#     source databases may be down.</p>
#     <p><a href="/">Back to search</a></p>
# </body>
# </html>
# """


# @app.route("/")
# def home():
#     plate = request.args.get("plate", "").strip()
#     result = None
#     reported_count = 0

#     # Top-level safety net. query_vehicle() and report_flags() are both
#     # already internally fault-tolerant (per-source try/except in
#     # mediator.py, whole-function try/except in reporting.py), so this
#     # should never actually fire — it exists as defense-in-depth so an
#     # unexpected error anywhere in the chain shows a friendly page
#     # instead of Flask's default 500 error screen.
#     try:
#         if plate:
#             result = query_vehicle(plate)

#             if result and result.get("found"):
#                 # None means "mot_db unreachable", not "0 flags" — the
#                 # template distinguishes the two so the UI never implies
#                 # a clean vehicle when reporting just couldn't happen.
#                 reported_count = report_flags(result, reported_by="live-lookup-ui")

#     except Exception as exc:
#         print(f"[app] unexpected error on plate={plate!r}: {exc}")
#         return render_template_string(ERROR_TEMPLATE), 500

#     return render_template_string(
#         TEMPLATE,
#         plate=plate,
#         result=result,
#         reported_count=reported_count,
#     )


# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)

from flask import Flask, request, render_template_string

from mediator import query_vehicle
from reporting import report_flags

app = Flask(__name__)

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
        </div>

        <form method="get">
            <input name="plate" placeholder="Enter vehicle plate"
                   value="{{ plate or '' }}" autofocus>
            <button type="submit">Search</button>
        </form>

        {% if plate %}
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


@app.route("/")
def home():
    plate = request.args.get("plate", "").strip()
    result = None
    reported_count = 0

    # Top-level safety net. query_vehicle() and report_flags() are both
    # already internally fault-tolerant (per-source try/except in
    # mediator.py, whole-function try/except in reporting.py), so this
    # should never actually fire — it exists as defense-in-depth so an
    # unexpected error anywhere in the chain shows a friendly page
    # instead of Flask's default 500 error screen.
    try:
        if plate:
            result = query_vehicle(plate)

            if result and result.get("found"):
                # None means "mot_db unreachable", not "0 flags" — the
                # template distinguishes the two so the UI never implies
                # a clean vehicle when reporting just couldn't happen.
                reported_count = report_flags(result, reported_by="live-lookup-ui")

    except Exception as exc:
        print(f"[app] unexpected error on plate={plate!r}: {exc}")
        return render_template_string(ERROR_TEMPLATE), 500

    return render_template_string(
        TEMPLATE,
        plate=plate,
        result=result,
        reported_count=reported_count,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)