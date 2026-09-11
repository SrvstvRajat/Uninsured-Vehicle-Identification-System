from flask import Flask, request, render_template_string

from query_tool import get_vehicle_status, load_master

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>Vehicle Insurance Lookup</title>
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
            max-width: 680px;
            width: 100%;
        }
        h2 {
            margin-top: 0;
            color: #1e3a5f;
            font-size: 1.6rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        h2::before { content: "🚗"; font-size: 1.4rem; }
        form { display: flex; gap: 10px; margin: 24px 0; }
        input {
            flex: 1;
            padding: 12px 14px;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #4a6fa5;
            box-shadow: 0 0 0 3px rgba(74,111,165,0.15);
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
            transition: background 0.2s;
        }
        button:hover { background: #16304e; }

        .error {
            background: #fdecea;
            border: 1px solid #f5c2c0;
            color: #a33;
            padding: 14px 18px;
            border-radius: 8px;
            font-size: 0.95rem;
        }

        .result-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #eef1f4;
            padding-bottom: 14px;
            margin-bottom: 18px;
        }
        .result-header h3 { margin: 0; color: #333; font-size: 1.15rem; }

        .badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.03em;
        }
        .badge-stolen { background: #fdecea; color: #c0392b; }
        .badge-clear  { background: #eafaf0; color: #1e8449; }
        .badge-warn   { background: #fff8e1; color: #b8860b; }

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
        .field-value { font-size: 0.98rem; color: #222; font-weight: 500; }

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
        .no-flags { color: #8a94a3; font-size: 0.9rem; }

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
        <h2>Vehicle Insurance Lookup</h2>
        <form method="get">
            <input name="plate" placeholder="Enter vehicle plate"
                   value="{{ plate or '' }}" autofocus>
            <button type="submit">Search</button>
        </form>

        {% if plate %}
            {% if result and result.get('found') %}
                <div class="result-header">
                    <h3>{{ result.get('make', '') }} {{ result.get('model', '') }} — {{ result.get('plate', '') }}</h3>
                    {% set decision = result.get('decision', '') %}
                    {% if decision == 'STOLEN' %}
                        <span class="badge badge-stolen">⚠ STOLEN</span>
                    {% elif result.get('flags') %}
                        <span class="badge badge-warn">FLAGGED</span>
                    {% else %}
                        <span class="badge badge-clear">CLEAR</span>
                    {% endif %}
                </div>

                <div class="grid">
                    <div><div class="field-label">Owner</div><div class="field-value">{{ result.get('owner', '—') }}</div></div>
                    <div><div class="field-label">Color</div><div class="field-value">{{ result.get('color', '—') }}</div></div>
                    <div><div class="field-label">Insurer</div><div class="field-value">{{ result.get('insurer', '—') }}</div></div>
                    <div><div class="field-label">Registration Date</div><div class="field-value">{{ result.get('registration_date', '—') }}</div></div>
                    <div><div class="field-label">Policy Start</div><div class="field-value">{{ result.get('policy_start_date', '—') }}</div></div>
                    <div><div class="field-label">Policy End</div><div class="field-value">{{ result.get('policy_end_date', '—') }}</div></div>
                </div>

                <div class="trust-wrap">
                    <div class="field-label">Trust Score: {{ result.get('trust_score', 0) }}/100</div>
                    <div class="trust-bar-bg">
                        <div class="trust-bar-fill" style="width: {{ result.get('trust_score', 0) }}%;"></div>
                    </div>
                </div>

                <div>
                    <div class="field-label">Flags</div>
                    <div class="flags">
                        {% if result.get('flags') %}
                            {% for flag in result['flags'] %}
                                <span class="flag-chip">{{ flag }}</span>
                            {% endfor %}
                        {% else %}
                            <span class="no-flags">No flags raised</span>
                        {% endif %}
                    </div>
                </div>
            {% else %}
                <div class="error">No record found for plate "{{ plate }}".</div>
            {% endif %}
        {% endif %}
    </div>
</body>
</html>
"""


@app.route("/")
def home():
    plate = request.args.get("plate")
    result = None
    if plate:
        result = get_vehicle_status(plate, load_master())
    return render_template_string(
        TEMPLATE,
        plate=plate,
        result=result,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)