"""
Phase 3 — "Context search" page on the coordinator (Flask blueprint, like the SQL console).

    GET /context?q=Is UP09AI88I5 insured and was it ever stolen?
    GET /context?q=...&plate=UP09AI8815        (after picking one of several candidates)
    GET /context/api?q=...                     same result as JSON (demo, evaluation)

The page walks through the pipeline in order:
  1. query understanding  2. vehicle (Phase 2 entity matching)
  3. federation: which machine answered which sub-query, how fast
  4. context per database: rows, hop, FK path, relevance (round 1 + round 2)
  5. cross-database links discovered in round 2
  6. correlated documents from the laptops, with why they matched
"""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template_string, request

from context_engine import DEFAULT_DEPTH, discover
from ui_theme import FONT_LINKS, THEME_CSS, appbar
from unstructured import search_documents

context_bp = Blueprint("context_search", __name__)

EXAMPLES = [
    "Is {plate} insured and was it ever stolen?",
    "Ownership history of {plate}",
    "Show challans and fitness status of {plate}",
]
SKIP_COLUMNS = {"id", "plate_key"}
SOURCE_ORDER = ("vehicles", "insurance", "rto", "theft")


def _brief(row: dict, limit: int = 6) -> list[tuple[str, str]]:
    items = [(k, str(v)) for k, v in row.items()
             if v not in (None, "") and k not in SKIP_COLUMNS and not k.endswith("_id")]
    return items[:limit]


def _run(q: str, plate: str | None, depth: int, with_docs: bool = True) -> dict:
    ctx = discover(q, plate=plate, depth=depth)
    ctx["documents"] = (search_documents(ctx) if with_docs and ctx["status"] == "ok"
                        else None)
    return ctx


@context_bp.route("/context/api")
def context_api():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify(error="Give ?q=<your question>"), 400
    depth = max(1, min(int(request.args.get("depth", DEFAULT_DEPTH)), 3))
    ctx = _run(q, request.args.get("plate"), depth,
               with_docs=request.args.get("docs", "1") != "0")
    for node in ctx.get("nodes", []):
        node.pop("key", None)
    return jsonify(ctx)


@context_bp.route("/context")
def context_page():
    q = (request.args.get("q") or "").strip()
    depth = max(1, min(int(request.args.get("depth", DEFAULT_DEPTH)), 3))
    ctx = _run(q, request.args.get("plate"), depth) if q else None
    grouped = {}
    if ctx:
        for node in ctx["nodes"]:
            grouped.setdefault(node["source"], {}).setdefault(node["table"], []).append(node)
    return render_template_string(
        TEMPLATE, q=q, depth=depth, ctx=ctx, grouped=grouped, brief=_brief,
        source_order=SOURCE_ORDER, examples=EXAMPLES, appbar=appbar,
        theme_css=THEME_CSS, font_links=FONT_LINKS)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Context search — Federated Vehicle Lookup</title>
{{ font_links }}
<style>
{{ theme_css }}
.ctx-form{display:flex;gap:10px;flex-wrap:wrap}
.ctx-form input[type=text]{flex:1 1 420px;min-height:40px;padding:8px 12px;border:1px solid var(--line-2);border-radius:var(--r);font:15px var(--font)}
.ctx-form select{min-height:40px;border:1px solid var(--line-2);border-radius:var(--r);padding:0 8px;font:13px var(--font)}
.examples{margin-top:10px;font-size:12.5px;color:var(--muted)}
.examples a{margin-right:12px;color:var(--brand)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;padding:2px 9px;border-radius:999px;background:var(--surface-2);border:1px solid var(--line-2)}
.chip b{font-weight:600;color:var(--muted);margin-right:4px}
.src{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:middle}
.src-vehicles{background:var(--c-vehicles)} .src-insurance{background:var(--c-insurance)}
.src-rto{background:var(--c-rto)} .src-theft{background:var(--c-theft)}
.node{border:1px solid var(--line);border-radius:var(--r);padding:8px 10px;margin:6px 0;background:var(--surface)}
.node-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:12.5px}
.node-head .rel{width:90px}
.node-row{font-size:12.5px;color:var(--ink-2);margin-top:5px;line-height:1.55}
.node-row span{margin-right:12px} .node-row b{color:var(--muted);font-weight:500}
.via{font:12px var(--mono);color:var(--muted)}
.r2{border-left:3px solid var(--info)}
.doc{border:1px solid var(--line);border-radius:var(--r);padding:10px 12px;margin:8px 0}
.doc-snip{font-size:13px;color:var(--ink-2);margin-top:6px;white-space:pre-wrap}
.why{font-size:12px;color:var(--ok);margin-top:4px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.kv{font-size:13px;line-height:1.7} .kv b{color:var(--muted);font-weight:500;display:inline-block;min-width:120px}
.small{font-size:12px;color:var(--muted)}
</style></head>
<body class="ui">
{{ appbar('context') }}
<main class="wrap page stack">
  <div class="page-head">
    <span class="eyebrow">Phase 3 · structured + unstructured integration</span>
    <h1 class="page-title">Context search</h1>
    <p class="page-sub">Ask about a vehicle. Every source database discovers its own context
      by walking its foreign keys; the coordinator links the databases and finds the
      documents that belong to that context.</p>
  </div>

  <section class="card"><div class="card-body">
    <form class="ctx-form" method="get" action="/context">
      <input type="text" name="q" value="{{ q }}" placeholder="e.g. Is UP09AI88I5 insured and was it ever stolen?" autofocus>
      <select name="depth" title="FK hops each database walks">
        {% for d in (1,2,3) %}<option value="{{ d }}" {% if d==depth %}selected{% endif %}>depth {{ d }}</option>{% endfor %}
      </select>
      <button class="btn" type="submit">Discover context</button>
    </form>
    <div class="examples">Try:
      {% for e in examples %}<a href="/context?q={{ e.format(plate='UP09AI8815')|urlencode }}">{{ e.format(plate='…') }}</a>{% endfor %}
    </div>
  </div></section>

{% if ctx %}
  {% if ctx.status == 'choose' %}
  <section class="card"><div class="card-head"><h2 class="card-title">Which vehicle?</h2>
    <span class="card-sub">{{ ctx.message }}</span></div>
    <div class="card-body">
    {% for c in ctx.candidates %}
      <div class="node"><span class="plate-tag">{{ c.plate }}</span>
        score {{ '%.2f'|format(c.score) }} · in {{ c.sources|join(', ') }}
        <a class="btn btn--sm btn--quiet" href="/context?q={{ q|urlencode }}&plate={{ c.plate }}&depth={{ depth }}">Use this vehicle</a></div>
    {% endfor %}</div></section>
  {% elif ctx.status in ('not_found', 'unavailable') %}
  <div class="notice notice--warn">{{ ctx.message }}</div>
  {% else %}

  <!-- 1. query understanding -->
  <section class="card"><div class="card-head"><h2 class="card-title">1 · Query understanding</h2>
    <span class="card-sub">total {{ '%.0f'|format(ctx.elapsed_ms) }} ms</span></div>
    <div class="card-body chips">
      {% for k in ('plates','phones','names','fir_nos','policy_nos','chassis','engines') %}
        {% for v in ctx.parsed[k] %}<span class="chip"><b>{{ k }}</b>{{ v }}</span>{% endfor %}
      {% endfor %}
      {% for i in ctx.intents %}<span class="badge badge-info">intent: {{ i }}{% if ctx.coverage.get(i) %} ✓{% else %} – none found{% endif %}</span>{% endfor %}
      {% if not ctx.intents %}<span class="small">no specific intent detected: general context</span>{% endif %}
      {% for t in ctx.parsed.terms[:10] %}<span class="chip">{{ t }}</span>{% endfor %}
    </div></section>

  <!-- 2. vehicle -->
  {% if ctx.vehicle %}{% set v = ctx.vehicle %}
  <section class="card"><div class="card-head"><h2 class="card-title">2 · Vehicle (Phase 2 entity matching)</h2>
    <span class="plate-tag">{{ v.vehicle_key }}</span>
    <span class="badge {% if v.decision.startswith('OK') %}badge-ok{% elif 'INCONCLUSIVE' in v.decision %}badge-warn{% else %}badge-bad{% endif %}">{{ v.decision }}</span>
    <span class="card-sub">trust {{ v.trust_score }}</span></div>
    <div class="card-body grid2">
      <div class="kv"><b>Make / model</b>{{ v.make or '—' }} {{ v.model or '' }}<br><b>Colour</b>{{ v.color or '—' }}<br><b>Owner</b>{{ v.owner or '—' }}</div>
      <div class="kv"><b>Insurer</b>{{ v.insurer or '—' }}<br><b>Policy ends</b>{{ v.policy_end_date or '—' }}<br><b>Theft status</b>{{ v.theft_status or '—' }}</div>
      <div class="kv">{% for l in ctx.entity_links %}<b>{{ l.source }}</b>{{ l.stored_plate }}{% if not l.exact %} <span class="small">(linked {{ '%.0f'|format(l.link_score*100) }}%)</span>{% endif %}<br>{% endfor %}</div>
    </div></section>
  {% endif %}

  <!-- 3. federation -->
  <section class="card"><div class="card-head"><h2 class="card-title">3 · Federated sub-queries</h2>
    <span class="card-sub">each call ran on that laptop; the database walked its own FK graph</span></div>
    <div class="table-wrap"><table class="tbl"><thead><tr><th>Round</th><th>Machine</th><th>Seed</th><th>Status</th><th>Rows kept</th><th>Examined / pruned</th><th>ms</th></tr></thead><tbody>
    {% for c in ctx.calls %}<tr>
      <td>{{ c.round }}</td><td><span class="src src-{{ c.source }}"></span>{{ c.machine }}</td>
      <td class="via">{% for s in c.seeds %}{{ s.table }}.{{ s.column }} {{ c.match }} {{ s['values'][:3]|join(', ') }}{% if not loop.last %}<br>{% endif %}{% endfor %}</td>
      <td>{% if c.status == 'ok' %}<span class="badge badge-ok">ok</span>{% else %}<span class="badge badge-warn" title="{{ c.error or '' }}">{{ c.status }}</span>{% endif %}</td>
      <td>{{ c.rows }}</td>
      <td>{% if c.stats %}{{ c.stats.rows_examined }} / {{ c.stats.pruned }}{% else %}—{% endif %}</td><td>{{ c.ms }}</td></tr>
    {% endfor %}</tbody></table></div></section>

  <!-- 4. context per database -->
  <section class="card"><div class="card-head"><h2 class="card-title">4 · Context per database</h2>
    <span class="card-sub">{{ ctx.nodes|length }} rows kept, {{ ctx.pruned_nodes }} pruned as less related to the query</span></div>
    <div class="card-body">
    {% for source in source_order %}{% if grouped.get(source) %}
      <h3 class="card-title" style="margin:10px 0 4px"><span class="src src-{{ source }}"></span>{{ source }}</h3>
      {% for table, rows in grouped[source].items() %}
        {% for n in rows %}
        <div class="node {% if n.round == 2 %}r2{% endif %}">
          <div class="node-head"><b>{{ table }}</b>
            <span class="badge badge-neutral">hop {{ n.hop }}</span>
            {% if n.round == 2 %}<span class="badge badge-info">round 2 via {{ n.link.identifier }}</span>{% endif %}
            <span class="rel"><span class="meter {% if n.relevance < 0.5 %}low{% elif n.relevance < 0.75 %}mid{% endif %}"><i style="width:{{ (n.relevance*100)|round }}%"></i></span></span>
            <span class="small">relevance {{ '%.2f'|format(n.relevance) }}</span>
            <span class="via">{{ n.via or 'seed (query result)' }}</span></div>
          <div class="node-row">{% for k, val in brief(n.row) %}<span><b>{{ k }}</b> {{ val }}</span>{% endfor %}</div>
        </div>{% endfor %}
      {% endfor %}
    {% endif %}{% endfor %}
    </div></section>

  <!-- 5. cross-database links -->
  <section class="card"><div class="card-head"><h2 class="card-title">5 · Cross-database links (round 2: beyond the plate)</h2></div>
    <div class="card-body">
    {% if ctx.cross_links %}
    <div class="table-wrap"><table class="tbl"><thead><tr><th>Identifier</th><th>Found in</th><th>Looked up in</th><th>Status</th><th>Rows</th></tr></thead><tbody>
    {% for l in ctx.cross_links %}<tr><td>{{ l.identifier }}: <span class="via">{{ l['values'][:3]|join(', ') }}</span></td>
      <td>{{ l['from']|join(', ') }}</td><td><span class="src src-{{ l.target }}"></span>{{ l.target }}.{{ l.target_table }}.{{ l.target_column }} ({{ l.match }})</td>
      <td>{% if l.status == 'ok' %}<span class="badge badge-ok">ok</span>{% else %}<span class="badge badge-warn">{{ l.status }}</span>{% endif %}</td><td>{{ l.rows }}</td></tr>{% endfor %}
    </tbody></table></div>
    {% else %}<p class="small">No new identifiers to follow into other databases.</p>{% endif %}
    <p class="small">Context summary sent to document search — identifiers:
      {% for k, vals in ctx.identifiers.items() %}<b>{{ k }}</b> {{ vals|length }} {% endfor %}·
      places: {{ ctx.places[:5]|join(', ') or '—' }} · date window: {{ ctx.date_window|join(' → ') if ctx.date_window else '—' }}</p>
    </div></section>

  <!-- 6. documents -->
  {% set d = ctx.documents %}
  <section class="card"><div class="card-head"><h2 class="card-title">6 · Correlated documents (unstructured)</h2>
    <span class="card-sub">{% if d %}{{ d.docs|length }} documents · {{ '%.0f'|format(d.elapsed_ms) }} ms{% endif %}</span></div>
    <div class="card-body">
    {% if d %}
      <div class="chips" style="margin-bottom:8px">{% for p in d.per_source %}<span class="chip"><span class="src src-{{ p.source }}"></span>{{ p.source }}: {% if p.status == 'ok' %}{{ p.returned }} of {{ p.stats.chunks }} chunks{% else %}{{ p.status }}{% endif %}</span>{% endfor %}</div>
      {% for doc in d.docs %}
      <div class="doc"><div class="node-head"><span class="src src-{{ doc.source }}"></span><b>{{ doc.doc_id }}</b>
        <span class="badge badge-neutral">{{ doc.doc_type }}</span><span class="small">{{ doc.machine }}</span>
        <span class="rel"><span class="meter {% if doc.score < 0.5 %}low{% elif doc.score < 0.7 %}mid{% endif %}"><i style="width:{{ (doc.score*100)|round }}%"></i></span></span>
        <span class="small">score {{ '%.2f'|format(doc.score) }} ({% for k, val in doc.breakdown.items() %}{{ k }} {{ '%.2f'|format(val) }}{% if not loop.last %}, {% endif %}{% endfor %})</span>
        {% if doc.attached_to %}<span class="via">→ {{ doc.attached_to.id }}</span>{% endif %}</div>
        <div class="why">matched on: {{ doc.matched_on|join(' · ') }}</div>
        <div class="doc-snip">{{ doc.snippet }}</div></div>
      {% else %}<p class="small">No document agrees with this context.</p>{% endfor %}
    {% else %}<p class="small">Document search not run.</p>{% endif %}
    <p class="small"><a href="/context/api?q={{ q|urlencode }}{% if request.args.get('plate') %}&plate={{ request.args.get('plate') }}{% endif %}&depth={{ depth }}">View this context as JSON</a></p>
    </div></section>
  {% endif %}
{% endif %}
</main></body></html>
"""
