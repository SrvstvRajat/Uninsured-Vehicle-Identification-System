"""Shared look & feel for every coordinator page (home, SQL console, cleaning, errors).

One stylesheet + one app bar so all pages stay visually consistent.
UI only: nothing here touches data, routing or business logic.
"""
from markupsafe import Markup, escape

FONT_LINKS = Markup(
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700'
    '&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
)

NAV_ITEMS = (
    ("lookup", "/", "Vehicle lookup"),
    ("sql", "/sql", "SQL console"),
    ("cleaning", "/cleaning", "Data cleaning"),
)


def appbar(active=""):
    """Top navigation bar; `active` is one of lookup / sql / cleaning."""
    links = "".join(
        '<a href="%s"%s>%s</a>' % (
            href, ' aria-current="page"' if key == active else "", escape(label))
        for key, href, label in NAV_ITEMS
    )
    return Markup(
        '<header class="appbar"><div class="appbar-in">'
        '<a class="brand" href="/"><span class="brand-mark">FV</span>'
        'Federated Vehicle Lookup</a>'
        '<nav class="topnav" aria-label="Tools">%s</nav>'
        '</div></header>' % links
    )


THEME_CSS = Markup(r"""
/* ===== Design system: tokens ===== */
:root{
  --bg:#f4f6f8; --surface:#ffffff; --surface-2:#f8f9fb; --line:#e4e8ec; --line-2:#d3dae1;
  --ink:#121c26; --ink-2:#364454; --muted:#667587; --faint:#98a3af;
  --brand:#12404f; --brand-2:#0d3340; --brand-50:#eef4f6; --brand-100:#d9e6ea;
  --ok:#1b7a52; --ok-bg:#e8f4ed; --ok-line:#b9dcc9;
  --warn:#955e08; --warn-bg:#fbf2df; --warn-line:#ecd5a1;
  --bad:#b03a2c; --bad-bg:#fbece9; --bad-line:#efc3bc;
  --info:#2a58a6; --info-bg:#eaf0f9; --info-line:#c4d3ee;
  --c-vehicles:#3d66b5; --c-insurance:#2a8a64; --c-rto:#7656a3; --c-theft:#bd4a37;
  --r-sm:6px; --r:8px; --r-lg:12px;
  --sh-1:0 1px 2px rgba(16,28,40,.05);
  --sh-2:0 1px 2px rgba(16,28,40,.04),0 8px 20px -8px rgba(16,28,40,.12);
  --sh-3:0 24px 48px -12px rgba(16,28,40,.30);
  --ring:0 0 0 3px rgba(18,64,79,.16);
  --font:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
  --plate:"Barlow Condensed","Roboto Condensed","Arial Narrow",sans-serif;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:400 14px/1.5 var(--font);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--brand)}
::selection{background:var(--brand-100)}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px}
.num{font-variant-numeric:tabular-nums}

/* ===== App bar ===== */
.appbar{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.88);-webkit-backdrop-filter:saturate(1.4) blur(10px);backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--line)}
.appbar-in{max-width:1120px;margin:0 auto;padding:0 20px;height:52px;display:flex;align-items:center;gap:18px}
.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;font-weight:650;font-size:14px;letter-spacing:-.01em;white-space:nowrap}
.brand-mark{min-width:26px;height:26px;padding:0 5px;border-radius:7px;background:var(--brand);color:#fff;display:grid;place-items:center;font-size:10.5px;font-weight:700;letter-spacing:.02em;box-shadow:inset 0 0 0 1px rgba(255,255,255,.14),var(--sh-1)}
.brand small{color:var(--muted);font-weight:500;font-size:12.5px;padding-left:10px;margin-left:2px;border-left:1px solid var(--line-2)}
.topnav{display:flex;gap:2px;margin-left:auto}
.topnav a{color:var(--muted);text-decoration:none;font-weight:500;font-size:13px;padding:6px 11px;border-radius:var(--r-sm);transition:background .15s,color .15s}
.topnav a:hover{background:var(--surface-2);color:var(--ink)}
.topnav a[aria-current=page]{background:var(--brand-50);color:var(--brand);font-weight:600}

/* ===== Layout ===== */
.wrap{max-width:1120px;margin:0 auto;padding-left:20px;padding-right:20px}
.page{padding-top:24px;padding-bottom:56px}
.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin:0 0 18px;flex-wrap:wrap}
.page-title{margin:0;font-size:20px;font-weight:650;letter-spacing:-.015em;line-height:1.25}
.page-sub{margin:4px 0 0;color:var(--muted);font-size:13px;max-width:68ch}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.stack>*+*{margin-top:16px}

/* ===== Card ===== */
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--sh-1)}
.card-head{padding:13px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.card-title{margin:0;font-size:13.5px;font-weight:600;letter-spacing:-.005em}
.card-sub{color:var(--muted);font-size:12px;margin-left:auto}
.card-body{padding:18px}

/* ===== Buttons ===== */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;font:600 13px/1 var(--font);padding:9px 14px;min-height:36px;border-radius:var(--r);border:1px solid transparent;cursor:pointer;text-decoration:none;white-space:nowrap;background:var(--brand);color:#fff;box-shadow:var(--sh-1),inset 0 1px 0 rgba(255,255,255,.12);transition:background .15s,border-color .15s,box-shadow .15s,transform .06s}
.btn:hover{background:var(--brand-2)}
.btn:active{transform:translateY(.5px)}
.btn:focus-visible{outline:none;box-shadow:var(--ring)}
.btn[disabled]{opacity:.55;cursor:default;transform:none}
.btn--quiet{background:#fff;color:var(--ink-2);border-color:var(--line-2);box-shadow:var(--sh-1)}
.btn--quiet:hover{background:var(--surface-2);border-color:#bcc6d0}
.btn--ghost{background:transparent;color:var(--brand);border-color:var(--brand-100);box-shadow:none}
.btn--ghost:hover{background:var(--brand-50);border-color:#b9cfd6}
.btn--sm{padding:6px 11px;min-height:30px;font-size:12.5px}

/* ===== Form controls (zero specificity so components can override) ===== */
:where(.ui) :where(input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=hidden]),select,textarea){
  width:100%;min-width:0;font:500 13.5px/1.4 var(--font);color:var(--ink);background:#fff;border:1px solid var(--line-2);
  border-radius:var(--r);padding:8px 10px;min-height:36px;transition:border-color .15s,box-shadow .15s,background .15s}
:where(.ui) :where(input,select,textarea):hover{border-color:#b6c1cc}
:where(.ui) :where(input,select,textarea):focus{outline:none;border-color:var(--brand);box-shadow:var(--ring)}
:where(.ui) :where(input,textarea)::placeholder{color:var(--faint);font-weight:400}
:where(.ui) select{appearance:none;-webkit-appearance:none;cursor:pointer;padding-right:30px;
  background:#fff url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' fill='none' stroke='%23667587' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>") no-repeat right 11px center}
:where(.ui) textarea{resize:vertical;line-height:1.5}
:where(.ui) label{display:block;font-size:12px;font-weight:500;color:var(--muted);margin:0 0 5px}
:where(.ui) input[type=checkbox]{accent-color:var(--brand);width:14px;height:14px;vertical-align:-2px;margin:0 6px 0 0}
:where(.ui) input[type=file]{font:500 12.5px var(--font);color:var(--muted);max-width:100%}
:where(.ui) input[type=file]::file-selector-button{font:600 12.5px var(--font);margin-right:10px;padding:7px 12px;border-radius:var(--r);border:1px solid var(--line-2);background:#fff;color:var(--ink-2);cursor:pointer;transition:background .15s}
:where(.ui) input[type=file]::file-selector-button:hover{background:var(--surface-2)}

/* ===== Tables ===== */
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:var(--r-lg);background:#fff;box-shadow:var(--sh-1)}
.card>.table-wrap,.card-body>.table-wrap{border:0;border-radius:0;box-shadow:none}
.tbl{width:100%;border-collapse:collapse;font-size:13px}
.tbl th{position:sticky;top:0;z-index:1;background:var(--surface-2);color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;text-align:left;padding:9px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
.tbl td{padding:10px 14px;border-bottom:1px solid var(--line);vertical-align:middle;font-variant-numeric:tabular-nums}
.tbl tbody tr:last-child td{border-bottom:0}
.tbl tbody tr{transition:background .12s}
.tbl tbody tr:hover{background:#f6f9fb}
.tbl .empty-row td{text-align:center;color:var(--muted);padding:28px 14px}
.plate-tag{display:inline-block;font:600 12px/1 var(--mono);letter-spacing:.05em;padding:5px 8px;border-radius:5px;background:var(--surface-2);border:1px solid var(--line-2);color:var(--ink);text-transform:uppercase}

/* ===== Badges / status ===== */
.badge{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;line-height:1.5;padding:1px 9px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.85}
.badge-ok{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}
.badge-warn{background:var(--warn-bg);color:var(--warn);border-color:var(--warn-line)}
.badge-bad{background:var(--bad-bg);color:var(--bad);border-color:var(--bad-line)}
.badge-info{background:var(--info-bg);color:var(--info);border-color:var(--info-line)}
.badge-neutral{background:#eef1f4;color:#4a5866;border-color:var(--line-2)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:currentColor}

/* ===== Notices ===== */
.notice{background:var(--info-bg);border:1px solid var(--info-line);color:#23477f;border-radius:var(--r);padding:10px 14px;margin:0 0 12px;font-size:13px;line-height:1.5;animation:rise .22s ease both}
.notice--ok{background:var(--ok-bg);border-color:var(--ok-line);color:#14583c}
.notice--warn{background:var(--warn-bg);border-color:var(--warn-line);color:#74480a}
.notice--bad{background:var(--bad-bg);border-color:var(--bad-line);color:#8d2d21}
.notice strong{font-weight:600}
.notice ul{margin:6px 0 0;padding-left:18px}
.notice p{margin:4px 0 0}
.notice a{font-weight:600}

/* ===== Metrics & meter ===== */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:14px 16px;box-shadow:var(--sh-1)}
.stat-number{font-size:26px;font-weight:650;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.stat-label{margin-top:4px;font-size:12px;color:var(--muted)}
.meter{height:6px;border-radius:99px;background:#e6ebef;overflow:hidden}
.meter i{display:block;height:100%;border-radius:99px;background:var(--ok);transform-origin:left;animation:grow .7s cubic-bezier(.2,.7,.2,1) both}
.meter.mid i{background:#c98a13}
.meter.low i{background:var(--bad)}

/* ===== Modal ===== */
.modal-overlay{position:fixed;inset:0;z-index:60;display:none;align-items:center;justify-content:center;padding:20px;background:rgba(13,22,31,.46);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)}
.modal-overlay.open{display:flex;animation:fade .15s ease both}
.modal-box{background:#fff;border:1px solid var(--line);border-radius:14px;box-shadow:var(--sh-3);width:100%;max-width:720px;max-height:82vh;display:flex;flex-direction:column;overflow:hidden;animation:rise .2s ease both}
.modal-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line)}
.modal-head h3{margin:0;font-size:14px;font-weight:600}
.modal-close{border:0;background:transparent;color:var(--muted);width:28px;height:28px;border-radius:7px;font-size:20px;line-height:1;cursor:pointer;transition:background .15s,color .15s}
.modal-close:hover{background:var(--surface-2);color:var(--ink)}
.modal-body{padding:16px 18px;overflow:auto}
.modal-loading{color:var(--muted);font-size:13px;padding:10px 0}
.modal-error{background:var(--bad-bg);border:1px solid var(--bad-line);color:#8d2d21;border-radius:var(--r);padding:10px 14px;font-size:13px}

/* ===== Motion ===== */
@keyframes rise{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
@media (max-width:640px){.appbar-in,.wrap{padding-left:14px;padding-right:14px}.brand small{display:none}.page{padding-top:18px}.appbar-in{flex-wrap:wrap;height:auto;min-height:52px;padding-top:8px;padding-bottom:8px;row-gap:6px}.topnav{width:100%;margin-left:0;overflow-x:auto}.topnav a{flex:1;text-align:center;white-space:nowrap}}

""")
