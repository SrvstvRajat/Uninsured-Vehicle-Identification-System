
"""
Federated SQL console: a Flask blueprint that lets the user type any SQL
query, shows how it was decomposed, and returns the live integrated result.

Routes
    GET  /sql        -> the console page
    POST /sql/run    -> JSON  {"sql": "...", "explain": false}
"""

from flask import Blueprint, jsonify, render_template_string, request

from federated_sql import ALLOW_WRITES, TABLES, run_federated

sql_bp = Blueprint("sql_console", __name__)

SAMPLES = [
    ("Uninsured vehicles (Registration x Insurance)",
     "SELECT v.reg_plate, v.make, v.model, v.owner_name\n"
     "FROM vehicles v\n"
     "LEFT JOIN insurance_policies i\n"
     "       ON v.plate_key = i.plate_key AND i.policy_end_date >= CURDATE()\n"
     "WHERE i.id IS NULL\n"
     "LIMIT 50"),
    ("Stolen vehicles with owner (Registration x Theft)",
     "SELECT v.reg_plate, v.owner_name, t.theft_date, t.status\n"
     "FROM vehicles v\n"
     "JOIN theft_records t ON v.plate_key = t.plate_key\n"
     "WHERE t.status = 'stolen'"),
    ("4-database 360 view",
     "SELECT v.reg_plate, v.make, i.insurer_name, i.policy_end_date,\n"
     "       r.rto_office, t.status AS theft_status\n"
     "FROM vehicles v\n"
     "LEFT JOIN insurance_policies i ON v.plate_key = i.plate_key\n"
     "LEFT JOIN rto_records r        ON v.plate_key = r.plate_key\n"
     "LEFT JOIN theft_records t      ON v.plate_key = t.plate_key\n"
     "LIMIT 50"),
    ("Aggregate: policies per insurer",
     "SELECT insurer_name, COUNT(*) AS policies, ROUND(AVG(premium_amount), 2) AS avg_premium\n"
     "FROM insurance_policies\n"
     "GROUP BY insurer_name\n"
     "ORDER BY policies DESC"),
    ("Sub-query across databases",
     "SELECT reg_plate, make, model FROM vehicles\n"
     "WHERE plate_key IN (SELECT plate_key FROM theft_records WHERE status = 'shredded')"),
    ("Single table with filter (full push-down)",
     "SELECT * FROM rto_records WHERE rto_office LIKE '%Delhi%' LIMIT 20"),
    ("Noisy / OCR plate (fuzzy match)",
     "SELECT * FROM vehicles WHERE reg_plate = 'UPo9AI88@5'"),
    ("Plates starting with a prefix (% wildcard)",
     "SELECT * FROM vehicles WHERE reg_plate = 'DL01%'"),
    ("Partial plate",
     "SELECT * FROM vehicles WHERE reg_plate = 'UP09'"),
    ("Misspelt owner name (any word order)",
     "SELECT reg_plate, make, model, owner_name FROM vehicles WHERE owner_name = 'sharma, rajt'"),
    ("Misspelt make + colour",
     "SELECT reg_plate, make, model, color FROM vehicles WHERE make = 'Hyundi' AND color = 'gray'"),
    ("Damaged engine number",
     "SELECT reg_plate, engine_no, chassis_no FROM vehicles WHERE engine_no = 'ENGOOO1234'"),
    ("Noisy plate across 2 databases",
     "SELECT v.reg_plate, v.make, v.owner_name, i.insurer_name, i.policy_end_date\n"
     "FROM vehicles v\n"
     "LEFT JOIN insurance_policies i ON v.plate_key = i.plate_key\n"
     "WHERE v.reg_plate = 'DL1OAJ653t'"),
    ("Schema", "SHOW TABLES"),
]

PAGE = r"""
<!doctype html>
<html>
<head>
<title>Federated SQL Console</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
         background: linear-gradient(135deg, #1e3a5f 0%, #4a6fa5 100%);
         min-height: 100vh; margin: 0; padding: 24px; color: #1f2d3d; }
  .wrap { max-width: 1250px; margin: 0 auto; }
  .card { background: #fff; border-radius: 12px; padding: 22px 26px;
          box-shadow: 0 10px 30px rgba(0,0,0,.25); margin-bottom: 18px; }
  h1 { margin: 0 0 4px; font-size: 24px; color: #1e3a5f; }
  h2 { margin: 0 0 12px; font-size: 16px; color: #1e3a5f; }
  .sub { color: #5b6b7c; font-size: 14px; margin-bottom: 14px; }
  .nav a { color: #4a6fa5; font-size: 14px; text-decoration: none; }
  textarea { width: 100%; height: 170px; font-family: Consolas, Menlo, monospace;
             font-size: 14px; padding: 12px; border: 2px solid #d5deea;
             border-radius: 8px; resize: vertical; }
  textarea:focus { outline: none; border-color: #4a6fa5; }
  .bar { display: flex; gap: 10px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  button { border: 0; border-radius: 8px; padding: 10px 20px; font-size: 14px;
           font-weight: 600; cursor: pointer; }
  .run { background: #1e3a5f; color: #fff; }
  .run:hover { background: #2c5282; }
  .ghost { background: #e8eef7; color: #1e3a5f; }
  select { padding: 9px; border-radius: 8px; border: 1px solid #d5deea; max-width: 360px; }
  .hint { font-size: 12px; color: #5b6b7c; margin-left: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th { background: #1e3a5f; color: #fff; text-align: left; padding: 8px 10px;
       position: sticky; top: 0; }
  td { padding: 7px 10px; border-bottom: 1px solid #e6ecf4; white-space: nowrap; }
  tr:nth-child(even) td { background: #f6f9fd; }
  .scroll { max-height: 440px; overflow: auto; border: 1px solid #e6ecf4; border-radius: 8px; }
  .meta { font-size: 13px; color: #5b6b7c; margin-bottom: 10px; }
  .err { background: #fdecea; color: #a02622; padding: 12px 14px; border-radius: 8px;
         font-size: 14px; white-space: pre-wrap; }
  .warn { background: #fff7e0; color: #7a5a00; padding: 8px 12px; border-radius: 8px;
          font-size: 13px; margin-bottom: 8px; }
  .step { border-left: 4px solid #4a6fa5; background: #f6f9fd; padding: 10px 14px;
          border-radius: 0 8px 8px 0; margin-bottom: 10px; font-size: 13px; }
  .step.bad { border-color: #c0392b; background: #fdf1ef; }
  .step b { color: #1e3a5f; }
  pre { margin: 6px 0 0; padding: 10px; background: #0f1b2d; color: #d6e4ff;
        border-radius: 6px; overflow-x: auto; font-size: 12.5px; white-space: pre-wrap; }
  .pill { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11px;
          font-weight: 700; margin-left: 6px; }
  .ok { background: #dff5e3; color: #1b6e2f; }
  .no { background: #fbd9d5; color: #a02622; }
  .null { color: #9aa7b6; font-style: italic; }
  table.fz { width:auto; margin-top:6px; font-size:12.5px; }
  table.fz th { position:static; background:#4a6fa5; padding:5px 10px; }
  .bar2 { display:inline-block; height:8px; background:#4a6fa5; border-radius:4px; vertical-align:middle; margin-right:6px; }
  details summary { cursor: pointer; font-size: 13px; color: #4a6fa5; margin: 6px 0; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="nav"><a href="/">&larr; Vehicle plate lookup</a></div>
    <h1>Federated SQL Console</h1>
    <div class="sub">
      Write any SQL against the global schema. The coordinator splits it, queries the source
      databases live, and integrates the answers. Tables:
      {% for t, s in tables.items() %}<code>{{ t }}</code> ({{ s.database }}){% if not loop.last %}, {% endif %}{% endfor %}.
      Use <code>plate_key</code> to join across sources (normalised plate).
    </div>
    <textarea id="sql" spellcheck="false" placeholder="SELECT ...">SELECT v.reg_plate, v.make, v.model, v.owner_name
FROM vehicles v
LEFT JOIN insurance_policies i
       ON v.plate_key = i.plate_key AND i.policy_end_date >= CURDATE()
WHERE i.id IS NULL
LIMIT 50</textarea>
    <div class="bar">
      <button class="run" id="runBtn">&#9654; Run query</button>
      <button class="ghost" id="explainBtn">Show plan only</button>
      <label style="font-size:13px;color:#1e3a5f;font-weight:600;">
        <input type="checkbox" id="fuzzy" checked> Fuzzy matching (any column)
      </label>
      <select id="samples"><option value="">Example queries&hellip;</option>
        {% for label, q in samples %}<option value="{{ loop.index0 }}">{{ label }}</option>{% endfor %}
      </select>
      <span class="hint">Ctrl+Enter to run{% if not writes %} &middot; writes disabled{% endif %}</span>
    </div>
  </div>

  <div class="card" id="resultCard" style="display:none"><h2>Result</h2><div id="result"></div></div>
  <div class="card" id="planCard" style="display:none"><h2>How the query was decomposed</h2><div id="plan"></div></div>
</div>

<script>
const SAMPLES = {{ samples_json|safe }};
const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function renderResult(r) {
  const box = $('result'); box.innerHTML = '';
  $('resultCard').style.display = 'block';
  if (!r.ok) { box.appendChild(el('div', 'err', r.error)); return; }
  (r.warnings || []).forEach(w => box.appendChild(el('div', 'warn', w)));
  if (r.kind === 'explain') {
    box.appendChild(el('div', 'meta', 'Plan only: the result query was not executed.')); return;
  }
  if (r.kind === 'write') {
    box.appendChild(el('div', 'meta', 'Statement executed on the owning source. Rows affected: ' + r.rows[0][0]));
    return;
  }
  let meta = r.row_count + ' row(s)';
  if (r.plan && r.plan.total_ms) meta += ' in ' + r.plan.total_ms + ' ms (live)';
  box.appendChild(el('div', 'meta', meta));
  const wrap = el('div', 'scroll'), t = el('table'), th = el('tr');
  r.columns.forEach(c => th.appendChild(el('th', '', c)));
  const head = el('thead'); head.appendChild(th); t.appendChild(head);
  const body = el('tbody');
  r.rows.forEach(row => {
    const tr = el('tr');
    row.forEach(v => {
      const td = v === null ? el('td', 'null', 'NULL') : el('td', '', String(v));
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  t.appendChild(body); wrap.appendChild(t); box.appendChild(wrap);
}

function renderPlan(plan) {
  const box = $('plan'); box.innerHTML = '';
  if (!plan) { $('planCard').style.display = 'none'; return; }
  $('planCard').style.display = 'block';

  const s0 = el('div', 'step');
  s0.appendChild(el('b', '', '1. Parsed your query'));
  s0.appendChild(el('pre', '', plan.original_sql));
  box.appendChild(s0);

  (plan.fuzzy || []).forEach(f => {
    const d = el('div', 'step');
    const kinds = {plate: 'plate matcher', code: 'code matcher', name: 'name matcher', text: 'text matcher'};
    d.appendChild(el('b', '', '1b. Fuzzy matching on ' + f.database + '.' + f.table + '.' + f.column +
      ' (' + (kinds[f.kind] || f.kind) + '; ' + f.candidates_scanned + ' distinct stored values compared, ' + f.ms + ' ms)'));
    d.appendChild(el('div', 'meta', 'Original condition: ' + f.original));
    f.literals.forEach(l => {
      d.appendChild(el('div', 'meta', 'Noisy input "' + l.query + '" ' +
        (l.exact ? '-> exact match found, no approximation used' :
         (l.matches.length ? (l.low_confidence ? '-> no strong match; closest available values (LOW confidence):' : '-> approximate matches (best first):')
                           : '-> nothing in the database resembles this value, condition left unchanged'))));
      if (l.matches.length) {
        const t = el('table', 'fz'), hr = el('tr');
        ['Stored value', 'Similarity'].forEach(h => hr.appendChild(el('th', '', h)));
        t.appendChild(hr);
        l.matches.forEach(m => {
          const tr = el('tr'); tr.appendChild(el('td', '', m.plate));
          const td = el('td'); const bar = el('span', 'bar2');
          bar.style.width = Math.round(m.score * 100) + 'px';
          td.appendChild(bar); td.appendChild(document.createTextNode((m.score * 100).toFixed(1) + '%'));
          tr.appendChild(td); t.appendChild(tr);
        });
        d.appendChild(t);
      }
    });
    if (f.rewritten) d.appendChild(el('div', 'meta', 'The condition was rewritten to match exactly these stored values before querying the source.'));
    box.appendChild(d);
  });

  const subs = plan.subqueries || [];
  const s1 = el('div', 'step');
  s1.appendChild(el('b', '', '2. Decomposed into ' + subs.length + ' source sub-quer' + (subs.length === 1 ? 'y' : 'ies') + ' (run in parallel)'));
  box.appendChild(s1);
  subs.forEach(s => {
    const d = el('div', 'step' + (s.status === 'error' ? ' bad' : ''));
    const h = el('div');
    h.appendChild(el('b', '', s.source + ' / ' + s.database + '.' + s.table));
    const pill = el('span', 'pill ' + (s.status === 'error' ? 'no' : 'ok'),
      s.status === 'planned' ? 'PLANNED' : (s.status === 'ok' ? 'AVAILABLE' : 'UNAVAILABLE'));
    h.appendChild(pill);
    d.appendChild(h);
    if (s.status === 'ok') d.appendChild(el('div', 'meta', s.rows_fetched + ' row(s) returned in ' + s.ms + ' ms'));
    if (s.error) d.appendChild(el('div', 'err', s.error));
    if (s.pushed_filters && s.pushed_filters.length)
      d.appendChild(el('div', 'meta', 'Filters pushed down to the source: ' + s.pushed_filters.length));
    d.appendChild(el('pre', '', s.sql));
    box.appendChild(d);
  });

  if (plan.integration_sql) {
    const s2 = el('div', 'step');
    s2.appendChild(el('b', '', '3. Integrated at the coordinator (joins / aggregates / sort)' +
      (plan.integration_ms !== undefined ? ' in ' + plan.integration_ms + ' ms' : '')));
    s2.appendChild(el('pre', '', plan.integration_sql));
    box.appendChild(s2);
  }
}

async function go(explain) {
  const sql = $('sql').value;
  $('runBtn').disabled = $('explainBtn').disabled = true;
  $('runBtn').textContent = 'Running...';
  try {
    const resp = await fetch('/sql/run', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({sql: sql, explain: explain, fuzzy: $('fuzzy').checked})
    });
    const r = await resp.json();
    renderResult(r); renderPlan(r.plan);
  } catch (e) {
    renderResult({ok: false, error: 'Request failed: ' + e}); renderPlan(null);
  } finally {
    $('runBtn').disabled = $('explainBtn').disabled = false;
    $('runBtn').innerHTML = '&#9654; Run query';
  }
}

$('runBtn').onclick = () => go(false);
$('explainBtn').onclick = () => go(true);
$('sql').addEventListener('keydown', e => { if (e.ctrlKey && e.key === 'Enter') go(false); });
$('samples').onchange = e => { if (e.target.value !== '') $('sql').value = SAMPLES[e.target.value]; };
</script>
</body>
</html>
"""


@sql_bp.route("/sql")
def sql_page():
    import json

    return render_template_string(
        PAGE,
        tables=TABLES,
        samples=SAMPLES,
        samples_json=json.dumps([q for _, q in SAMPLES]).replace("</", "<\\/"),
        writes=ALLOW_WRITES,
    )


@sql_bp.route("/sql/run", methods=["POST"])
def sql_run():
    data = request.get_json(silent=True) or {}
    result = run_federated(
        data.get("sql", ""),
        explain_only=bool(data.get("explain")),
        fuzzy=data.get("fuzzy"),
    )
    return jsonify(result)