"""
Federated SQL console: a Flask blueprint that lets the user type any SQL
query, shows how it was decomposed, and returns the live integrated result.

Routes
    GET  /sql        -> the console page
    POST /sql/run    -> JSON  {"sql": "...", "explain": false}
"""

from flask import Blueprint, jsonify, render_template_string, request

from federated_sql import ALLOW_WRITES, TABLES, check_source_health, run_federated
from ui_theme import THEME_CSS, FONT_LINKS, appbar

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
<html lang="en">
<head>
<title>Federated SQL Console</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{{ font_links }}
<style>
{{ theme_css }}
body.ui{min-height:100vh;background:
  radial-gradient(ellipse at 8% 18%,rgba(77,157,128,.13),transparent 34%),
  radial-gradient(ellipse at 94% 42%,rgba(93,117,189,.12),transparent 38%),
  linear-gradient(145deg,#eaf2ee 0%,#e8eef2 52%,#f1eee6 100%);background-attachment:fixed}
.sql-page{max-width:1120px;padding-top:26px;padding-bottom:64px}
.sql-hero{position:relative;overflow:hidden;padding:clamp(22px,4vw,34px);border-radius:18px;color:#fff;
  background:linear-gradient(118deg,#123844 0%,#14515a 52%,#273c67 100%);
  border:1px solid rgba(255,255,255,.13);box-shadow:0 22px 50px -26px rgba(14,43,59,.55)}
.sql-hero::after{content:"";position:absolute;width:310px;height:310px;right:-95px;top:-170px;
  border:1px solid rgba(255,255,255,.14);border-radius:50%;box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025)}
.sql-hero>*{position:relative;z-index:1}
.sql-eyebrow{display:inline-flex;align-items:center;gap:8px;color:#c6eee5;font-size:10.5px;font-weight:700;
  letter-spacing:.12em;text-transform:uppercase}
.sql-eyebrow::before{content:"";width:7px;height:7px;border-radius:50%;background:#65e0ae;box-shadow:0 0 0 4px rgba(101,224,174,.15)}
.sql-hero h1{margin:8px 0;font-size:clamp(25px,3.4vw,34px);font-weight:700;letter-spacing:-.035em;line-height:1.12;color:#fff}
.sql-hero p{max-width:72ch;margin:0;color:#c0d7dc;font-size:13.5px;line-height:1.65}
.sql-caps{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
.sql-cap{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;color:#e2eff0;
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:999px;font-size:10.5px;font-weight:600}
.sql-cap::before{content:"";width:6px;height:6px;border-radius:50%;background:#ffc56b}
.sql-section{margin-top:16px;overflow:hidden}
.sql-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;
  padding:15px 18px;border-bottom:1px solid var(--line)}
.sql-section-head h2{margin:0;color:var(--ink);font-size:14px;font-weight:650}
.sql-section-head p{margin:3px 0 0;color:var(--muted);font-size:12px}
.sql-schema{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.sql-schema code{padding:4px 8px;background:#edf4f1;border:1px solid #d8e5df;border-radius:6px;
  color:#24564e;font:600 11px var(--mono)}
.sql-editor-wrap{padding:16px 18px 18px}
#sql{display:block;width:100%;min-height:210px;resize:vertical;padding:16px 18px;
  color:#e1edf4;background:#142638;border:1px solid #284456;border-radius:11px;
  font:13px/1.65 var(--mono);tab-size:4;box-shadow:inset 0 1px 4px rgba(0,0,0,.18)}
#sql:hover{border-color:#456779}
#sql:focus{outline:none;border-color:#5cae9a;box-shadow:0 0 0 3px rgba(92,174,154,.18),inset 0 1px 4px rgba(0,0,0,.18)}
#sql::placeholder{color:#8fa8b7}
.sql-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:9px;margin-top:13px}
.sql-toolbar .btn{min-height:36px}
.sql-toolbar select{width:auto;max-width:min(360px,100%);min-width:220px}
.sql-toolbar .sql-fuzzy{display:inline-flex;align-items:center;gap:7px;margin:0;padding:8px 10px;
  color:var(--ink-2);background:#f7faf8;border:1px solid var(--line);border-radius:8px;font-size:12px}
.sql-toolbar .sql-fuzzy input{width:14px;height:14px;margin:0;accent-color:var(--brand)}
.sql-run{background:linear-gradient(135deg,#176451,#24477b);box-shadow:0 7px 16px -9px rgba(19,69,76,.65)}
.sql-run:hover{background:linear-gradient(135deg,#1d755f,#2e568d)}
.sql-explain{background:#eef4f6;color:#24505b;border:1px solid #d6e5e8;box-shadow:none}
.sql-explain:hover{background:#e3eef1}
.sql-hint{margin-left:auto;color:var(--muted);font-size:11.5px}
.sql-runtime{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:999px;
  background:var(--ok-bg);border:1px solid var(--ok-line);color:var(--ok);font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase}
.sql-runtime.off{background:var(--warn-bg);border-color:var(--warn-line);color:var(--warn)}
.sql-runtime::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.sql-body{padding:16px 18px 18px}
.sql-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;color:var(--muted);font-size:12px}
.sql-meta strong{color:var(--ink-2);font-size:13px}
.sql-scroll{max-height:480px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}
.sql-results-table{width:100%;border-collapse:separate;border-spacing:0;font-size:12px}
.sql-results-table th{position:sticky;top:0;z-index:1;padding:10px 12px;text-align:left;white-space:nowrap;
  color:#344455;background:#edf3f2;border-bottom:1px solid #d9e4e0;font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase}
.sql-results-table td{padding:9px 12px;border-bottom:1px solid #edf0f2;color:var(--ink-2);white-space:nowrap;font:12px var(--mono)}
.sql-results-table tbody tr:nth-child(even) td{background:#f8faf9}
.sql-results-table tbody tr:hover td{background:#eef5f2}
.sql-null{color:var(--faint);font-style:italic}
.sql-alert{padding:11px 13px;border-radius:9px;margin-bottom:9px;font-size:12.5px;line-height:1.55}
.sql-alert:last-child{margin-bottom:0}
.sql-alert-error{color:#8d2d21;background:var(--bad-bg);border:1px solid var(--bad-line)}
.sql-alert-warn{color:var(--warn);background:var(--warn-bg);border:1px solid var(--warn-line)}
.sql-empty{padding:24px;text-align:center;color:var(--muted);font-size:12.5px}
.sql-empty strong{display:block;margin-bottom:3px;color:var(--ink-2);font-size:13px}
.sql-step{margin:0 0 10px;padding:13px 14px;border:1px solid var(--line);border-left:3px solid #518b88;
  border-radius:9px;background:linear-gradient(145deg,#fbfdfc,#f3f7f5);font-size:12px}
.sql-step:last-child{margin-bottom:0}
.sql-step.bad{border-left-color:var(--bad);background:#fdf5f3}
.sql-step b{color:var(--ink-2);font-size:12px}
.sql-step-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.sql-step-meta{margin-top:8px;color:var(--muted);font-size:11.5px;overflow-wrap:anywhere}
.sql-code{margin:9px 0 0;padding:12px 14px;overflow:auto;border:1px solid #294253;border-radius:8px;
  color:#d8e9ef;background:#152838;font:11.5px/1.55 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere}
.sql-pill{display:inline-flex;align-items:center;padding:4px 9px;border-radius:999px;
  font-size:9.5px;font-weight:750;letter-spacing:.06em}
.sql-pill-ok{color:var(--ok);background:var(--ok-bg);border:1px solid var(--ok-line)}
.sql-pill-no{color:var(--bad);background:var(--bad-bg);border:1px solid var(--bad-line)}
.sql-pill-plan{color:var(--info);background:var(--info-bg);border:1px solid var(--info-line)}
.sql-source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:9px;margin-bottom:12px}
.sql-source-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;
  border:1px solid var(--line);border-radius:9px;background:linear-gradient(145deg,#fbfdfc,#f3f7f5)}
.sql-source-name{min-width:0}
.sql-source-name strong{display:block;color:var(--ink-2);font-size:12px}
.sql-source-name code{display:block;margin-top:2px;color:var(--muted);font:10.5px var(--mono);overflow-wrap:anywhere}
.sql-pill-issue{color:var(--warn);background:var(--warn-bg);border:1px solid var(--warn-line)}
.sql-query-error{padding:12px 14px;border:1px solid var(--bad-line);border-radius:9px;
  color:#8d2d21;background:var(--bad-bg);font-size:12.5px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}
.sql-query-error strong{display:block;margin-bottom:3px;font-size:12px}
.sql-fuzzy-table{width:auto;margin-top:8px;border-collapse:collapse;font-size:11.5px}
.sql-fuzzy-table th{position:static;padding:6px 9px;color:var(--ink-2);background:#edf3f2;border:1px solid var(--line);text-align:left}
.sql-fuzzy-table td{padding:6px 9px;border:1px solid var(--line);font-family:var(--mono)}
.sql-score{display:inline-block;height:7px;margin-right:6px;border-radius:999px;background:#5a9b8b;vertical-align:middle}
@media(max-width:640px){
  .sql-page{padding-top:18px}.sql-hero{padding:21px 17px}
  .sql-editor-wrap,.sql-body{padding:13px}
  #sql{min-height:190px;padding:13px;font-size:12px}
  .sql-toolbar>*{flex:1 1 100%;width:100%!important;max-width:none!important}
  .sql-toolbar .sql-fuzzy{justify-content:flex-start}
  .sql-hint{margin-left:0}
  .sql-section-head{padding:13px}
}
</style>
</head>
<body class="ui">
{{ appbar('sql') }}
<main class="wrap page sql-page">
  <section class="sql-hero">
    <span class="sql-eyebrow">Federated data workspace</span>
    <h1>SQL Console</h1>
    <p>Query the shared vehicle schema. The coordinator routes work to the source databases, executes compatible subqueries in parallel, and integrates the result into one view.</p>
    <div class="sql-caps" aria-label="Console features">
      <span class="sql-cap">Live source queries</span>
      <span class="sql-cap">Cross-database joins</span>
      <span class="sql-cap">{% if writes %}Writes enabled{% else %}Read-only mode{% endif %}</span>
    </div>
  </section>

  <section class="card sql-section" aria-labelledby="editor-title">
    <div class="sql-section-head">
      <div><h2 id="editor-title">Compose a query</h2><p>Use <code>plate_key</code> to join records across source databases.</p></div>
      <span class="sql-runtime{% if writes %} off{% endif %}">{% if writes %}Writes enabled{% else %}Read-only mode{% endif %}</span>
    </div>
    <div class="sql-editor-wrap">
      <div class="sql-schema" aria-label="Available tables">
        {% for t, s in tables.items() %}<code>{{ t }}</code>{% endfor %}
      </div>
    <textarea id="sql" spellcheck="false" aria-label="SQL query" placeholder="SELECT ...">SELECT v.reg_plate, v.make, v.model, v.owner_name
FROM vehicles v
LEFT JOIN insurance_policies i
       ON v.plate_key = i.plate_key AND i.policy_end_date >= CURDATE()
WHERE i.id IS NULL
LIMIT 50</textarea>
    <div class="sql-toolbar">
      <button class="btn sql-run" id="runBtn">&#9654; Run query</button>
      <button class="btn sql-explain" id="explainBtn">Show plan only</button>
      <label class="sql-fuzzy"><input type="checkbox" id="fuzzy" checked> Fuzzy matching</label>
      <select id="samples"><option value="">Example queries&hellip;</option>
        {% for label, q in samples %}<option value="{{ loop.index0 }}">{{ label }}</option>{% endfor %}
      </select>
      <span class="sql-hint">Ctrl+Enter to run</span>
    </div>
    </div>
  </section>

  <section class="card sql-section" id="resultCard" aria-labelledby="result-title" style="display:none">
    <div class="sql-section-head"><div><h2 id="result-title">Query result</h2><p id="result-description">Integrated output from the live federated query.</p></div></div>
    <div class="sql-body" id="result"></div>
  </section>
  <section class="card sql-section" id="planCard" aria-labelledby="plan-title" style="display:none">
    <div class="sql-section-head"><div><h2 id="plan-title">Execution plan</h2><p>See how the query was parsed, routed, and integrated.</p></div></div>
    <div class="sql-body" id="plan"></div>
  </section>
</main>

<script>
const SAMPLES = {{ samples_json|safe }};
const $ = id => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function sourceAvailability(status, error) {
  if (status === 'ok') return {label: 'ONLINE', className: 'sql-pill-ok'};
  if (status === 'planned') return {label: 'PLANNED', className: 'sql-pill-plan'};
  if (/cannot reach|timed out|did not answer|host is down|connection refused|network is unreachable|no route to host/i.test(error || '')) {
    return {label: 'OFFLINE', className: 'sql-pill-no'};
  }
  return {label: 'ISSUE', className: 'sql-pill-issue'};
}

function renderSourceStatuses(plan) {
  const sources = Array.isArray(plan) ? plan : ((plan && plan.subqueries) || []);
  if (!sources.length) return false;
  const list = el('div', 'sql-source-list');
  sources.forEach(source => {
    const item = el('div', 'sql-source-item');
    const name = el('div', 'sql-source-name');
    name.appendChild(el('strong', '', source.source));
    name.appendChild(el('code', '', source.database));
    const availability = typeof source.available === 'boolean'
      ? {label: source.available ? 'ONLINE' : 'OFFLINE',
         className: source.available ? 'sql-pill-ok' : 'sql-pill-no'}
      : sourceAvailability(source.status, source.error);
    item.appendChild(name);
    item.appendChild(el('span', 'sql-pill ' + availability.className, availability.label));
    list.appendChild(item);
  });
  $('result').appendChild(list);
  return true;
}

function renderResult(r) {
  const box = $('result'); box.innerHTML = '';
  $('resultCard').style.display = 'block';
  renderSourceStatuses(r.source_status || r.plan);
  if (!r.ok) {
    $('result-title').textContent = 'Database status';
    $('result-description').textContent = 'Live status of all four source databases.';
    const error = el('div', 'sql-query-error');
    error.appendChild(el('strong', '', 'Query issue'));
    error.appendChild(document.createTextNode(r.error || 'The query could not be completed.'));
    box.appendChild(error);
    return;
  }
  $('result-title').textContent = 'Query result';
  $('result-description').textContent = 'Live status of all four source databases and integrated query output.';
  (r.warnings || []).forEach(w => box.appendChild(el('div', 'sql-alert sql-alert-warn', w)));
  if (r.kind === 'explain') {
    box.appendChild(el('div', 'sql-meta', 'Plan only: the result query was not executed.')); return;
  }
  if (r.kind === 'write') {
    box.appendChild(el('div', 'sql-meta', 'Statement executed on the owning source. Rows affected: ' + r.rows[0][0]));
    return;
  }
  let meta = r.row_count + ' row(s)';
  if (r.plan && r.plan.total_ms) meta += ' in ' + r.plan.total_ms + ' ms (live)';
  const summary = el('div', 'sql-meta');
  summary.appendChild(el('strong', '', meta));
  box.appendChild(summary);
  if (!r.rows || !r.rows.length) {
    const empty = el('div', 'sql-empty');
    empty.appendChild(el('strong', '', 'No rows returned'));
    empty.appendChild(document.createTextNode('The query ran successfully, but no records matched.'));
    box.appendChild(empty);
    return;
  }
  const wrap = el('div', 'sql-scroll'), t = el('table', 'sql-results-table'), th = el('tr');
  r.columns.forEach(c => th.appendChild(el('th', '', c)));
  const head = el('thead'); head.appendChild(th); t.appendChild(head);
  const body = el('tbody');
  r.rows.forEach(row => {
    const tr = el('tr');
    row.forEach(v => {
      const td = v === null ? el('td', 'sql-null', 'NULL') : el('td', '', String(v));
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

  const s0 = el('div', 'sql-step');
  s0.appendChild(el('b', '', '1. Parsed your query'));
  s0.appendChild(el('pre', 'sql-code', plan.original_sql));
  box.appendChild(s0);

  (plan.fuzzy || []).forEach(f => {
    const d = el('div', 'sql-step');
    const kinds = {plate: 'plate matcher', code: 'code matcher', name: 'name matcher', text: 'text matcher'};
    d.appendChild(el('b', '', '1b. Fuzzy matching on ' + f.database + '.' + f.table + '.' + f.column +
      ' (' + (kinds[f.kind] || f.kind) + '; ' + f.candidates_scanned + ' distinct stored values compared, ' + f.ms + ' ms)'));
    d.appendChild(el('div', 'sql-step-meta', 'Original condition: ' + f.original));
    f.literals.forEach(l => {
      d.appendChild(el('div', 'sql-step-meta', 'Noisy input "' + l.query + '" ' +
        (l.exact ? '-> exact match found, no approximation used' :
         (l.matches.length ? (l.low_confidence ? '-> no strong match; closest available values (LOW confidence):' : '-> approximate matches (best first):')
                           : '-> nothing in the database resembles this value, condition left unchanged'))));
      if (l.matches.length) {
        const t = el('table', 'sql-fuzzy-table'), hr = el('tr');
        ['Stored value', 'Similarity'].forEach(h => hr.appendChild(el('th', '', h)));
        t.appendChild(hr);
        l.matches.forEach(m => {
          const tr = el('tr'); tr.appendChild(el('td', '', m.plate));
          const td = el('td'); const bar = el('span', 'sql-score');
          bar.style.width = Math.round(m.score * 100) + 'px';
          td.appendChild(bar); td.appendChild(document.createTextNode((m.score * 100).toFixed(1) + '%'));
          tr.appendChild(td); t.appendChild(tr);
        });
        d.appendChild(t);
      }
    });
    if (f.rewritten) d.appendChild(el('div', 'sql-step-meta', 'The condition was rewritten to match exactly these stored values before querying the source.'));
    box.appendChild(d);
  });

  const subs = plan.subqueries || [];
  const s1 = el('div', 'sql-step');
  s1.appendChild(el('b', '', '2. Decomposed into ' + subs.length + ' source sub-quer' + (subs.length === 1 ? 'y' : 'ies') + ' (run in parallel)'));
  box.appendChild(s1);
  subs.forEach(s => {
    const d = el('div', 'sql-step' + (s.status === 'error' ? ' bad' : ''));
    const h = el('div', 'sql-step-head');
    h.appendChild(el('b', '', s.source + ' / ' + s.database + '.' + s.table));
    const availability = sourceAvailability(s.status, s.error);
    const pill = el('span', 'sql-pill ' + availability.className, availability.label);
    h.appendChild(pill);
    d.appendChild(h);
    if (s.endpoint) d.appendChild(el('div', 'sql-step-meta', 'Served via REST API: POST ' + s.endpoint));
    if (s.status === 'ok') d.appendChild(el('div', 'sql-step-meta', s.rows_fetched + ' row(s) returned in ' + s.ms + ' ms'));
    if (s.error) d.appendChild(el('div', 'sql-alert sql-alert-error', s.error));
    if (s.pushed_filters && s.pushed_filters.length)
      d.appendChild(el('div', 'sql-step-meta', 'Filters pushed down to the source: ' + s.pushed_filters.length));
    d.appendChild(el('pre', 'sql-code', s.sql));
    box.appendChild(d);
  });

  if (plan.integration_sql) {
    const s2 = el('div', 'sql-step');
    s2.appendChild(el('b', '', '3. Integrated at the coordinator (joins / aggregates / sort)' +
      (plan.integration_ms !== undefined ? ' in ' + plan.integration_ms + ' ms' : '')));
    s2.appendChild(el('pre', 'sql-code', plan.integration_sql));
    box.appendChild(s2);
  }
}

async function go(explain) {
  const sql = $('sql').value;
  $('runBtn').disabled = $('explainBtn').disabled = true;
  $('runBtn').textContent = 'Running query...';
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
    $('runBtn').textContent = '▶ Run query';
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
        theme_css=THEME_CSS,
        font_links=FONT_LINKS,
        appbar=appbar,
    )


@sql_bp.route("/sql/run", methods=["POST"])
def sql_run():
    data = request.get_json(silent=True) or {}
    result = run_federated(
        data.get("sql", ""),
        explain_only=bool(data.get("explain")),
        fuzzy=data.get("fuzzy"),
    )
    result["source_status"] = check_source_health()
    return jsonify(result)