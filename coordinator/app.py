# FUZZY_MIN_SCORE = 0.60
# FUZZY_MIN_MARGIN = 0.07
# FUZZY_TOP_K = 5

# from flask import Flask, request, render_template_string, redirect, url_for
# from werkzeug.utils import secure_filename

# import csv
# import re
# import time
# from functools import lru_cache
# from pathlib import Path

# from mediator import (query_vehicle, list_candidate_plates, normalize_plate,
#                       list_vehicle_profiles, check_source_status)
# from fuzzy_match import plate_similarity
# from detail_match import (rank_with_details, decide, DETAIL_FIELDS,
#                           SECTIONS, DETAIL_LABELS)
# from plate_ocr import (recognize_plate_image, MAX_IMAGE_BYTES,
#                        PlateOCRInputError, PlateOCREngineError)
# from reporting import report_flags
# from sql_console import sql_bp          # <-- NEW: federated SQL console
# from ui_theme import THEME_CSS, FONT_LINKS, appbar   # shared look & feel
# from plate_correct import correct_plate  # position-aware plate correction (from friend)

# app = Flask(__name__)
# app.config['MAX_CONTENT_LENGTH'] = MAX_IMAGE_BYTES + 1024 * 1024
# app.register_blueprint(sql_bp)          # <-- NEW: adds /sql and /sql/run

# TEMPLATE = """
# <!doctype html>
# <html lang="en">
# <head>
# <meta charset="utf-8">
# <title>Federated Vehicle Lookup</title>
# <meta name="viewport" content="width=device-width, initial-scale=1">
# {{ font_links }}
# <style>
# {{ theme_css }}
# /* ===== Home: hero ===== */
# .hero-wrap{padding-top:24px}
# .hero-card{position:relative;overflow:hidden;border-radius:20px;padding:clamp(22px,4vw,36px);color:#fff;
#   background:linear-gradient(118deg,#123844 0%,#14515a 52%,#273c67 100%);
#   border:1px solid rgba(255,255,255,.13);box-shadow:0 22px 50px -26px rgba(14,43,59,.55)}
# .hero-card::before{content:"";position:absolute;inset:0;pointer-events:none;
#   background:radial-gradient(520px 260px at 92% 3%,rgba(95,226,190,.18),transparent 68%),
#   radial-gradient(440px 220px at 0% 120%,rgba(255,190,92,.16),transparent 68%)}
# .hero-card>*{position:relative}
# .hero-intro{display:grid;grid-template-columns:minmax(0,1fr) 250px;align-items:center;gap:28px}
# .hero-copy{min-width:0}
# .hero-kicker{display:inline-flex;align-items:center;gap:8px;margin:0 0 12px!important;
#   color:#c6eee5!important;font-size:10.5px!important;font-weight:700;letter-spacing:.12em;
#   text-transform:uppercase}
# .hero-kicker::before{content:"";width:8px;height:8px;border-radius:50%;background:#65e0ae;
#   box-shadow:0 0 0 5px rgba(101,224,174,.15)}
# .hero h1,.hero-card h1{margin:0 0 9px;font-size:clamp(26px,3.2vw,36px);font-weight:700;
#   letter-spacing:-.035em;line-height:1.12}
# .hero-card p{margin:0 0 16px;color:#c0d7dc;font-size:13.5px;max-width:64ch;line-height:1.65}
# .hero-meta{display:flex;flex-wrap:wrap;gap:7px}
# .hero-meta span{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;
#   color:#e2eff0;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
#   border-radius:999px;font-size:10.5px;font-weight:600}
# .hero-meta span::before{content:"";width:6px;height:6px;border-radius:50%;background:#ffc56b}
# .network-visual{width:100%;max-width:250px;justify-self:end;filter:drop-shadow(0 12px 20px rgba(5,22,32,.2))}
# .network-visual svg{display:block;width:100%;height:auto;overflow:visible}
# .network-visual .link{fill:none;stroke:rgba(211,239,236,.46);stroke-width:2;stroke-dasharray:4 5}
# .network-visual .node{stroke:rgba(255,255,255,.8);stroke-width:2}
# .network-visual .node-label{fill:#f4fbfa;font:600 10px var(--font);text-anchor:middle}
# .network-visual .center-label{fill:#163d4a;font:700 9px var(--font);text-anchor:middle}
# #lookup{display:flex;gap:10px;align-items:stretch}
# #lookup .actions{display:flex;margin:0}
# #lookup .btn{height:100%;min-height:54px;padding:0 23px;font-size:13.5px;
#   background:linear-gradient(135deg,#ffe09b,#ffc76a);color:#303747;
#   box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 8px 20px -9px rgba(0,0,0,.55);
#   transition:transform .15s,filter .15s,box-shadow .15s}
# #lookup .btn:hover{background:linear-gradient(135deg,#ffe7b1,#ffd17f);
#   transform:translateY(-1px);box-shadow:0 10px 22px -9px rgba(0,0,0,.6)}

# /* the plate */
# .plate{flex:1;min-width:0;display:flex;align-items:stretch;background:#fff;color:#0d1b21;border:2px solid #0d1b21;border-radius:9px;overflow:hidden;
#   box-shadow:inset 0 0 0 2px #fff,0 6px 18px -6px rgba(0,0,0,.5);transition:box-shadow .15s}
# .plate:focus-within{box-shadow:inset 0 0 0 2px #fff,0 0 0 3px rgba(217,154,31,.65),0 6px 18px -6px rgba(0,0,0,.5)}
# .plate-strip{background:linear-gradient(180deg,#3158c9,#25419a);color:#fff;width:40px;flex:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font:700 .64rem var(--plate);letter-spacing:.09em}
# .chakra{width:14px;height:14px;border:2px solid #fff;border-radius:50%;display:block;position:relative}
# .chakra::after{content:"";position:absolute;inset:2px;border-radius:50%;border:1px dashed #fff}
# .plate input[type=text]{flex:1;min-width:0;border:0;background:transparent;outline:none;box-shadow:none;border-radius:0;
#   font:700 32px/1 var(--plate);letter-spacing:.09em;text-transform:uppercase;color:#0d1b21;padding:12px 16px;text-align:center}
# .plate input[type=text]:hover,.plate input[type=text]:focus{border:0;box-shadow:none}
# .plate input::placeholder{color:#b8c2c7;font-weight:600}
# .plate-chars{font:700 26px/1 var(--plate);letter-spacing:.09em;padding:9px 18px;align-self:center}
# .plate--sm{flex:none;border-width:1.5px;border-radius:6px;box-shadow:none;display:inline-flex}
# .plate--sm .plate-strip{width:24px;font-size:.46rem;gap:2px}
# .plate--sm .chakra{width:9px;height:9px;border-width:1.5px}
# .plate--sm .chakra::after{display:none}
# .plate--sm .plate-chars{font-size:18px;padding:4px 11px}
# .plate--md{flex:none;box-shadow:none;border-color:#0d1b21}
# .plate--md .plate-chars{font-size:28px;padding:8px 18px}

# /* OCR row */
# .ocr{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.12);color:#a9c4cd;font-size:12.5px}
# .ocr input[type=file]{color:#c3d8df}
# .ocr input[type=file]::file-selector-button{background:rgba(255,255,255,.08);color:#fff;border-color:rgba(255,255,255,.25)}
# .ocr input[type=file]::file-selector-button:hover{background:rgba(255,255,255,.16)}
# .ocr .btn{background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.28);box-shadow:none;min-height:32px;padding:7px 13px;font-size:12.5px}
# .ocr .btn:hover{background:rgba(255,255,255,.18)}
# .ocr>span{color:#e0ebee;font-weight:600}

# /* ===== Unclear-plate filter ===== */
# .filter{margin-top:14px}
# .filter>details{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--sh-1);transition:box-shadow .2s}
# .filter>details[open]{box-shadow:var(--sh-2)}
# .filter summary{list-style:none;cursor:pointer;padding:12px 16px;display:flex;align-items:center;gap:10px;font-size:13.5px;font-weight:600;border-radius:var(--r-lg);transition:background .15s}
# .filter summary:hover{background:var(--surface-2)}
# .filter summary::-webkit-details-marker{display:none}
# .filter summary .caret{margin-left:auto;width:7px;height:7px;border-right:1.6px solid var(--muted);border-bottom:1.6px solid var(--muted);transform:rotate(45deg) translateY(-2px);transition:transform .18s}
# .filter details[open] .caret{transform:rotate(-135deg)}
# .pill{background:var(--brand-50);color:var(--brand);border:1px solid var(--brand-100);font-size:11.5px;font-weight:600;padding:1px 9px;border-radius:999px}
# .pill[hidden]{display:none}
# .filter-body{padding:2px 16px 16px;border-top:1px solid var(--line)}
# .filter-note{color:var(--muted);font-size:12.5px;margin:12px 0;max-width:70ch;line-height:1.55}
# .filter-note b{color:var(--ink-2)}
# .src-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
# .src{background:linear-gradient(155deg,#fff,var(--surface-2));border:1px solid var(--line);
#   border-top:3px solid var(--c);border-radius:10px;padding:11px 12px 14px;min-width:0;
#   transition:transform .16s,border-color .16s,box-shadow .16s}
# .src:hover{transform:translateY(-2px);box-shadow:var(--sh-2)}
# .src h3{display:flex;align-items:center;gap:7px;margin:0 0 2px;font-size:11px;font-weight:650;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2)}
# .src h3::before{content:"";width:8px;height:8px;border-radius:3px;background:var(--c)}
# .src-vehicles{--c:var(--c-vehicles)}.src-insurance{--c:var(--c-insurance)}.src-rto{--c:var(--c-rto)}.src-theft{--c:var(--c-theft)}
# .fld{margin-top:10px}
# .fld label{margin-bottom:4px;font-size:11.5px}
# .fld select,.fld input[type=text]{min-height:34px;padding:6px 9px;font-size:13px;background-color:#fff}
# .pick-txt{margin-top:6px}
# .pick-txt[hidden]{display:none}
# .filter-foot{display:flex;align-items:center;gap:10px;margin-top:16px;flex-wrap:wrap}
# .filter-foot span{color:var(--muted);font-size:12px}

# /* ===== Results ===== */
# main.wrap{padding-top:22px;padding-bottom:56px}
# .cands{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);margin:0 0 16px;overflow:hidden;box-shadow:var(--sh-1);animation:rise .25s ease both}
# .cands h2{font-size:13.5px;font-weight:600;margin:0;padding:13px 18px 2px}
# .cands>p{margin:0;padding:0 18px 11px;color:var(--muted);font-size:12px}
# .cand{display:grid;grid-template-columns:auto 150px 1fr auto;gap:14px;align-items:center;padding:11px 18px;border-top:1px solid var(--line);transition:background .12s}
# .cand:hover{background:#f7f9fb}
# .score{font-weight:600;font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums}
# .score-bar{display:block;margin-top:5px;height:5px;border-radius:99px;background:#e6ebef;overflow:hidden}
# .score-bar i{display:block;height:100%;border-radius:99px;background:var(--brand);transform-origin:left;animation:grow .6s cubic-bezier(.2,.7,.2,1) both}
# .chips{display:flex;flex-wrap:wrap;gap:5px;min-width:0}
# .chip{font-size:11.5px;padding:2px 8px;border-radius:6px;border:1px solid var(--line);background:var(--surface-2);white-space:nowrap;color:var(--ink-2)}
# .chip b{font-weight:600;color:var(--muted);margin-right:2px}
# .chip.match{background:var(--ok-bg);border-color:var(--ok-line);color:#14583c}
# .chip.partial{background:var(--warn-bg);border-color:var(--warn-line);color:#74480a}
# .chip.mismatch{background:var(--bad-bg);border-color:var(--bad-line);color:#8d2d21}
# .chip .mark{font-weight:700;margin-left:3px}
# .chip[class*="src-"]{border-left:3px solid var(--c)}
# .legend h2{font-size:13.5px;font-weight:600;margin:0 0 12px}
# .legend-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
# .legend-grid .src{background:var(--surface);padding:14px;box-shadow:var(--sh-1);transition:box-shadow .2s,transform .2s,border-color .2s}
# .legend-grid .src:hover{box-shadow:var(--sh-2);transform:translateY(-1px);border-color:var(--line-2)}
# .legend-grid .src p{margin:6px 0 0;color:var(--muted);font-size:12.5px;line-height:1.5}
# .legend-status{display:flex;align-items:center;justify-content:space-between;gap:8px;
#   margin-top:12px;padding-top:9px;border-top:1px solid var(--line);font-size:11px}
# .legend-status-label{color:var(--muted)}

# .record{background:var(--surface);border:1px solid var(--line);border-radius:18px;overflow:hidden;
#   box-shadow:0 16px 38px -24px rgba(17,44,61,.35);animation:rise .28s ease both}
# .record-head{padding:22px 24px;display:flex;flex-wrap:wrap;align-items:center;gap:14px 20px;
#   border-bottom:1px solid var(--line);background:linear-gradient(105deg,#fff 55%,#eef7f5)}
# .record-title{flex:1;min-width:180px}
# .record-title h2{margin:0;font-size:19px;font-weight:650;letter-spacing:-.015em;line-height:1.2}
# .record-title p{margin:3px 0 0;color:var(--muted);font-size:12.5px}
# .verdict{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;font-weight:650;letter-spacing:.06em;text-transform:uppercase;padding:6px 13px;border-radius:999px;border:1px solid}
# .verdict--clear{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
# .verdict--flag{color:var(--warn);background:var(--warn-bg);border-color:var(--warn-line)}
# .verdict--bad{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-line)}
# .assess{padding:18px 22px;display:grid;grid-template-columns:1fr 1.5fr;gap:18px 40px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#fcfdfd,#f8fafb)}
# .assess .lbl{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
# .trust-num{font-size:30px;font-weight:650;letter-spacing:-.03em;line-height:1;margin-bottom:10px;font-variant-numeric:tabular-nums}
# .trust-num small{font-size:13px;color:var(--muted);font-weight:500;letter-spacing:0;margin-left:2px}
# .decision{font-weight:600;font-size:14px;margin:0 0 12px;line-height:1.4}
# .flag{display:inline-block;background:var(--bad-bg);color:#8d2d21;border:1px solid var(--bad-line);font-size:11.5px;font-weight:500;padding:2px 10px;border-radius:999px;margin:0 6px 6px 0}
# .noflag{color:var(--muted);font-size:12.5px}
# .panels{display:grid;grid-template-columns:repeat(4,1fr)}
# .panel{position:relative;padding:19px 20px 20px;border-right:1px solid var(--line);
#   min-width:0;transition:background .15s}
# .panel::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--c)}
# .panel:last-child{border-right:0}
# .panel:hover{background:#fbfcfd}
# .panel header{display:flex;align-items:center;gap:7px;margin-bottom:4px}
# .panel header::before{content:"";width:8px;height:8px;border-radius:3px;background:var(--c)}
# .panel h3{margin:0;font-size:11px;font-weight:650;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2)}
# .panel dl{margin:0}
# .panel dt{font-size:11.5px;color:var(--muted);margin-top:11px}
# .panel dd{margin:1px 0 0;font-size:13.5px;font-weight:500;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
# .panel--alert{background:#fdf5f3}
# .panel--alert:hover{background:#fdf5f3}
# .empty{padding:22px;border-radius:14px}
# .empty-title{font-size:15px;font-weight:600;margin:0 0 4px}
# .empty p{margin:0;color:var(--muted);font-size:13px}
# .status-box{padding:14px 22px 16px;border-top:1px solid var(--line);background:var(--surface-2)}
# .empty .status-box{padding-left:0;padding-right:0;margin-top:14px;background:transparent}
# .status-box h3{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
# .status-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:0 28px}
# .status-item{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12.5px;padding:7px 0;border-bottom:1px dashed var(--line-2)}
# .st{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border:1px solid transparent;
#   border-radius:999px;font-weight:650;font-size:10.5px;letter-spacing:.04em;white-space:nowrap}
# .st.ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
# .st.down{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-line)}

# /* ===== Visual polish ===== */
# .hero-card{padding:clamp(22px,4vw,34px);border-radius:18px}
# .hero-kicker{display:inline-flex;align-items:center;gap:8px;margin:0 0 12px!important;
#   color:#d9e8ec!important;font-size:10.5px!important;font-weight:650;letter-spacing:.1em;
#   text-transform:uppercase}
# .hero-kicker::before{content:"";width:7px;height:7px;border-radius:50%;background:#56d19a;
#   box-shadow:0 0 0 4px rgba(86,209,154,.14)}
# .hero-card h1{font-size:clamp(25px,3.4vw,34px);letter-spacing:-.035em}
# .hero-card>p:not(.hero-kicker){font-size:14px;max-width:68ch}
# .hero-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
# .hero-meta span{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;
#   color:#d3e1e5;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);
#   border-radius:999px;font-size:11px;font-weight:550}
# .hero-meta span::before{content:"";width:5px;height:5px;border-radius:50%;background:#e2b85b}
# #lookup .btn{transition:transform .15s,background .15s,box-shadow .15s}
# #lookup .btn:hover{transform:translateY(-1px);box-shadow:0 8px 20px -7px rgba(0,0,0,.55)}
# .filter>details{overflow:hidden}
# .filter summary{min-height:50px}
# .filter summary:focus-visible{outline-offset:-3px}
# .filter details[open] summary{border-radius:var(--r-lg) var(--r-lg) 0 0}
# .src{transition:transform .16s,border-color .16s,box-shadow .16s}
# .src:focus-within{border-color:var(--brand);box-shadow:var(--ring)}
# .src-grid .src{border-top:3px solid var(--c);padding-top:10px}
# .filter-foot{padding-top:2px}
# .cands h2{font-size:15px;padding-top:16px}
# .cand{min-height:70px}
# .cand .btn{justify-self:end}
# .record-head{background:linear-gradient(110deg,#fff 55%,#f6f9fa)}
# .record-title h2{font-size:21px}
# .assess{grid-template-columns:minmax(150px,.7fr) minmax(0,2fr)}
# .panel{position:relative;padding-top:18px}
# .panel::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--c);opacity:.72}
# .panel--alert::before{background:var(--bad)}
# .panel dd{line-height:1.45}
# .status-box h3{display:flex;align-items:center;gap:8px}
# .status-box h3::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--ok)}
# .empty{border-left:4px solid var(--warn);background:linear-gradient(110deg,#fff,#fffdf8)}
# .legend{padding:20px;background:rgba(255,255,255,.58);border:1px solid var(--line);
#   border-radius:var(--r-lg)}
# .legend h2{font-size:15px}

# /* Bring the page background, navigation and content cards into one palette. */
# body.ui{
#   --surface:#f8fbf9;
#   --surface-2:#edf4f1;
#   --line:#d8e5df;
#   --line-2:#c8d8d1;
#   background:
#     radial-gradient(ellipse at 8% 22%,rgba(77,157,128,.13),transparent 35%),
#     radial-gradient(ellipse at 93% 48%,rgba(93,117,189,.11),transparent 38%),
#     linear-gradient(145deg,#eaf2ee 0%,#e8eef2 52%,#f1eee6 100%);
#   background-attachment:fixed;
# }
# .ui .appbar{
#   background:rgba(235,244,240,.9);
#   border-bottom-color:rgba(190,210,201,.8);
#   box-shadow:0 4px 18px rgba(35,67,62,.05);
# }
# .ui .brand-mark{
#   background:linear-gradient(145deg,#176451,#24477b);
# }
# .ui .filter>details,.ui .cands,.ui .record{
#   background:linear-gradient(145deg,rgba(250,252,250,.97),rgba(240,247,244,.96));
#   border-color:rgba(197,215,206,.9);
# }
# .ui .filter>details,.ui .cands{
#   box-shadow:0 10px 28px -22px rgba(30,69,62,.42);
# }
# .ui .filter>details[open]{
#   box-shadow:0 18px 38px -24px rgba(30,69,62,.45);
# }
# .ui .filter-body{
#   background:linear-gradient(180deg,rgba(237,245,241,.78),rgba(248,251,249,.94));
# }
# .ui .src-grid .src{
#   background:linear-gradient(150deg,#fbfdfb,#eef5f2);
#   border-right-color:#d7e4de;
#   border-bottom-color:#d7e4de;
#   border-left-color:#d7e4de;
# }
# .ui .legend{
#   background:linear-gradient(135deg,rgba(231,242,237,.94),rgba(236,239,247,.9));
#   border-color:#d4e1dc;
#   box-shadow:0 10px 30px -24px rgba(35,66,69,.42);
# }
# .ui .legend-grid .src{
#   background:linear-gradient(155deg,#fbfdfb,#edf4f1);
#   border-color:#d9e5df;
# }
# .ui .record-head{
#   background:linear-gradient(105deg,#f9fcfa 15%,#e8f4ef 68%,#edf0f8);
# }
# .ui .assess{
#   background:linear-gradient(105deg,#f0f6f3,#edf1f7);
# }
# .ui .panel{
#   background:rgba(249,252,250,.7);
# }
# .ui .panel:nth-child(even){
#   background:rgba(237,244,242,.68);
# }
# .ui .panel:hover{
#   background:#f8fcfa;
# }
# .ui .panel--alert,.ui .panel--alert:hover{
#   background:linear-gradient(140deg,#fbefec,#f9f4ef);
# }
# .ui .status-box{
#   background:linear-gradient(100deg,#eaf3ef,#eef1f7);
# }
# .ui .empty{
#   background:linear-gradient(120deg,#fbfcf8,#f5f0df);
# }

# @media (max-width:980px){
#   .hero-intro{grid-template-columns:minmax(0,1fr) 190px;gap:18px}
#   .network-visual{max-width:190px}
#   .src-grid,.legend-grid{grid-template-columns:1fr 1fr}
#   .panels{grid-template-columns:1fr 1fr}
#   .panel:nth-child(2){border-right:0}
#   .panel:nth-child(-n+2){border-bottom:1px solid var(--line)}
#   .cand{grid-template-columns:auto 130px 1fr}
#   .cand .btn{grid-column:3;justify-self:start}
# }
# @media (max-width:680px){
#   body.ui{background-attachment:scroll}
#   .hero-card{padding:20px 16px 16px}
#   .hero-intro{grid-template-columns:1fr;gap:8px}
#   .network-visual{display:none}
#   .hero-card h1{font-size:26px}
#   .hero-meta{gap:6px}
#   .hero-meta span{font-size:10.5px}
#   #lookup{flex-direction:column}
#   #lookup .btn{width:100%;min-height:44px}
#   .plate input[type=text]{font-size:26px;padding:10px 8px;letter-spacing:.05em}
#   .plate-strip{width:32px}
#   .src-grid,.legend-grid,.panels,.assess{grid-template-columns:1fr}
#   .panel{border-right:0;border-bottom:1px solid var(--line)}
#   .panel:last-child{border-bottom:0}
#   .cand{grid-template-columns:1fr;gap:8px}
#   .cand .btn{grid-column:auto;justify-self:stretch}
#   .filter-foot .btn{flex:1}
#   .record-head{padding:16px}
#   .assess{padding:16px;gap:18px}
#   .status-box{padding-left:16px;padding-right:16px}
#   .legend{padding:16px}
# }
# @media (prefers-reduced-motion:reduce){
#   *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;
#     animation-iteration-count:1!important;transition-duration:.01ms!important}
# }
# </style>
# </head>
# <body class="ui">

# {% macro source_badge(status) -%}
# {% if status.get('available') %}<span class="st ok">&#9679; Online</span>{% else %}<span class="st down">&#9679; Offline</span>{% endif %}
# {%- endmacro %}

# {% macro status_box(ss) -%}
# {% if ss %}
# <div class="status-box">
#     <h3>Live Source Status</h3>
#     <div class="status-list">
#     {% for source, status in ss.items() %}
#         <div class="status-item"><span>{{ source }}</span>
#         {{ source_badge(status) }}</div>
#     {% endfor %}
#     </div>
# </div>
# {% endif %}
# {%- endmacro %}

# {% macro pick(field, label) -%}
# {% set opts = field_options.get(field) or [] %}
# {% set cur = (details or {}).get(field, '') %}
# {% set custom = cur and (cur not in opts) %}
# <div class="fld">
#     <label for="{{ 's_' ~ field if opts else 'f_' ~ field }}">{{ label }}</label>
#     {% if opts %}
#     <div class="pick" data-field="{{ field }}">
#         <select class="pick-sel" id="s_{{ field }}">
#             <option value="">Any</option>
#             {% for o in opts %}<option value="{{ o }}"{% if o == cur %} selected{% endif %}>{{ o }}</option>{% endfor %}
#             <option value="__other"{% if custom %} selected{% endif %}>Other, type it&hellip;</option>
#         </select>
#         <input class="pick-txt" type="text" id="f_{{ field }}" name="{{ field }}" value="{{ cur }}"
#                placeholder="Type {{ label|lower }}" autocomplete="off"{% if not custom %} hidden{% endif %}>
#     </div>
#     {% else %}
#     <input type="text" id="f_{{ field }}" name="{{ field }}" value="{{ cur }}"
#            placeholder="Type {{ label|lower }}" autocomplete="off">
#     {% endif %}
# </div>
# {%- endmacro %}

# {{ appbar('lookup') }}

# <section class="wrap hero-wrap">
#     <div class="hero-card hero">
#         <div class="hero-intro">
#             <div class="hero-copy">
#                 <p class="hero-kicker">Coordinator · Live federated search</p>
#                 <h1>Check any vehicle across four registries</h1>
#                 <p>Mediation / Federated Virtual Integration &mdash; live query across
#                    independent vehicle, insurance, RTO and theft databases.
#                    Plate lookup supports local PaddleOCR and OCR-aware fuzzy suggestions.</p>
#                 <div class="hero-meta" aria-label="System characteristics">
#                     <span>Queries source databases live</span>
#                     <span>No central master copy</span>
#                     <span>Four independent registries</span>
#                 </div>
#             </div>
#             <div class="network-visual" aria-hidden="true">
#                 <svg viewBox="0 0 250 180" role="presentation">
#                     <path class="link" d="M125 91 51 38M125 91 199 38M125 91 51 144M125 91 199 144"/>
#                     <circle cx="51" cy="38" r="22" fill="#4569d4" class="node"/>
#                     <circle cx="199" cy="38" r="22" fill="#38ae82" class="node"/>
#                     <circle cx="51" cy="144" r="22" fill="#a47ad2" class="node"/>
#                     <circle cx="199" cy="144" r="22" fill="#e47d69" class="node"/>
#                     <circle cx="125" cy="91" r="34" fill="#f7cf7c" class="node"/>
#                     <text x="51" y="42" class="node-label">REG</text>
#                     <text x="199" y="42" class="node-label">INS</text>
#                     <text x="51" y="148" class="node-label">RTO</text>
#                     <text x="199" y="148" class="node-label">THEFT</text>
#                     <text x="125" y="88" class="center-label">LIVE</text>
#                     <text x="125" y="101" class="center-label">MATCH</text>
#                     <circle cx="125" cy="91" r="44" fill="none" stroke="rgba(255,255,255,.24)" stroke-width="1" stroke-dasharray="2 6"/>
#                 </svg>
#             </div>
#         </div>

#         <form method="get" action="/" id="lookup" autocomplete="off">
#             <div class="plate">
#                 <span class="plate-strip"><i class="chakra"></i>IND</span>
#                 <input type="text" name="plate" value="{{ plate or '' }}" placeholder="DL 01 AB 1234"
#                        aria-label="Vehicle plate" spellcheck="false" autofocus>
#             </div>
#             <div class="actions">
#                 <button class="btn" type="submit">Look up vehicle</button>
#             </div>
#         </form>

#         <form method="post" action="/scan" enctype="multipart/form-data" class="ocr">
#             <span>Have a photo of the plate?</span>
#             <input type="file" name="plate_image" accept="image/jpeg,image/png,image/heic" required>
#             <button class="btn" type="submit">Read plate from photo</button>
#         </form>
#     </div>
# </section>

# <div class="wrap filter">
#     <details {% if details %}open{% endif %}>
#         <summary>
#             Plate unclear? Narrow it down with other details
#             <span class="pill" id="count" hidden>0</span>
#             <i class="caret"></i>
#         </summary>
#         <div class="filter-body">
#             <p class="filter-note">Pick a value from each database or type your own. Use <b>?</b> for plate characters you
#                 can't read. Leave blank anything you don't know; the plate and every detail you fill in are combined to find
#                 the one registration that agrees with them.</p>
#             <div class="src-grid">
#             {% for sec in sections %}
#                 <section class="src src-{{ sec.key }}">
#                     <h3>{{ sec.title|replace(' DB', '') }}</h3>
#                     {% for field, label in sec.fields %}{{ pick(field, label) }}{% endfor %}
#                 </section>
#             {% endfor %}
#             </div>
#             <div class="filter-foot">
#                 <button class="btn" type="submit" form="lookup">Look up vehicle</button>
#                 <button class="btn btn--quiet" type="button" id="clear-details">Clear details</button>
#                 <span>Details from several databases make the match more certain.</span>
#             </div>
#         </div>
#     </details>
# </div>

# <main class="wrap">
#     {% if ocr_candidates %}
#         <div class="notice">
#             <strong>OCR readings &mdash; verify against the image:</strong>
#             <ul>
#             {% for item in ocr_candidates %}
#                 <li>{{ item.plate|fmt_plate }} &mdash; OCR confidence {{ '%.0f'|format(item.confidence * 100) }}%.
#                     <a href="/?plate={{ item.plate|urlencode }}">Search this reading</a></li>
#             {% endfor %}
#             </ul>
#         </div>
#     {% endif %}

#     {% if correction %}
#         <div class="notice{% if not correction.corrected or not correction.valid %} notice--warn{% endif %}">
#             <strong>Plate cleaning pipeline</strong>
#             <ul>
#                 <li>Step 1 &mdash; Original input: <code>{{ correction.original }}</code></li>
#                 <li>Step 2 &mdash; Normalized formatting: <code>{{ correction.cleaned }}</code></li>
#                 <li>Step 3 &mdash; Position-aware correction:
#                     {% if correction.corrected %}
#                         <code>{{ correction.corrected }}</code>
#                         {% if correction.changes %}
#                             <ul>
#                             {% for pos, old, new, kind in correction.changes %}
#                                 <li>Position {{ pos + 1 }}: <code>{{ old }}</code> &rarr;
#                                     <code>{{ new }}</code> (expected a {{ kind }})</li>
#                             {% endfor %}
#                             </ul>
#                         {% else %}
#                             (no character changes needed)
#                         {% endif %}
#                         {% if not correction.valid %}
#                             <br><em>Warning: state code <code>{{ correction.corrected[:2] }}</code>
#                             is not a known Indian state/UT code.</em>
#                         {% endif %}
#                     {% else %}
#                         could not fit the Indian plate pattern (LL DD L DDDD); inspect candidate matches below.
#                     {% endif %}
#                 </li>
#             </ul>
#             <em>The original value is preserved. Corrections are suggestions; nothing is written to the databases.</em>
#         </div>
#     {% endif %}

#     {% if identified_by %}
#         <div class="notice notice--ok">
#             <strong>Vehicle identified: {{ plate_resolved|fmt_plate }}.</strong>
#             Matched on {{ identified_by }}. Review the evidence before acting on it.
#         </div>
#     {% endif %}

#     {% if fuzzy_candidates %}
#         <section class="cands" aria-labelledby="cand-h">
#             <h2 id="cand-h">Fuzzy plate candidates</h2>
#             <p>Suggestions, not proof of identity.</p>
#             {% for item in fuzzy_candidates %}
#                 <div class="cand">
#                     <span class="plate plate--sm"><span class="plate-strip"><i class="chakra"></i>IND</span><span class="plate-chars">{{ item.plate|fmt_plate }}</span></span>
#                     <div class="score"><span>similarity {{ '%.1f'|format(item.score * 100) }}%</span>
#                         <span class="score-bar"><i style="width: {{ '%.0f'|format(item.score * 100) }}%"></i></span></div>
#                     <div class="chips">
#                     {% if details %}
#                         {% for field, v in (item.fields or {}).items() %}
#                             <span class="chip {{ v.status }} src-{{ field_source.get(field, '') }}"><b>{{ field_labels.get(field, field) }}</b> {{ v.stored or '—' }}<span class="mark">{% if v.status == 'match' %}✓{% elif v.status == 'mismatch' %}✗{% else %}~{% endif %}</span></span>
#                         {% endfor %}
#                     {% endif %}
#                     </div>
#                     <a class="btn btn--ghost btn--sm" href="/?plate={{ item.plate|urlencode }}&confirmed=1" style="text-decoration:none">Open this vehicle</a>
#                 </div>
#             {% endfor %}
#         </section>
#         {% if fuzzy_best and not fuzzy_auto %}
#             <div class="notice notice--warn">
#                 {{ decision_reason or 'No candidate passed both the similarity and ambiguity checks.' }}
#                 Please verify manually{% if details %} or add another detail{% endif %}.
#             </div>
#         {% endif %}
#     {% endif %}

#     {% if error_message %}
#         <div class="notice notice--bad">{{ error_message }}</div>
#     {% endif %}

#     {% if plate or details %}
#         {% if match_score is not none %}
#             <div class="notice">Selected registration similarity: {{ '%.1f'|format(match_score * 100) }}%.</div>
#         {% endif %}

#         {% if result and result.get('found') %}
#             {% if reported_count %}
#                 <div class="notice">{{ reported_count }} new flag(s) reported to the Ministry of Transport for this lookup.</div>
#             {% elif reported_count is none %}
#                 <div class="notice notice--warn">Ministry of Transport reporting is currently unavailable
#                     (mot_db unreachable). The lookup result below is unaffected.</div>
#             {% endif %}

#             {% set decision = result.get('decision', '') %}
#             {% set ts = result.get('trust_score', 0) or 0 %}
#             {% set ss = result.get('source_status', {}) %}
#             <article class="record">
#                 <div class="record-head">
#                     <span class="plate plate--md"><span class="plate-strip"><i class="chakra"></i>IND</span><span class="plate-chars">{{ (result.get('plate') or plate)|fmt_plate }}</span></span>
#                     <div class="record-title">
#                         <h2>{{ result.get('make') or '' }} {{ result.get('model') or '' }}</h2>
#                         <p>{{ result.get('color') or '' }}{% if result.get('color') and result.get('owner') %}, owned by {% elif result.get('owner') %}Owned by {% endif %}{{ result.get('owner') or '' }}</p>
#                     </div>
#                     {% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %}
#                         <span class="verdict verdict--bad">&#9888; {{ decision }}</span>
#                     {% elif decision == 'OK — INSURED AND CLEAR' %}
#                         <span class="verdict verdict--clear">CLEAR</span>
#                     {% else %}
#                         <span class="verdict verdict--flag">FLAGGED</span>
#                     {% endif %}
#                 </div>

#                 <div class="assess">
#                     <div>
#                         <div class="lbl">Trust Score</div>
#                         <div class="trust-num">{{ ts }}<small>/100</small></div>
#                         <div class="meter {{ '' if ts >= 80 else ('mid' if ts >= 50 else 'low') }}" role="img" aria-label="Trust score {{ ts }} out of 100"><i style="width: {{ ts }}%"></i></div>
#                     </div>
#                     <div>
#                         <div class="lbl">Decision</div>
#                         <p class="decision">{{ result.get('decision') }}</p>
#                         <div class="lbl">Flags</div>
#                         {% if result.get('flags') %}
#                             {% for flag in result['flags'] %}<span class="flag">{{ flag }}</span>{% endfor %}
#                         {% else %}
#                             <span class="noflag">No flags raised</span>
#                         {% endif %}
#                     </div>
#                 </div>

#                 <div class="panels">
#                     <section class="panel src-vehicles">
#                         <header><h3>Registration</h3></header>
#                         <dl>
#                             <dt>Make / Model</dt><dd>{{ result.get('make') or '—' }} {{ result.get('model') or '' }}</dd>
#                             <dt>Color</dt><dd>{{ result.get('color') or '—' }}</dd>
#                             <dt>Owner</dt><dd>{{ result.get('owner') or '—' }}</dd>
#                             <dt>Engine No.</dt><dd>{{ result.get('engine_no') or '—' }}</dd>
#                             <dt>Chassis No.</dt><dd>{{ result.get('chassis_no') or '—' }}</dd>
#                         </dl>
#                     </section>
#                     <section class="panel src-insurance">
#                         <header><h3>Insurance</h3></header>
#                         <dl>
#                             <dt>Insurer</dt><dd>{{ result.get('insurer') or '—' }}</dd>
#                             <dt>Policy No.</dt><dd>{{ result.get('policy_no') or '—' }}</dd>
#                             <dt>Policy Start</dt><dd>{{ result.get('policy_start_date') or '—' }}</dd>
#                             <dt>Policy End</dt><dd>{{ result.get('policy_end_date') or '—' }}</dd>
#                         </dl>
#                     </section>
#                     <section class="panel src-rto">
#                         <header><h3>RTO</h3></header>
#                         <dl>
#                             <dt>RTO Office</dt><dd>{{ result.get('rto_office') or '—' }}</dd>
#                             <dt>Registration Date</dt><dd>{{ result.get('registration_date') or '—' }}</dd>
#                             <dt>Renewal Date</dt><dd>{{ result.get('renewal_date') or '—' }}</dd>
#                         </dl>
#                     </section>
#                     <section class="panel src-theft{% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %} panel--alert{% endif %}">
#                         <header><h3>Theft record</h3></header>
#                         <dl>
#                             <dt>Theft Status</dt><dd>{{ result.get('theft_status') or '—' }}</dd>
#                             <dt>Theft Date</dt><dd>{{ result.get('theft_date') or '—' }}</dd>
#                             <dt>Shredded Date</dt><dd>{{ result.get('shredded_date') or '—' }}</dd>
#                         </dl>
#                     </section>
#                 </div>
#                 {{ status_box(ss) }}
#             </article>

#         {% else %}
#             <section class="record empty">
#                 <p class="empty-title">No registration confirmed</p>
#                 <p>{{ (result.get('message') if result else None) or 'No record found for this plate.' }}</p>
#                 {{ status_box(result.get('source_status') if result else None) }}
#             </section>
#         {% endif %}
#     {% endif %}

#     {% if not plate and not details and not ocr_candidates and not error_message %}
#         <section class="legend" aria-labelledby="legend-h">
#             <h2 id="legend-h">Where the answer comes from</h2>
#             <div class="legend-grid">
#                 <div class="src src-vehicles"><h3>Registration</h3><p>Make, model, color, owner, engine and chassis numbers.</p>
#                     {% set status = (health_status or {}).get('vehicles') %}
#                     {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
#                         {{ source_badge(status) }}
#                     </div>{% endif %}
#                 </div>
#                 <div class="src src-insurance"><h3>Insurance</h3><p>Insurer, policy number and policy start and end dates.</p>
#                     {% set status = (health_status or {}).get('insurance') %}
#                     {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
#                         {{ source_badge(status) }}
#                     </div>{% endif %}
#                 </div>
#                 <div class="src src-rto"><h3>RTO</h3><p>Registering office, registration date and renewal date.</p>
#                     {% set status = (health_status or {}).get('rto') %}
#                     {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
#                         {{ source_badge(status) }}
#                     </div>{% endif %}
#                 </div>
#                 <div class="src src-theft"><h3>Theft record</h3><p>Whether the vehicle was stolen, recovered or shredded, and when.</p>
#                     {% set status = (health_status or {}).get('theft') %}
#                     {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
#                         {{ source_badge(status) }}
#                     </div>{% endif %}
#                 </div>
#             </div>
#         </section>
#     {% endif %}
# </main>

# <script>
# (function () {
#     var MODELS = {{ (model_by_make or {})|tojson }};
#     var ALL_MODELS = {{ (field_options.get('model') or [])|tojson }};
#     var $ = function (s, r) { return (r || document).querySelector(s); };
#     var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

#     function updateCount() {
#         var n = $$('.src-grid input[type=text]').filter(function (i) { return i.value.trim() !== ''; }).length;
#         var pill = $('#count');
#         pill.textContent = n + (n === 1 ? ' detail' : ' details');
#         pill.hidden = n === 0;
#     }

#     function buildOptions(sel, list, cur, txt) {
#         while (sel.firstChild) sel.removeChild(sel.firstChild);
#         function add(value, label) {
#             var o = document.createElement('option');
#             o.value = value; o.textContent = label; sel.appendChild(o);
#         }
#         add('', 'Any');
#         list.forEach(function (v) { add(v, v); });
#         add('__other', 'Other, type it\u2026');
#         if (cur && list.indexOf(cur) > -1) { sel.value = cur; txt.hidden = true; }
#         else if (cur) { sel.value = '__other'; txt.hidden = false; }
#         else { sel.value = ''; txt.hidden = true; }
#     }

#     function refreshModels() {
#         var p = $('.pick[data-field="model"]');
#         if (!p) return;
#         var sel = $('.pick-sel', p), txt = $('.pick-txt', p);
#         var makeEl = $('#f_make');
#         var make = makeEl ? makeEl.value.trim().toLowerCase() : '';
#         var key = Object.keys(MODELS).filter(function (k) { return k.toLowerCase() === make; })[0];
#         var list = key ? MODELS[key] : ALL_MODELS;
#         var cur = txt.value;
#         if (key && cur && list.indexOf(cur) === -1) { cur = ''; txt.value = ''; }
#         buildOptions(sel, list, cur, txt);
#     }

#     $$('.pick').forEach(function (p) {
#         var sel = $('.pick-sel', p), txt = $('.pick-txt', p), field = p.getAttribute('data-field');
#         sel.addEventListener('change', function () {
#             if (sel.value === '__other') { txt.hidden = false; txt.value = ''; txt.focus(); }
#             else { txt.hidden = true; txt.value = sel.value; }
#             if (field === 'make') refreshModels();
#             updateCount();
#         });
#         txt.addEventListener('input', function () {
#             if (field === 'make') refreshModels();
#             updateCount();
#         });
#     });
#     $$('.src-grid input[type=text]').forEach(function (i) { i.addEventListener('input', updateCount); });

#     $('#clear-details').addEventListener('click', function () {
#         $$('.src-grid input[type=text]').forEach(function (i) { i.value = ''; });
#         $$('.pick').forEach(function (p) { $('.pick-sel', p).value = ''; $('.pick-txt', p).hidden = true; });
#         refreshModels();
#         updateCount();
#     });

#     refreshModels();
#     updateCount();
# })();
# </script>
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


# def _rank_plate_candidates(query, limit=FUZZY_TOP_K):
#     """Compare the query with live plate identifiers discovered from sources."""
#     query_key = normalize_plate(query) or ""
#     if not query_key:
#         return []

#     scores = {}
#     for raw_plate in list_candidate_plates():
#         canonical = normalize_plate(raw_plate)
#         if not canonical:
#             continue
#         score = plate_similarity(query_key, canonical)
#         if canonical not in scores or score > scores[canonical]:
#             scores[canonical] = score

#     return [
#         {"plate": plate, "score": score}
#         for plate, score in sorted(
#             scores.items(), key=lambda item: (-item[1], item[0])
#         )[:limit]
#     ]


# def _fuzzy_decision(candidates):
#     """Auto-select only a strong, unambiguous candidate; otherwise review."""
#     if not candidates:
#         return None, False
#     best_score = candidates[0]["score"]
#     second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
#     safe = (
#         best_score >= FUZZY_MIN_SCORE
#         and best_score - second_score >= FUZZY_MIN_MARGIN
#     )
#     return candidates[0]["plate"], safe


# _OPTIONS_TTL = 300      # seconds to reuse the dropdown values
# _OUTAGE_TTL = 30        # shorter reuse while the live sources are unreachable
# _options_cache = {"at": 0.0, "ttl": 0, "data": {}, "models": {}}
# STATIC_OPTIONS = {
#     "policy_status": ["Active", "Expired", "No policy"],
#     "renewal_status": ["Valid", "Lapsed", "No RTO record"],
#     "theft_status": ["Stolen", "Recovered", "Shredded", "No theft record"],
# }
# OPTION_FIELDS = ("make", "model", "color", "owner_name", "insurer_name",
#                  "rto_office", "registration_year", "theft_year")

# # Where the project's CSV dataset lives (repo-root /data, or coordinator/data).
# _HERE = Path(__file__).resolve().parent
# DATA_DIRS = (_HERE.parent / "data", _HERE / "data")


# def _read_dataset(filename):
#     for folder in DATA_DIRS:
#         path = folder / filename
#         if path.is_file():
#             try:
#                 with path.open(newline="", encoding="utf-8-sig") as handle:
#                     return list(csv.DictReader(handle))
#             except Exception as exc:
#                 print(f"[app] could not read {path}: {exc}")
#     return []


# def _clean_value(value):
#     text = str(value or "").strip()
#     return "" if not text or text.startswith("No ") else text


# @lru_cache(maxsize=1)
# def _dataset_options():
#     """Dropdown values taken from the project's CSV dataset.

#     Returns (options_by_field, models_by_make). These work even when the
#     live databases are down, so the filter always has real choices.
#     """
#     vehicles = _read_dataset("laptop1_vehicle_registration.csv")
#     insurance = _read_dataset("laptop2_insurance.csv")
#     rto = _read_dataset("laptop3_rto.csv")
#     theft = _read_dataset("laptop4_theft_shredding.csv")

#     values = {field: set() for field in OPTION_FIELDS}
#     models_by_make = {}
#     for row in vehicles:
#         for field in ("make", "model", "color", "owner_name"):
#             if _clean_value(row.get(field)):
#                 values[field].add(_clean_value(row[field]))
#         make, model = _clean_value(row.get("make")), _clean_value(row.get("model"))
#         if make and model:
#             models_by_make.setdefault(make, set()).add(model)
#     for row in insurance:
#         if _clean_value(row.get("insurer_name")):
#             values["insurer_name"].add(_clean_value(row["insurer_name"]))
#     for row in rto:
#         if _clean_value(row.get("rto_office")):
#             values["rto_office"].add(_clean_value(row["rto_office"]))
#         year = str(row.get("registration_date") or "")[:4]
#         if year.isdigit():
#             values["registration_year"].add(year)
#     for row in theft:
#         year = str(row.get("theft_date") or "")[:4]
#         if year.isdigit():
#             values["theft_year"].add(year)
#     return values, models_by_make


# def _field_options():
#     """Dropdown values per field: CSV dataset merged with the live sources.

#     Only distinct *values* are cached (never vehicle rows). Returns
#     (options_by_field, models_by_make).
#     """
#     now = time.time()
#     if _options_cache["data"] and now - _options_cache["at"] < _options_cache["ttl"]:
#         return _options_cache["data"], _options_cache["models"]

#     dataset_values, dataset_models = _dataset_options()
#     merged = {field: set(vals) for field, vals in dataset_values.items()}
#     models_by_make = {make: set(models) for make, models in dataset_models.items()}

#     try:
#         profiles = list_vehicle_profiles()
#     except Exception:
#         profiles = []
#     for profile in profiles:
#         for field in OPTION_FIELDS:
#             if _clean_value(profile.get(field)):
#                 merged[field].add(_clean_value(profile[field]))
#         make, model = _clean_value(profile.get("make")), _clean_value(profile.get("model"))
#         if make and model:
#             models_by_make.setdefault(make, set()).add(model)

#     options = {k: list(v) for k, v in STATIC_OPTIONS.items()}
#     for field, vals in merged.items():
#         if vals:
#             options[field] = sorted(vals, key=str.casefold)
#     models = {make: sorted(vals, key=str.casefold)
#               for make, vals in sorted(models_by_make.items(), key=lambda kv: kv[0].casefold())}

#     _options_cache.update(
#         at=now, data=options, models=models,
#         ttl=_OPTIONS_TTL if profiles else _OUTAGE_TTL,
#     )
#     return options, models


# @app.context_processor
# def _inject_form_data():
#     options, models = _field_options()
#     return {"sections": SECTIONS, "field_options": options,
#             "model_by_make": models, "field_labels": DETAIL_LABELS,
#             "field_source": {f: sec["key"] for sec in SECTIONS
#                              for f, _label in sec["fields"]}}


# @app.context_processor
# def _inject_theme():
#     """Shared stylesheet, fonts and app bar for every page (presentation only)."""
#     return {"theme_css": THEME_CSS, "font_links": FONT_LINKS, "appbar": appbar}


# _PLATE_RE = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{1,4})$")


# @app.template_filter("fmt_plate")
# def _fmt_plate(value):
#     """DL01AB1234 -> 'DL 01 AB 1234' (display only)."""
#     text = re.sub(r"[\s.-]", "", str(value or "")).upper()
#     match = _PLATE_RE.match(text)
#     return " ".join(match.groups()) if match else text


# def _read_details(source):
#     """Optional operator-supplied details (make/model/color/owner/engine/chassis)."""
#     return {
#         field: (source.get(field) or "").strip()[:60]
#         for field in DETAIL_FIELDS
#         if (source.get(field) or "").strip()
#     }


# def _rank_unified(query, details, limit=FUZZY_TOP_K):
#     """Rank registrations by plate alone, or plate + details when provided.

#     Returns (candidates, best_plate, auto_ok, reason, used_details).
#     """
#     if details:
#         rows = list_vehicle_profiles()
#         if rows:
#             ranked = rank_with_details(
#                 normalize_plate(query) or "", details, rows, limit
#             )
#             best, auto, reason = decide(ranked, used_details=True)
#             return ranked, best, auto, reason, True
#         # Registration DB unreachable: fall back to plate-only ranking.
#     candidates = _rank_plate_candidates(query, limit)
#     best, auto = _fuzzy_decision(candidates)
#     return candidates, best, auto, None, False


# def _plate_correction(plate):
#     """Position-aware correction for a typed/OCR plate, or None when not applicable.

#     Skipped when the operator used '?' for unreadable characters: that wildcard
#     is handled by the fuzzy matcher, and correct_plate() would turn it into 7/T.
#     """
#     if not plate or "?" in plate:
#         return None
#     return correct_plate(plate)


# def _describe_evidence(candidate):
#     fields = [f for f, v in (candidate.get("fields") or {}).items()
#               if v["status"] == "match"]
#     return "plate + " + ", ".join(
#         DETAIL_LABELS.get(f, f) for f in fields
#     ) if fields else "plate"


# @app.route("/", methods=["GET"])
# def home():
#     plate = request.args.get("plate", "").strip()
#     confirmed = request.args.get("confirmed") == "1"
#     result = None
#     reported_count = 0
#     ocr_candidates = []
#     fuzzy_candidates = []
#     fuzzy_best = None
#     fuzzy_auto = False
#     match_score = None
#     error_message = None
#     resolved_plate = plate
#     details = _read_details(request.args)
#     decision_reason = None
#     identified_by = None
#     health_status = check_source_status() if not plate and not details else {}
#     correction = None

#     try:
#         if plate or details:
#             # Keep the typed plate; rank against the position-corrected form when one exists.
#             correction = _plate_correction(plate)
#             search_key = (correction or {}).get("corrected") or plate

#             fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
#                 _rank_unified(search_key, details)
#             )

#             top = fuzzy_candidates[0] if fuzzy_candidates else None
#             exact = bool(
#                 top
#                 and plate
#                 and normalize_plate(top["plate"]) == normalize_plate(search_key)
#                 and top.get("plate_score", top["score"]) >= 0.999
#                 and not any(v["status"] == "mismatch"
#                             for v in (top.get("fields") or {}).values())
#             )

#             # Never silently replace a typed plate with a fuzzy guess.
#             # Exact plate or explicit user selection may run the full federated lookup.
#             if exact:
#                 resolved_plate = fuzzy_candidates[0]["plate"]
#                 match_score = 1.0
#                 result = query_vehicle(resolved_plate)
#             elif confirmed:
#                 selected = normalize_plate(plate)
#                 result = query_vehicle(selected)
#                 resolved_plate = selected
#                 match_score = 1.0
#             elif fuzzy_auto:
#                 resolved_plate = fuzzy_best
#                 match_score = fuzzy_candidates[0]["score"]
#                 result = query_vehicle(resolved_plate)
#                 if used:
#                     identified_by = _describe_evidence(fuzzy_candidates[0])
#             else:
#                 # Keep the raw query visible and ask the user to select a candidate.
#                 result = {
#                     "plate": plate,
#                     "found": False,
#                     "message": (
#                         "No exact registration was confirmed. Review the "
#                         "candidates above and select the correct plate."
#                     ),
#                 }

#             # Reporting is only triggered for an exact match of the plate AS TYPED, or an
#             # explicit selection. A corrected or fuzzy guess is displayed, never written back.
#             typed_exact = exact and normalize_plate(search_key) == normalize_plate(plate)
#             if result and result.get("found") and (typed_exact or confirmed):
#                 reported_count = report_flags(result, reported_by="live-lookup-ui")

#     except Exception as exc:
#         print(f"[app] lookup failed for plate={plate!r}: {exc}")
#         error_message = (
#             "Could not complete the lookup. Check source availability and try again."
#         )

#     return render_template_string(
#         TEMPLATE,
#         plate=plate,
#         result=result,
#         reported_count=reported_count,
#         ocr_candidates=ocr_candidates,
#         fuzzy_candidates=fuzzy_candidates,
#         fuzzy_best=fuzzy_best,
#         fuzzy_auto=fuzzy_auto,
#         match_score=match_score,
#         error_message=error_message,
#         details=details,
#         decision_reason=decision_reason,
#         identified_by=identified_by,
#         plate_resolved=resolved_plate,
#         health_status=health_status,
#         correction=correction,
#     )


# @app.route("/scan", methods=["POST"])
# def scan_plate_image():
#     upload = request.files.get("plate_image")
#     if upload is None or not upload.filename:
#         return render_template_string(
#             TEMPLATE, plate="", result=None, reported_count=0,
#             ocr_candidates=[], fuzzy_candidates=[], fuzzy_best=None,
#             fuzzy_auto=False, match_score=None,
#             error_message="Choose an image of a registration plate first.",
#         ), 400

#     try:
#         # recognize_plate_image validates file signature/size and returns ranked OCR readings.
#         ocr_candidates = recognize_plate_image(upload)
#         if not ocr_candidates:
#             raise PlateOCRInputError(
#                 "No plausible registration plate text was found. Try a clearer image."
#             )

#         # Use the best OCR reading as the search query; do not report/write flags here.
#         query = ocr_candidates[0]["plate"]
#         details = _read_details(request.form)
#         # Best OCR reading -> position-aware correction -> fuzzy ranking.
#         correction = _plate_correction(query)
#         search_key = (correction or {}).get("corrected") or query
#         fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
#             _rank_unified(search_key, details)
#         )

#         # Only run Vehicle 360 automatically when the best fuzzy match is strong
#         # and sufficiently separated from the runner-up. Otherwise show suggestions.
#         result = None
#         match_score = None
#         identified_by = None
#         if fuzzy_auto:
#             result = query_vehicle(fuzzy_best)
#             match_score = fuzzy_candidates[0]["score"]
#             if used:
#                 identified_by = _describe_evidence(fuzzy_candidates[0])
#         else:
#             result = {
#                 "plate": query,
#                 "found": False,
#                 "message": (
#                     "OCR completed, but no unique high-confidence registration "
#                     "match was found. Verify the image and select a candidate."
#                 ),
#             }

#         return render_template_string(
#             TEMPLATE,
#             plate=query,
#             result=result,
#             reported_count=0,
#             ocr_candidates=ocr_candidates,
#             fuzzy_candidates=fuzzy_candidates,
#             fuzzy_best=fuzzy_best,
#             fuzzy_auto=fuzzy_auto,
#             match_score=match_score,
#             error_message=None,
#             details=details,
#             decision_reason=decision_reason,
#             identified_by=identified_by,
#             plate_resolved=fuzzy_best,
#             correction=correction,
#         )

#     except PlateOCRInputError as exc:
#         message = str(exc)
#     except PlateOCREngineError as exc:
#         print(f"[app] OCR engine failed: {exc}")
#         message = "OCR could not run. Confirm PaddleOCR is installed on the Coordinator."
#     except Exception as exc:
#         print(f"[app] OCR/fuzzy lookup failed: {exc}")
#         message = "OCR or candidate matching failed. Check the Coordinator logs."

#     return render_template_string(
#         TEMPLATE,
#         plate="",
#         result=None,
#         reported_count=0,
#         ocr_candidates=[],
#         fuzzy_candidates=[],
#         fuzzy_best=None,
#         fuzzy_auto=False,
#         match_score=None,
#         error_message=message,
#     ), 400


# # =====================================================================
# # MERGED FROM FRIEND'S app.py: Data Cleaning Workbench (/cleaning)
# # Added as-is; nothing above this block was modified.
# # =====================================================================
# try:
#     from fuzzy_match import IDENTIFIER_PREFIXES, normalize_identifier
# except ImportError:
#     # Fallbacks: this project's fuzzy_match.py does not define these helpers.
#     # If your friend's fuzzy_match.py has them, copy his versions over these.
#     IDENTIFIER_PREFIXES = {"engine_no": "ENG", "chassis_no": "CH"}

#     def normalize_identifier(value, field):
#         """Strip the standard prefix (if present) to expose the serial payload."""
#         prefix = IDENTIFIER_PREFIXES.get(field, "")
#         value = str(value or "")
#         return value[len(prefix):] if prefix and value.startswith(prefix) else value

# CLEANING_TEMPLATE = r"""
# <!doctype html>
# <html lang="en">
# <head>
# <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
# <title>Data Cleaning Workbench</title>
# {{ font_links }}
# <style>
# {{ theme_css }}
# .muted{color:var(--muted)}.good{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
# .clean-hero{position:relative;overflow:hidden;margin-bottom:16px;padding:clamp(22px,4vw,32px);
#   border:1px solid rgba(255,255,255,.13);border-radius:18px;color:#fff;
#   background:linear-gradient(118deg,#123844 0%,#14515a 52%,#273c67 100%);
#   box-shadow:0 22px 50px -26px rgba(14,43,59,.48)}
# .clean-hero::after{content:"";position:absolute;right:-88px;top:-178px;width:300px;height:300px;
#   border:1px solid rgba(255,255,255,.14);border-radius:50%;box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025)}
# .clean-hero>*{position:relative;z-index:1}
# .clean-kicker{display:inline-flex;align-items:center;gap:8px;color:#c6eee5;font-size:10.5px;
#   font-weight:700;letter-spacing:.12em;text-transform:uppercase}
# .clean-kicker::before{content:"";width:7px;height:7px;border-radius:50%;background:#65e0ae;box-shadow:0 0 0 4px rgba(101,224,174,.15)}
# .clean-hero h1{margin:8px 0;font-size:clamp(26px,3.4vw,35px);font-weight:700;letter-spacing:-.035em;line-height:1.12}
# .clean-hero p{max-width:70ch;margin:0;color:#c0d7dc;font-size:13.5px;line-height:1.65}
# .clean-features{display:flex;flex-wrap:wrap;gap:8px;margin-top:17px}
# .clean-feature{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;color:#e2eff0;
#   background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:999px;font-size:10.5px;font-weight:600}
# .clean-feature::before{content:"";width:5px;height:5px;border-radius:50%;background:#ffc56b}
# .clean-card{overflow:hidden;margin-bottom:16px}
# .clean-card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line)}
# .clean-card-head h2{margin:0;font-size:14px;font-weight:650}
# .clean-card-head p{margin:3px 0 0;color:var(--muted);font-size:12px}
# .clean-form{display:grid;grid-template-columns:minmax(190px,.75fr) minmax(240px,1.5fr) auto;gap:14px;align-items:end;padding:20px}
# .clean-form .btn{min-height:38px}
# .clean-input-hint{margin:6px 0 0;color:var(--muted);font-size:11px}
# .clean-trace-head{align-items:flex-start}
# .clean-safe{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid var(--ok-line);
#   border-radius:999px;background:var(--ok-bg);color:var(--ok);font-size:10px;font-weight:700;white-space:nowrap}
# .clean-safe::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
# .clean-note{margin:0;padding:13px 20px;color:var(--ink-2);background:#f8faf9;border-bottom:1px solid var(--line);font-size:12px;line-height:1.6}
# .clean-steps{display:grid;gap:10px;padding:16px 20px}
# .clean-step{position:relative;padding:14px 15px 14px 48px;border:1px solid var(--line);border-radius:10px;
#   background:linear-gradient(145deg,#fff,#f8faf9);transition:border-color .16s,box-shadow .16s,transform .16s}
# .clean-step:hover{transform:translateY(-1px);border-color:var(--line-2);box-shadow:var(--sh-2)}
# .clean-step-index{position:absolute;left:14px;top:14px;display:grid;place-items:center;width:23px;height:23px;
#   border-radius:7px;background:var(--brand-50);border:1px solid var(--brand-100);color:var(--brand);font-size:10px;font-weight:750}
# .clean-step h3{margin:0 0 4px;font-size:12.5px;font-weight:650}
# .clean-step p{margin:0 0 8px;color:var(--ink-2);font-size:12px;line-height:1.55}
# .clean-step p:last-child{margin-bottom:0}
# .clean-value{padding:8px 10px;border:1px solid var(--line);border-radius:7px;background:#f3f6f5;color:var(--ink);
#   font:500 12px/1.5 var(--mono);overflow-wrap:anywhere}
# .clean-level{display:inline-flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;font-weight:600}
# .clean-level::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
# .clean-level.good{color:var(--ok)}.clean-level.warn{color:var(--warn)}.clean-level.bad{color:var(--bad)}.clean-level.muted{color:var(--muted)}
# .clean-candidates{padding:0 20px 16px}
# .clean-candidates h3{margin:0 0 9px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
# .clean-candidate{display:grid;grid-template-columns:minmax(0,1fr) minmax(100px,160px) 50px;align-items:center;gap:12px;
#   padding:9px 11px;border:1px solid var(--line);border-bottom:0;background:#fff}
# .clean-candidate:first-of-type{border-radius:9px 9px 0 0}
# .clean-candidate:last-child{border-bottom:1px solid var(--line);border-radius:0 0 9px 9px}
# .clean-candidate-value{min-width:0;font:500 12px var(--mono);overflow-wrap:anywhere}
# .clean-score-track{height:6px;overflow:hidden;border-radius:999px;background:#e8eeeb}
# .clean-score-fill{height:100%;border-radius:inherit;background:linear-gradient(90deg,#4d9d80,#4569bb)}
# .clean-candidate strong{color:var(--ink-2);font-size:11px;text-align:right;font-variant-numeric:tabular-nums}
# .clean-final{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:14px;
#   margin:0 20px 20px;padding:16px;border:1px solid var(--brand-100);border-radius:11px;
#   background:linear-gradient(120deg,#edf5f1,#eef1f8)}
# .clean-final-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:11px;
#   background:#fff;border:1px solid var(--brand-100);color:var(--brand);font-size:17px;font-weight:700}
# .clean-final h3{margin:0 0 5px;color:var(--brand);font-size:10px;font-weight:750;letter-spacing:.09em;text-transform:uppercase}
# .clean-final .clean-value{margin-bottom:6px;background:#fff;font-size:13px;font-weight:600}
# .clean-final p{margin:0;font-size:11.5px;font-weight:500;line-height:1.5}
# .clean-about{padding:17px 20px}
# .clean-about h2{margin:0 0 5px;font-size:13px;font-weight:650}
# .clean-about p{margin:0;color:var(--muted);font-size:12px;line-height:1.65}
# @media(max-width:720px){
#   .clean-form{grid-template-columns:1fr;padding:16px}
#   .clean-form .btn{width:100%}
#   .clean-card-head{padding:14px 16px}
#   .clean-safe{white-space:normal}
#   .clean-note{padding:12px 16px}
#   .clean-steps{padding:13px 15px}
#   .clean-candidates{padding:0 15px 14px}
#   .clean-candidate{grid-template-columns:minmax(0,1fr) 44px;gap:6px 10px}
#   .clean-score-track{grid-column:1;grid-row:2}
#   .clean-candidate strong{grid-column:2;grid-row:1 / span 2}
#   .clean-final{margin:0 15px 15px;padding:13px;gap:10px}
# }
# </style></head><body class="ui">
# {{ appbar('cleaning') }}
# <main class="wrap page">
# <section class="clean-hero">
# <span class="clean-kicker">Transparent data preparation</span>
# <h1>Data Cleaning Workbench</h1>
# <p>Inspect how a value is normalized, validated, and compared with known records. Suggestions are shown for review—your input is never silently rewritten or saved.</p>
# <div class="clean-features"><span class="clean-feature">Formatting trace</span><span class="clean-feature">Validation checks</span><span class="clean-feature">Evidence-based suggestions</span></div>
# </section>
# <section class="card clean-card">
# <div class="clean-card-head"><div><h2>Inspect a value</h2><p>Choose a field and enter the value you want to review.</p></div></div>
# <form method="post" action="/cleaning" class="clean-form">
# <div><label for="field">Field to inspect</label><select id="field" name="field">
# {% for key,label in fields %}<option value="{{ key }}" {% if selected_field==key %}selected{% endif %}>{{ label }} ({{ key }})</option>{% endfor %}
# </select></div>
# <div><label for="raw">Input value</label><input id="raw" name="raw" value="{{ raw }}" placeholder="e.g. DL 01 AB 1002" autocomplete="off" required><p class="clean-input-hint">Your value is inspected only; no database changes are made.</p></div>
# <button class="btn" type="submit">Inspect value <span aria-hidden="true">&rarr;</span></button></form></section>
# {% if result %}<section class="card clean-card" aria-labelledby="trace-title">
# <div class="clean-card-head clean-trace-head"><div><h2 id="trace-title">Cleaning trace</h2><p>{{ selected_label }} · {{ result.steps|length }} processing steps</p></div><span class="clean-safe">No changes saved</span></div>
# <p class="clean-note">The original input is preserved. Any suggested correction is based on available matching evidence and should be reviewed before use.</p>
# <div class="clean-steps">
# {% for step in result.steps %}<article class="clean-step"><span class="clean-step-index" aria-hidden="true">{{ '%02d'|format(loop.index) }}</span><h3>{{ step.title }}</h3><p>{{ step.description }}</p>{% if step.value is not none %}<div class="clean-value">{{ step.value if step.value else '(empty)' }}</div>{% endif %}{% if step.note %}<p class="clean-level {{ step.level or 'muted' }}">{{ step.note }}</p>{% endif %}</article>{% endfor %}
# </div>
# {% if result.candidates %}<div class="clean-candidates"><h3>Closest known values</h3>{% for c in result.candidates %}<div class="clean-candidate"><span class="clean-candidate-value">{{ c.value }}</span><span class="clean-score-track" aria-hidden="true"><span class="clean-score-fill" style="display:block;width:{{ '%.1f'|format(c.score*100) }}%"></span></span><strong>{{ '%.1f'|format(c.score*100) }}%</strong></div>{% endfor %}</div>{% endif %}
# <div class="clean-final"><span class="clean-final-mark" aria-hidden="true">&rarr;</span><div><h3>Suggested output</h3><div class="clean-value">{{ result.output or '(empty)' }}</div><p class="{{ result.level }}">{{ result.status }}</p></div></div>
# </section>{% endif %}
# <section class="card clean-about"><h2>How the workbench handles data</h2><p>Registration plates use normalization and OCR-aware similarity matching. Engine and chassis identifiers use prefix and formatting checks, while model values are compared with known records when available. Ambiguous matches stay suggestions for manual review—no value is automatically written back to the databases.</p></section>
# </main></body></html>
# """

# CLEANING_FIELDS = [
#     ("reg_plate", "Registration plate"),
#     ("engine_no", "Engine number"),
#     ("chassis_no", "Chassis number"),
#     ("model", "Vehicle model"),
# ]


# def _cleaning_normalize(field, raw):
#     """Formatting-only normalization. Does not guess character corrections."""
#     import re
#     value = str(raw or "").strip()
#     if field in ("reg_plate", "engine_no", "chassis_no"):
#         return re.sub(r"[\s.-]", "", value.upper())
#     if field == "model":
#         return re.sub(r"\s+", " ", value).strip().title()
#     return value


# def _cleaning_candidates(field, normalized, limit=5):
#     """Fetch known candidate values via existing mediator lookups where possible."""
#     from difflib import SequenceMatcher
#     candidates = []
#     try:
#         plates = list_candidate_plates() or []
#     except Exception:
#         plates = []
#     if field == "reg_plate":
#         for plate in plates:
#             canonical = normalize_plate(plate)
#             if canonical:
#                 score = plate_similarity(normalized, canonical)
#                 candidates.append({"value": canonical, "score": float(score)})
#     else:
#         # query_vehicle exposes the vehicle fields used by the existing lookup page.
#         # We only use values that the mediator actually returns; no values are fabricated.
#         seen = set()
#         for plate in plates:
#             try:
#                 record = query_vehicle(plate)
#             except Exception:
#                 continue
#             if not isinstance(record, dict) or not record.get("found"):
#                 continue
#             key_map = {"model": "model", "engine_no": "engine_no", "chassis_no": "chassis_no"}
#             value = str(record.get(key_map[field]) or "").strip()
#             if not value:
#                 continue
#             normalized_candidate = _cleaning_normalize(field, value)
#             if normalized_candidate in seen:
#                 continue
#             seen.add(normalized_candidate)
#             score = SequenceMatcher(None, normalized.casefold(), normalized_candidate.casefold(), autojunk=False).ratio()
#             candidates.append({"value": value, "score": score})
#     candidates.sort(key=lambda item: (-item["score"], item["value"]))
#     return candidates[:limit]


# def _build_cleaning_trace(field, raw):
#     import re
#     original = str(raw or "")
#     normalized = _cleaning_normalize(field, original)
#     steps = [
#         {"title": "Original input", "description": "The value exactly as entered by the user; it is not overwritten.", "value": original, "note": "Source value preserved.", "level": "muted"},
#         {"title": "Normalize formatting", "description": "Remove spaces, hyphens and dots and standardize case for identifiers; collapse repeated spaces for model names.", "value": normalized, "note": "Formatting normalization is not the same as correcting an incorrect character.", "level": "good" if normalized != original else "muted"},
#     ]
#     candidates = _cleaning_candidates(field, normalized)
#     output = normalized
#     status = "Normalized only. No correction was made automatically."
#     level = "warn"
#     if field == "reg_plate":
#         valid = bool(re.fullmatch(r"[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}", normalized))
#         steps.append({"title": "Plate-format validation", "description": "Check the normalized value against the expected Indian registration-plate pattern.", "value": normalized, "note": "Format looks valid." if valid else "Format does not match the expected pattern; inspect candidate matches below.", "level": "good" if valid else "warn"})
#         if candidates:
#             best = candidates[0]
#             margin = best["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0.0)
#             clear = best["score"] >= 0.82 and margin >= 0.05
#             steps.append({"title": "Registered-plate matching", "description": "Rank known registration plates with the project's OCR-aware plate similarity function.", "value": best["value"], "note": f"Best candidate similarity: {best['score']:.1%}. " + ("The candidate is a strong suggestion, but should still be confirmed." if clear else "The match is weak or ambiguous; manual review is required."), "level": "good" if clear else "warn"})
#             if clear and best["value"] != normalized:
#                 output = best["value"]
#                 status = "Strong candidate suggested; confirm before using it."
#                 level = "good"
#             elif best["value"] == normalized:
#                 output = best["value"]
#                 status = "Exact registered plate match."
#                 level = "good"
#             else:
#                 status = "No unique high-confidence correction. Original normalized value retained for review."
#         else:
#             steps.append({"title": "Registered-plate matching", "description": "Compare against known registered plates.", "value": None, "note": "No candidate values were available from the mediator.", "level": "warn"})
#     elif field in ("engine_no", "chassis_no"):
#         prefix = IDENTIFIER_PREFIXES.get(field, "")
#         identifier = normalize_identifier(normalized, field)
#         has_prefix = normalized.startswith(prefix)
#         steps.append({"title": "Identifier prefix and payload", "description": f"Expected standard prefix: {prefix}. The prefix is separated from the serial payload for comparison.", "value": identifier, "note": "Standard prefix present." if has_prefix else f"Prefix {prefix} is missing or not in the expected position; this is not enough evidence by itself to rebuild the identifier.", "level": "good" if has_prefix else "warn"})
#         if candidates:
#             best = candidates[0]
#             steps.append({"title": "Compare with registered identifiers", "description": "Compare the input with identifier values actually returned by the mediator, when that field is exposed.", "value": best["value"], "note": f"Best text similarity: {best['score']:.1%}. Treat this as a suggestion, not proof of identity.", "level": "good" if best["score"] >= 0.9 else "warn"})
#             if best["score"] >= 0.9:
#                 output = best["value"]
#                 status = "High-similarity candidate suggested; verify cross-field consistency before acceptance."
#                 level = "good"
#             else:
#                 status = "No sufficiently strong identifier match; manual review required."
#         else:
#             steps.append({"title": "Cross-field consistency", "description": "A safe repair may require engine/chassis relationships learned from registry records.", "value": None, "note": "The mediator did not expose candidate identifiers for this field, so no correction is guessed.", "level": "warn"})
#     elif field == "model":
#         if candidates:
#             best = candidates[0]
#             margin = best["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0.0)
#             clear = best["score"] >= 0.78 and margin >= 0.05
#             steps.append({"title": "Known-model fuzzy matching", "description": "Compare the normalized input with model names returned by vehicle records.", "value": best["value"], "note": f"Best similarity: {best['score']:.1%}. " + ("Unique high-confidence suggestion." if clear else "Low-confidence or ambiguous match; review required."), "level": "good" if clear else "warn"})
#             if clear:
#                 output = best["value"]
#                 status = "Known-model suggestion found; confirm before acceptance."
#                 level = "good"
#             else:
#                 status = "No unique high-confidence model correction; normalized value retained."
#         else:
#             steps.append({"title": "Known-model matching", "description": "Compare against models exposed by the existing mediator lookup.", "value": None, "note": "No known model values were available, so no correction is guessed.", "level": "warn"})
#     return {"steps": steps, "candidates": candidates, "output": output, "status": status, "level": level}


# @app.route("/cleaning", methods=["GET", "POST"])
# def data_cleaning_workbench():
#     selected_field = request.values.get("field", "reg_plate")
#     if selected_field not in {field for field, _label in CLEANING_FIELDS}:
#         selected_field = "reg_plate"
#     raw = request.values.get("raw", "")
#     result = _build_cleaning_trace(selected_field, raw) if request.method == "POST" and raw.strip() else None
#     return render_template_string(CLEANING_TEMPLATE, fields=CLEANING_FIELDS,
#                                   selected_field=selected_field,
#                                   selected_label=dict(CLEANING_FIELDS)[selected_field],
#                                   raw=raw, result=result)


# @app.errorhandler(413)
# def upload_too_large(_error):
#     return render_template_string(
#         TEMPLATE, plate="", result=None, reported_count=0,
#         ocr_candidates=[], fuzzy_candidates=[], fuzzy_best=None,
#         fuzzy_auto=False, match_score=None,
#         error_message="Image upload is too large. Maximum allowed size is 8 MB.",
#     ), 413


# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)



FUZZY_MIN_SCORE = 0.60
FUZZY_MIN_MARGIN = 0.07
FUZZY_TOP_K = 5

from flask import Flask, request, render_template_string, redirect, url_for
from werkzeug.utils import secure_filename

import csv
import re
import time
from functools import lru_cache
from pathlib import Path

from mediator import (query_vehicle, list_candidate_plates, normalize_plate,
                      list_vehicle_profiles, check_source_status)
from fuzzy_match import plate_similarity
from detail_match import (rank_with_details, decide, DETAIL_FIELDS,
                          SECTIONS, DETAIL_LABELS)
from plate_ocr import (recognize_plate_image, MAX_IMAGE_BYTES,
                       PlateOCRInputError, PlateOCREngineError)
from reporting import report_flags
from sql_console import sql_bp          # <-- NEW: federated SQL console
from ui_theme import THEME_CSS, FONT_LINKS, appbar   # shared look & feel
from plate_correct import correct_plate  # position-aware plate correction

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_IMAGE_BYTES + 1024 * 1024
app.register_blueprint(sql_bp)          # <-- NEW: adds /sql and /sql/run

TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Federated Vehicle Lookup</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
{{ font_links }}
<style>
{{ theme_css }}
/* ===== Home: hero ===== */
.hero-wrap{padding-top:24px}
.hero-card{position:relative;overflow:hidden;border-radius:20px;padding:clamp(22px,4vw,36px);color:#fff;
  background:linear-gradient(118deg,#123844 0%,#14515a 52%,#273c67 100%);
  border:1px solid rgba(255,255,255,.13);box-shadow:0 22px 50px -26px rgba(14,43,59,.55)}
.hero-card::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(520px 260px at 92% 3%,rgba(95,226,190,.18),transparent 68%),
  radial-gradient(440px 220px at 0% 120%,rgba(255,190,92,.16),transparent 68%)}
.hero-card>*{position:relative}
.hero-intro{display:grid;grid-template-columns:minmax(0,1fr) 250px;align-items:center;gap:28px}
.hero-copy{min-width:0}
.hero-kicker{display:inline-flex;align-items:center;gap:8px;margin:0 0 12px!important;
  color:#c6eee5!important;font-size:10.5px!important;font-weight:700;letter-spacing:.12em;
  text-transform:uppercase}
.hero-kicker::before{content:"";width:8px;height:8px;border-radius:50%;background:#65e0ae;
  box-shadow:0 0 0 5px rgba(101,224,174,.15)}
.hero h1,.hero-card h1{margin:0 0 9px;font-size:clamp(26px,3.2vw,36px);font-weight:700;
  letter-spacing:-.035em;line-height:1.12}
.hero-card p{margin:0 0 16px;color:#c0d7dc;font-size:13.5px;max-width:64ch;line-height:1.65}
.hero-meta{display:flex;flex-wrap:wrap;gap:7px}
.hero-meta span{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;
  color:#e2eff0;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);
  border-radius:999px;font-size:10.5px;font-weight:600}
.hero-meta span::before{content:"";width:6px;height:6px;border-radius:50%;background:#ffc56b}
.network-visual{width:100%;max-width:250px;justify-self:end;filter:drop-shadow(0 12px 20px rgba(5,22,32,.2))}
.network-visual svg{display:block;width:100%;height:auto;overflow:visible}
.network-visual .link{fill:none;stroke:rgba(211,239,236,.46);stroke-width:2;stroke-dasharray:4 5}
.network-visual .node{stroke:rgba(255,255,255,.8);stroke-width:2}
.network-visual .node-label{fill:#f4fbfa;font:600 10px var(--font);text-anchor:middle}
.network-visual .center-label{fill:#163d4a;font:700 9px var(--font);text-anchor:middle}
#lookup{display:flex;gap:10px;align-items:stretch}
#lookup .actions{display:flex;margin:0}
#lookup .btn{height:100%;min-height:54px;padding:0 23px;font-size:13.5px;
  background:linear-gradient(135deg,#ffe09b,#ffc76a);color:#303747;
  box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 8px 20px -9px rgba(0,0,0,.55);
  transition:transform .15s,filter .15s,box-shadow .15s}
#lookup .btn:hover{background:linear-gradient(135deg,#ffe7b1,#ffd17f);
  transform:translateY(-1px);box-shadow:0 10px 22px -9px rgba(0,0,0,.6)}

/* the plate */
.plate{flex:1;min-width:0;display:flex;align-items:stretch;background:#fff;color:#0d1b21;border:2px solid #0d1b21;border-radius:9px;overflow:hidden;
  box-shadow:inset 0 0 0 2px #fff,0 6px 18px -6px rgba(0,0,0,.5);transition:box-shadow .15s}
.plate:focus-within{box-shadow:inset 0 0 0 2px #fff,0 0 0 3px rgba(217,154,31,.65),0 6px 18px -6px rgba(0,0,0,.5)}
.plate-strip{background:linear-gradient(180deg,#3158c9,#25419a);color:#fff;width:40px;flex:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;font:700 .64rem var(--plate);letter-spacing:.09em}
.chakra{width:14px;height:14px;border:2px solid #fff;border-radius:50%;display:block;position:relative}
.chakra::after{content:"";position:absolute;inset:2px;border-radius:50%;border:1px dashed #fff}
.plate input[type=text]{flex:1;min-width:0;border:0;background:transparent;outline:none;box-shadow:none;border-radius:0;
  font:700 32px/1 var(--plate);letter-spacing:.09em;text-transform:uppercase;color:#0d1b21;padding:12px 16px;text-align:center}
.plate input[type=text]:hover,.plate input[type=text]:focus{border:0;box-shadow:none}
.plate input::placeholder{color:#b8c2c7;font-weight:600}
.plate-chars{font:700 26px/1 var(--plate);letter-spacing:.09em;padding:9px 18px;align-self:center}
.plate--sm{flex:none;border-width:1.5px;border-radius:6px;box-shadow:none;display:inline-flex}
.plate--sm .plate-strip{width:24px;font-size:.46rem;gap:2px}
.plate--sm .chakra{width:9px;height:9px;border-width:1.5px}
.plate--sm .chakra::after{display:none}
.plate--sm .plate-chars{font-size:18px;padding:4px 11px}
.plate--md{flex:none;box-shadow:none;border-color:#0d1b21}
.plate--md .plate-chars{font-size:28px;padding:8px 18px}

/* OCR row */
.ocr{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px;margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.12);color:#a9c4cd;font-size:12.5px}
.ocr input[type=file]{color:#c3d8df}
.ocr input[type=file]::file-selector-button{background:rgba(255,255,255,.08);color:#fff;border-color:rgba(255,255,255,.25)}
.ocr input[type=file]::file-selector-button:hover{background:rgba(255,255,255,.16)}
.ocr .btn{background:rgba(255,255,255,.1);color:#fff;border:1px solid rgba(255,255,255,.28);box-shadow:none;min-height:32px;padding:7px 13px;font-size:12.5px}
.ocr .btn:hover{background:rgba(255,255,255,.18)}
.ocr>span{color:#e0ebee;font-weight:600}

/* ===== Unclear-plate filter ===== */
.filter{margin-top:14px}
.filter>details{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:var(--sh-1);transition:box-shadow .2s}
.filter>details[open]{box-shadow:var(--sh-2)}
.filter summary{list-style:none;cursor:pointer;padding:12px 16px;display:flex;align-items:center;gap:10px;font-size:13.5px;font-weight:600;border-radius:var(--r-lg);transition:background .15s}
.filter summary:hover{background:var(--surface-2)}
.filter summary::-webkit-details-marker{display:none}
.filter summary .caret{margin-left:auto;width:7px;height:7px;border-right:1.6px solid var(--muted);border-bottom:1.6px solid var(--muted);transform:rotate(45deg) translateY(-2px);transition:transform .18s}
.filter details[open] .caret{transform:rotate(-135deg)}
.pill{background:var(--brand-50);color:var(--brand);border:1px solid var(--brand-100);font-size:11.5px;font-weight:600;padding:1px 9px;border-radius:999px}
.pill[hidden]{display:none}
.filter-body{padding:2px 16px 16px;border-top:1px solid var(--line)}
.filter-note{color:var(--muted);font-size:12.5px;margin:12px 0;max-width:70ch;line-height:1.55}
.filter-note b{color:var(--ink-2)}
.src-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.src{background:linear-gradient(155deg,#fff,var(--surface-2));border:1px solid var(--line);
  border-top:3px solid var(--c);border-radius:10px;padding:11px 12px 14px;min-width:0;
  transition:transform .16s,border-color .16s,box-shadow .16s}
.src:hover{transform:translateY(-2px);box-shadow:var(--sh-2)}
.src h3{display:flex;align-items:center;gap:7px;margin:0 0 2px;font-size:11px;font-weight:650;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2)}
.src h3::before{content:"";width:8px;height:8px;border-radius:3px;background:var(--c)}
.src-vehicles{--c:var(--c-vehicles)}.src-insurance{--c:var(--c-insurance)}.src-rto{--c:var(--c-rto)}.src-theft{--c:var(--c-theft)}
.fld{margin-top:10px}
.fld label{margin-bottom:4px;font-size:11.5px}
.fld select,.fld input[type=text]{min-height:34px;padding:6px 9px;font-size:13px;background-color:#fff}
.pick-txt{margin-top:6px}
.pick-txt[hidden]{display:none}
.filter-foot{display:flex;align-items:center;gap:10px;margin-top:16px;flex-wrap:wrap}
.filter-foot span{color:var(--muted);font-size:12px}

/* ===== Results ===== */
main.wrap{padding-top:22px;padding-bottom:56px}
.cands{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);margin:0 0 16px;overflow:hidden;box-shadow:var(--sh-1);animation:rise .25s ease both}
.cands h2{font-size:13.5px;font-weight:600;margin:0;padding:13px 18px 2px}
.cands>p{margin:0;padding:0 18px 11px;color:var(--muted);font-size:12px}
.cand{display:grid;grid-template-columns:auto 150px 1fr auto;gap:14px;align-items:center;padding:11px 18px;border-top:1px solid var(--line);transition:background .12s}
.cand:hover{background:#f7f9fb}
.score{font-weight:600;font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums}
.score-bar{display:block;margin-top:5px;height:5px;border-radius:99px;background:#e6ebef;overflow:hidden}
.score-bar i{display:block;height:100%;border-radius:99px;background:var(--brand);transform-origin:left;animation:grow .6s cubic-bezier(.2,.7,.2,1) both}
.chips{display:flex;flex-wrap:wrap;gap:5px;min-width:0}
.chip{font-size:11.5px;padding:2px 8px;border-radius:6px;border:1px solid var(--line);background:var(--surface-2);white-space:nowrap;color:var(--ink-2)}
.chip b{font-weight:600;color:var(--muted);margin-right:2px}
.chip.match{background:var(--ok-bg);border-color:var(--ok-line);color:#14583c}
.chip.partial{background:var(--warn-bg);border-color:var(--warn-line);color:#74480a}
.chip.mismatch{background:var(--bad-bg);border-color:var(--bad-line);color:#8d2d21}
.chip .mark{font-weight:700;margin-left:3px}
.chip[class*="src-"]{border-left:3px solid var(--c)}
.legend h2{font-size:13.5px;font-weight:600;margin:0 0 12px}
.legend-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.legend-grid .src{background:var(--surface);padding:14px;box-shadow:var(--sh-1);transition:box-shadow .2s,transform .2s,border-color .2s}
.legend-grid .src:hover{box-shadow:var(--sh-2);transform:translateY(-1px);border-color:var(--line-2)}
.legend-grid .src p{margin:6px 0 0;color:var(--muted);font-size:12.5px;line-height:1.5}
.legend-status{display:flex;align-items:center;justify-content:space-between;gap:8px;
  margin-top:12px;padding-top:9px;border-top:1px solid var(--line);font-size:11px}
.legend-status-label{color:var(--muted)}

.record{background:var(--surface);border:1px solid var(--line);border-radius:18px;overflow:hidden;
  box-shadow:0 16px 38px -24px rgba(17,44,61,.35);animation:rise .28s ease both}
.record-head{padding:22px 24px;display:flex;flex-wrap:wrap;align-items:center;gap:14px 20px;
  border-bottom:1px solid var(--line);background:linear-gradient(105deg,#fff 55%,#eef7f5)}
.record-title{flex:1;min-width:180px}
.record-title h2{margin:0;font-size:19px;font-weight:650;letter-spacing:-.015em;line-height:1.2}
.record-title p{margin:3px 0 0;color:var(--muted);font-size:12.5px}
.verdict{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;font-weight:650;letter-spacing:.06em;text-transform:uppercase;padding:6px 13px;border-radius:999px;border:1px solid}
.verdict--clear{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.verdict--flag{color:var(--warn);background:var(--warn-bg);border-color:var(--warn-line)}
.verdict--bad{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-line)}
.assess{padding:18px 22px;display:grid;grid-template-columns:1fr 1.5fr;gap:18px 40px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#fcfdfd,#f8fafb)}
.assess .lbl{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.trust-num{font-size:30px;font-weight:650;letter-spacing:-.03em;line-height:1;margin-bottom:10px;font-variant-numeric:tabular-nums}
.trust-num small{font-size:13px;color:var(--muted);font-weight:500;letter-spacing:0;margin-left:2px}
.decision{font-weight:600;font-size:14px;margin:0 0 12px;line-height:1.4}
.flag{display:inline-block;background:var(--bad-bg);color:#8d2d21;border:1px solid var(--bad-line);font-size:11.5px;font-weight:500;padding:2px 10px;border-radius:999px;margin:0 6px 6px 0}
.noflag{color:var(--muted);font-size:12.5px}
.panels{display:grid;grid-template-columns:repeat(4,1fr)}
.panel{position:relative;padding:19px 20px 20px;border-right:1px solid var(--line);
  min-width:0;transition:background .15s}
.panel::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--c)}
.panel:last-child{border-right:0}
.panel:hover{background:#fbfcfd}
.panel header{display:flex;align-items:center;gap:7px;margin-bottom:4px}
.panel header::before{content:"";width:8px;height:8px;border-radius:3px;background:var(--c)}
.panel h3{margin:0;font-size:11px;font-weight:650;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2)}
.panel dl{margin:0}
.panel dt{font-size:11.5px;color:var(--muted);margin-top:11px}
.panel dd{margin:1px 0 0;font-size:13.5px;font-weight:500;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.panel--alert{background:#fdf5f3}
.panel--alert:hover{background:#fdf5f3}
.empty{padding:22px;border-radius:14px}
.empty-title{font-size:15px;font-weight:600;margin:0 0 4px}
.empty p{margin:0;color:var(--muted);font-size:13px}
.status-box{padding:14px 22px 16px;border-top:1px solid var(--line);background:var(--surface-2)}
.empty .status-box{padding-left:0;padding-right:0;margin-top:14px;background:transparent}
.status-box h3{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.status-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:0 28px}
.status-item{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:12.5px;padding:7px 0;border-bottom:1px dashed var(--line-2)}
.st{display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border:1px solid transparent;
  border-radius:999px;font-weight:650;font-size:10.5px;letter-spacing:.04em;white-space:nowrap}
.st.ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-line)}
.st.down{color:var(--bad);background:var(--bad-bg);border-color:var(--bad-line)}

/* ===== Visual polish ===== */
.hero-card{padding:clamp(22px,4vw,34px);border-radius:18px}
.hero-kicker{display:inline-flex;align-items:center;gap:8px;margin:0 0 12px!important;
  color:#d9e8ec!important;font-size:10.5px!important;font-weight:650;letter-spacing:.1em;
  text-transform:uppercase}
.hero-kicker::before{content:"";width:7px;height:7px;border-radius:50%;background:#56d19a;
  box-shadow:0 0 0 4px rgba(86,209,154,.14)}
.hero-card h1{font-size:clamp(25px,3.4vw,34px);letter-spacing:-.035em}
.hero-card>p:not(.hero-kicker){font-size:14px;max-width:68ch}
.hero-meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.hero-meta span{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;
  color:#d3e1e5;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.13);
  border-radius:999px;font-size:11px;font-weight:550}
.hero-meta span::before{content:"";width:5px;height:5px;border-radius:50%;background:#e2b85b}
#lookup .btn{transition:transform .15s,background .15s,box-shadow .15s}
#lookup .btn:hover{transform:translateY(-1px);box-shadow:0 8px 20px -7px rgba(0,0,0,.55)}
.filter>details{overflow:hidden}
.filter summary{min-height:50px}
.filter summary:focus-visible{outline-offset:-3px}
.filter details[open] summary{border-radius:var(--r-lg) var(--r-lg) 0 0}
.src{transition:transform .16s,border-color .16s,box-shadow .16s}
.src:focus-within{border-color:var(--brand);box-shadow:var(--ring)}
.src-grid .src{border-top:3px solid var(--c);padding-top:10px}
.filter-foot{padding-top:2px}
.cands h2{font-size:15px;padding-top:16px}
.cand{min-height:70px}
.cand .btn{justify-self:end}
.record-head{background:linear-gradient(110deg,#fff 55%,#f6f9fa)}
.record-title h2{font-size:21px}
.assess{grid-template-columns:minmax(150px,.7fr) minmax(0,2fr)}
.panel{position:relative;padding-top:18px}
.panel::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--c);opacity:.72}
.panel--alert::before{background:var(--bad)}
.panel dd{line-height:1.45}
.status-box h3{display:flex;align-items:center;gap:8px}
.status-box h3::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--ok)}
.empty{border-left:4px solid var(--warn);background:linear-gradient(110deg,#fff,#fffdf8)}
.legend{padding:20px;background:rgba(255,255,255,.58);border:1px solid var(--line);
  border-radius:var(--r-lg)}
.legend h2{font-size:15px}

/* Bring the page background, navigation and content cards into one palette. */
body.ui{
  --surface:#f8fbf9;
  --surface-2:#edf4f1;
  --line:#d8e5df;
  --line-2:#c8d8d1;
  background:
    radial-gradient(ellipse at 8% 22%,rgba(77,157,128,.13),transparent 35%),
    radial-gradient(ellipse at 93% 48%,rgba(93,117,189,.11),transparent 38%),
    linear-gradient(145deg,#eaf2ee 0%,#e8eef2 52%,#f1eee6 100%);
  background-attachment:fixed;
}
.ui .appbar{
  background:rgba(235,244,240,.9);
  border-bottom-color:rgba(190,210,201,.8);
  box-shadow:0 4px 18px rgba(35,67,62,.05);
}
.ui .brand-mark{
  background:linear-gradient(145deg,#176451,#24477b);
}
.ui .filter>details,.ui .cands,.ui .record{
  background:linear-gradient(145deg,rgba(250,252,250,.97),rgba(240,247,244,.96));
  border-color:rgba(197,215,206,.9);
}
.ui .filter>details,.ui .cands{
  box-shadow:0 10px 28px -22px rgba(30,69,62,.42);
}
.ui .filter>details[open]{
  box-shadow:0 18px 38px -24px rgba(30,69,62,.45);
}
.ui .filter-body{
  background:linear-gradient(180deg,rgba(237,245,241,.78),rgba(248,251,249,.94));
}
.ui .src-grid .src{
  background:linear-gradient(150deg,#fbfdfb,#eef5f2);
  border-right-color:#d7e4de;
  border-bottom-color:#d7e4de;
  border-left-color:#d7e4de;
}
.ui .legend{
  background:linear-gradient(135deg,rgba(231,242,237,.94),rgba(236,239,247,.9));
  border-color:#d4e1dc;
  box-shadow:0 10px 30px -24px rgba(35,66,69,.42);
}
.ui .legend-grid .src{
  background:linear-gradient(155deg,#fbfdfb,#edf4f1);
  border-color:#d9e5df;
}
.ui .record-head{
  background:linear-gradient(105deg,#f9fcfa 15%,#e8f4ef 68%,#edf0f8);
}
.ui .assess{
  background:linear-gradient(105deg,#f0f6f3,#edf1f7);
}
.ui .panel{
  background:rgba(249,252,250,.7);
}
.ui .panel:nth-child(even){
  background:rgba(237,244,242,.68);
}
.ui .panel:hover{
  background:#f8fcfa;
}
.ui .panel--alert,.ui .panel--alert:hover{
  background:linear-gradient(140deg,#fbefec,#f9f4ef);
}
.ui .status-box{
  background:linear-gradient(100deg,#eaf3ef,#eef1f7);
}
.ui .empty{
  background:linear-gradient(120deg,#fbfcf8,#f5f0df);
}

/* ===== Plate cleaning trace (home page) ===== */
.trace code{font:500 12px var(--mono);background:rgba(0,0,0,.06);padding:1px 6px;border-radius:5px}
.trace ol{list-style:none;margin:8px 0;padding:0;display:grid;gap:7px}
.trace li.step{padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:rgba(255,255,255,.7);
  font-size:12.5px;line-height:1.55}
.trace li.step b{color:var(--ink-2)}
.trace ul{margin:6px 0 0 18px;padding:0}
.trace .alts{margin-top:6px;color:var(--muted)}

@media (max-width:980px){
  .hero-intro{grid-template-columns:minmax(0,1fr) 190px;gap:18px}
  .network-visual{max-width:190px}
  .src-grid,.legend-grid{grid-template-columns:1fr 1fr}
  .panels{grid-template-columns:1fr 1fr}
  .panel:nth-child(2){border-right:0}
  .panel:nth-child(-n+2){border-bottom:1px solid var(--line)}
  .cand{grid-template-columns:auto 130px 1fr}
  .cand .btn{grid-column:3;justify-self:start}
}
@media (max-width:680px){
  body.ui{background-attachment:scroll}
  .hero-card{padding:20px 16px 16px}
  .hero-intro{grid-template-columns:1fr;gap:8px}
  .network-visual{display:none}
  .hero-card h1{font-size:26px}
  .hero-meta{gap:6px}
  .hero-meta span{font-size:10.5px}
  #lookup{flex-direction:column}
  #lookup .btn{width:100%;min-height:44px}
  .plate input[type=text]{font-size:26px;padding:10px 8px;letter-spacing:.05em}
  .plate-strip{width:32px}
  .src-grid,.legend-grid,.panels,.assess{grid-template-columns:1fr}
  .panel{border-right:0;border-bottom:1px solid var(--line)}
  .panel:last-child{border-bottom:0}
  .cand{grid-template-columns:1fr;gap:8px}
  .cand .btn{grid-column:auto;justify-self:stretch}
  .filter-foot .btn{flex:1}
  .record-head{padding:16px}
  .assess{padding:16px;gap:18px}
  .status-box{padding-left:16px;padding-right:16px}
  .legend{padding:16px}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;
    animation-iteration-count:1!important;transition-duration:.01ms!important}
}
</style>
</head>
<body class="ui">

{% macro source_badge(status) -%}
{% if status.get('available') %}<span class="st ok">&#9679; Online</span>{% else %}<span class="st down">&#9679; Offline</span>{% endif %}
{%- endmacro %}

{% macro status_box(ss) -%}
{% if ss %}
<div class="status-box">
    <h3>Live Source Status</h3>
    <div class="status-list">
    {% for source, status in ss.items() %}
        <div class="status-item"><span>{{ source }}</span>
        {{ source_badge(status) }}</div>
    {% endfor %}
    </div>
</div>
{% endif %}
{%- endmacro %}

{% macro pick(field, label) -%}
{% set opts = field_options.get(field) or [] %}
{% set cur = (details or {}).get(field, '') %}
{% set custom = cur and (cur not in opts) %}
<div class="fld">
    <label for="{{ 's_' ~ field if opts else 'f_' ~ field }}">{{ label }}</label>
    {% if opts %}
    <div class="pick" data-field="{{ field }}">
        <select class="pick-sel" id="s_{{ field }}">
            <option value="">Any</option>
            {% for o in opts %}<option value="{{ o }}"{% if o == cur %} selected{% endif %}>{{ o }}</option>{% endfor %}
            <option value="__other"{% if custom %} selected{% endif %}>Other, type it&hellip;</option>
        </select>
        <input class="pick-txt" type="text" id="f_{{ field }}" name="{{ field }}" value="{{ cur }}"
               placeholder="Type {{ label|lower }}" autocomplete="off"{% if not custom %} hidden{% endif %}>
    </div>
    {% else %}
    <input type="text" id="f_{{ field }}" name="{{ field }}" value="{{ cur }}"
           placeholder="Type {{ label|lower }}" autocomplete="off">
    {% endif %}
</div>
{%- endmacro %}

{{ appbar('lookup') }}

<section class="wrap hero-wrap">
    <div class="hero-card hero">
        <div class="hero-intro">
            <div class="hero-copy">
                <p class="hero-kicker">Coordinator · Live federated search</p>
                <h1>Check any vehicle across four registries</h1>
                <p>Mediation / Federated Virtual Integration &mdash; live query across
                   independent vehicle, insurance, RTO and theft databases.
                   Plate lookup supports local PaddleOCR, position-aware character
                   correction and OCR-aware fuzzy suggestions.</p>
                <div class="hero-meta" aria-label="System characteristics">
                    <span>Queries source databases live</span>
                    <span>No central master copy</span>
                    <span>Four independent registries</span>
                </div>
            </div>
            <div class="network-visual" aria-hidden="true">
                <svg viewBox="0 0 250 180" role="presentation">
                    <path class="link" d="M125 91 51 38M125 91 199 38M125 91 51 144M125 91 199 144"/>
                    <circle cx="51" cy="38" r="22" fill="#4569d4" class="node"/>
                    <circle cx="199" cy="38" r="22" fill="#38ae82" class="node"/>
                    <circle cx="51" cy="144" r="22" fill="#a47ad2" class="node"/>
                    <circle cx="199" cy="144" r="22" fill="#e47d69" class="node"/>
                    <circle cx="125" cy="91" r="34" fill="#f7cf7c" class="node"/>
                    <text x="51" y="42" class="node-label">REG</text>
                    <text x="199" y="42" class="node-label">INS</text>
                    <text x="51" y="148" class="node-label">RTO</text>
                    <text x="199" y="148" class="node-label">THEFT</text>
                    <text x="125" y="88" class="center-label">LIVE</text>
                    <text x="125" y="101" class="center-label">MATCH</text>
                    <circle cx="125" cy="91" r="44" fill="none" stroke="rgba(255,255,255,.24)" stroke-width="1" stroke-dasharray="2 6"/>
                </svg>
            </div>
        </div>

        <form method="get" action="/" id="lookup" autocomplete="off">
            <div class="plate">
                <span class="plate-strip"><i class="chakra"></i>IND</span>
                <input type="text" name="plate" value="{{ plate or '' }}" placeholder="DL 01 AB 1234"
                       aria-label="Vehicle plate" spellcheck="false" autofocus>
            </div>
            <div class="actions">
                <button class="btn" type="submit">Look up vehicle</button>
            </div>
        </form>

        <form method="post" action="/scan" enctype="multipart/form-data" class="ocr">
            <span>Have a photo of the plate?</span>
            <input type="file" name="plate_image" accept="image/jpeg,image/png,image/heic" required>
            <button class="btn" type="submit">Read plate from photo</button>
        </form>
    </div>
</section>

<div class="wrap filter">
    <details {% if details %}open{% endif %}>
        <summary>
            Plate unclear? Narrow it down with other details
            <span class="pill" id="count" hidden>0</span>
            <i class="caret"></i>
        </summary>
        <div class="filter-body">
            <p class="filter-note">Pick a value from each database or type your own. Use <b>?</b> for plate characters you
                can't read. Leave blank anything you don't know; the plate and every detail you fill in are combined to find
                the one registration that agrees with them.</p>
            <div class="src-grid">
            {% for sec in sections %}
                <section class="src src-{{ sec.key }}">
                    <h3>{{ sec.title|replace(' DB', '') }}</h3>
                    {% for field, label in sec.fields %}{{ pick(field, label) }}{% endfor %}
                </section>
            {% endfor %}
            </div>
            <div class="filter-foot">
                <button class="btn" type="submit" form="lookup">Look up vehicle</button>
                <button class="btn btn--quiet" type="button" id="clear-details">Clear details</button>
                <span>Details from several databases make the match more certain.</span>
            </div>
        </div>
    </details>
</div>

<main class="wrap">
    {% if ocr_candidates %}
        <div class="notice">
            <strong>OCR readings &mdash; verify against the image:</strong>
            <ul>
            {% for item in ocr_candidates %}
                <li>{{ item.plate|fmt_plate }} &mdash; OCR confidence {{ '%.0f'|format(item.confidence * 100) }}%.
                    <a href="/?plate={{ item.plate|urlencode }}">Search this reading</a></li>
            {% endfor %}
            </ul>
        </div>
    {% endif %}

    {% if correction %}
        <div class="notice trace{% if not correction.corrected or not correction.valid %} notice--warn{% endif %}">
            <strong>Plate cleaning trace &middot; 4 processing steps</strong>
            <ol>
                <li class="step"><b>01 Original input</b> &mdash; <code>{{ correction.original }}</code>
                    (source value preserved)</li>
                <li class="step"><b>02 Normalize formatting</b> &mdash; <code>{{ correction.cleaned }}</code></li>
                <li class="step"><b>03 Plate-format validation</b> &mdash;
                    {% if correction.pattern_ok %}
                        format matches the expected Indian registration pattern.
                    {% else %}
                        format does not match the expected pattern (LL DD LLL DDDD);
                        applying position-aware correction.
                    {% endif %}
                </li>
                <li class="step"><b>04 Position-aware correction</b> &mdash;
                    {% if correction.corrected %}
                        <code>{{ correction.corrected }}</code>
                        {% if correction.changes %}
                            <ul>
                            {% for pos, old, new, kind in correction.changes %}
                                <li>Position {{ pos + 1 }}: <code>{{ old }}</code> &rarr;
                                    <code>{{ new }}</code> (expected a {{ kind }})</li>
                            {% endfor %}
                            </ul>
                        {% else %}
                            (no character changes needed)
                        {% endif %}
                        {% if correction.variants and correction.variants|length > 1 %}
                            <div class="alts">Alternative readings also checked against the databases:
                                {% for v in correction.variants[1:6] %}<code>{{ v }}</code> {% endfor %}</div>
                        {% endif %}
                        {% if not correction.valid %}
                            <div class="alts"><em>Warning: state code <code>{{ correction.corrected[:2] }}</code>
                            is not a known Indian state/UT code.</em></div>
                        {% endif %}
                    {% else %}
                        could not fit the Indian plate pattern (LL DD L DDDD); inspect candidate matches below.
                    {% endif %}
                </li>
            </ol>
            <em>No changes saved. The original value is preserved; corrections are suggestions to review.</em>
        </div>
    {% endif %}

    {% if identified_by %}
        <div class="notice notice--ok">
            <strong>Vehicle identified: {{ plate_resolved|fmt_plate }}.</strong>
            Matched on {{ identified_by }}. Review the evidence before acting on it.
        </div>
    {% endif %}

    {% if fuzzy_candidates %}
        <section class="cands" aria-labelledby="cand-h">
            <h2 id="cand-h">Fuzzy plate candidates</h2>
            <p>Suggestions, not proof of identity.</p>
            {% for item in fuzzy_candidates %}
                <div class="cand">
                    <span class="plate plate--sm"><span class="plate-strip"><i class="chakra"></i>IND</span><span class="plate-chars">{{ item.plate|fmt_plate }}</span></span>
                    <div class="score"><span>similarity {{ '%.1f'|format(item.score * 100) }}%</span>
                        <span class="score-bar"><i style="width: {{ '%.0f'|format(item.score * 100) }}%"></i></span></div>
                    <div class="chips">
                    {% if details %}
                        {% for field, v in (item.fields or {}).items() %}
                            <span class="chip {{ v.status }} src-{{ field_source.get(field, '') }}"><b>{{ field_labels.get(field, field) }}</b> {{ v.stored or '—' }}<span class="mark">{% if v.status == 'match' %}✓{% elif v.status == 'mismatch' %}✗{% else %}~{% endif %}</span></span>
                        {% endfor %}
                    {% endif %}
                    </div>
                    <a class="btn btn--ghost btn--sm" href="/?plate={{ item.plate|urlencode }}&confirmed=1" style="text-decoration:none">Open this vehicle</a>
                </div>
            {% endfor %}
        </section>
        {% if fuzzy_best and not fuzzy_auto %}
            <div class="notice notice--warn">
                {{ decision_reason or 'No candidate passed both the similarity and ambiguity checks.' }}
                Please verify manually{% if details %} or add another detail{% endif %}.
            </div>
        {% endif %}
    {% endif %}

    {% if error_message %}
        <div class="notice notice--bad">{{ error_message }}</div>
    {% endif %}

    {% if plate or details %}
        {% if match_score is not none %}
            <div class="notice">Selected registration similarity: {{ '%.1f'|format(match_score * 100) }}%.</div>
        {% endif %}

        {% if result and result.get('found') %}
            {% if reported_count %}
                <div class="notice">{{ reported_count }} new flag(s) reported to the Ministry of Transport for this lookup.</div>
            {% elif reported_count is none %}
                <div class="notice notice--warn">Ministry of Transport reporting is currently unavailable
                    (mot_db unreachable). The lookup result below is unaffected.</div>
            {% endif %}

            {% set decision = result.get('decision', '') %}
            {% set ts = result.get('trust_score', 0) or 0 %}
            {% set ss = result.get('source_status', {}) %}
            <article class="record">
                <div class="record-head">
                    <span class="plate plate--md"><span class="plate-strip"><i class="chakra"></i>IND</span><span class="plate-chars">{{ (result.get('plate') or plate)|fmt_plate }}</span></span>
                    <div class="record-title">
                        <h2>{{ result.get('make') or '' }} {{ result.get('model') or '' }}</h2>
                        <p>{{ result.get('color') or '' }}{% if result.get('color') and result.get('owner') %}, owned by {% elif result.get('owner') %}Owned by {% endif %}{{ result.get('owner') or '' }}</p>
                    </div>
                    {% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %}
                        <span class="verdict verdict--bad">&#9888; {{ decision }}</span>
                    {% elif decision == 'OK — INSURED AND CLEAR' %}
                        <span class="verdict verdict--clear">CLEAR</span>
                    {% else %}
                        <span class="verdict verdict--flag">FLAGGED</span>
                    {% endif %}
                </div>

                <div class="assess">
                    <div>
                        <div class="lbl">Trust Score</div>
                        <div class="trust-num">{{ ts }}<small>/100</small></div>
                        <div class="meter {{ '' if ts >= 80 else ('mid' if ts >= 50 else 'low') }}" role="img" aria-label="Trust score {{ ts }} out of 100"><i style="width: {{ ts }}%"></i></div>
                    </div>
                    <div>
                        <div class="lbl">Decision</div>
                        <p class="decision">{{ result.get('decision') }}</p>
                        <div class="lbl">Flags</div>
                        {% if result.get('flags') %}
                            {% for flag in result['flags'] %}<span class="flag">{{ flag }}</span>{% endfor %}
                        {% else %}
                            <span class="noflag">No flags raised</span>
                        {% endif %}
                    </div>
                </div>

                <div class="panels">
                    <section class="panel src-vehicles">
                        <header><h3>Registration</h3></header>
                        <dl>
                            <dt>Make / Model</dt><dd>{{ result.get('make') or '—' }} {{ result.get('model') or '' }}</dd>
                            <dt>Color</dt><dd>{{ result.get('color') or '—' }}</dd>
                            <dt>Owner</dt><dd>{{ result.get('owner') or '—' }}</dd>
                            <dt>Engine No.</dt><dd>{{ result.get('engine_no') or '—' }}</dd>
                            <dt>Chassis No.</dt><dd>{{ result.get('chassis_no') or '—' }}</dd>
                        </dl>
                    </section>
                    <section class="panel src-insurance">
                        <header><h3>Insurance</h3></header>
                        <dl>
                            <dt>Insurer</dt><dd>{{ result.get('insurer') or '—' }}</dd>
                            <dt>Policy No.</dt><dd>{{ result.get('policy_no') or '—' }}</dd>
                            <dt>Policy Start</dt><dd>{{ result.get('policy_start_date') or '—' }}</dd>
                            <dt>Policy End</dt><dd>{{ result.get('policy_end_date') or '—' }}</dd>
                        </dl>
                    </section>
                    <section class="panel src-rto">
                        <header><h3>RTO</h3></header>
                        <dl>
                            <dt>RTO Office</dt><dd>{{ result.get('rto_office') or '—' }}</dd>
                            <dt>Registration Date</dt><dd>{{ result.get('registration_date') or '—' }}</dd>
                            <dt>Renewal Date</dt><dd>{{ result.get('renewal_date') or '—' }}</dd>
                        </dl>
                    </section>
                    <section class="panel src-theft{% if decision in ['STOLEN', 'SCRAPPED/SHREDDED'] %} panel--alert{% endif %}">
                        <header><h3>Theft record</h3></header>
                        <dl>
                            <dt>Theft Status</dt><dd>{{ result.get('theft_status') or '—' }}</dd>
                            <dt>Theft Date</dt><dd>{{ result.get('theft_date') or '—' }}</dd>
                            <dt>Shredded Date</dt><dd>{{ result.get('shredded_date') or '—' }}</dd>
                        </dl>
                    </section>
                </div>
                {{ status_box(ss) }}
            </article>

        {% else %}
            <section class="record empty">
                <p class="empty-title">No registration confirmed</p>
                <p>{{ (result.get('message') if result else None) or 'No record found for this plate.' }}</p>
                {{ status_box(result.get('source_status') if result else None) }}
            </section>
        {% endif %}
    {% endif %}

    {% if not plate and not details and not ocr_candidates and not error_message %}
        <section class="legend" aria-labelledby="legend-h">
            <h2 id="legend-h">Where the answer comes from</h2>
            <div class="legend-grid">
                <div class="src src-vehicles"><h3>Registration</h3><p>Make, model, color, owner, engine and chassis numbers.</p>
                    {% set status = (health_status or {}).get('vehicles') %}
                    {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
                        {{ source_badge(status) }}
                    </div>{% endif %}
                </div>
                <div class="src src-insurance"><h3>Insurance</h3><p>Insurer, policy number and policy start and end dates.</p>
                    {% set status = (health_status or {}).get('insurance') %}
                    {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
                        {{ source_badge(status) }}
                    </div>{% endif %}
                </div>
                <div class="src src-rto"><h3>RTO</h3><p>Registering office, registration date and renewal date.</p>
                    {% set status = (health_status or {}).get('rto') %}
                    {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
                        {{ source_badge(status) }}
                    </div>{% endif %}
                </div>
                <div class="src src-theft"><h3>Theft record</h3><p>Whether the vehicle was stolen, recovered or shredded, and when.</p>
                    {% set status = (health_status or {}).get('theft') %}
                    {% if status %}<div class="legend-status"><span class="legend-status-label">Database</span>
                        {{ source_badge(status) }}
                    </div>{% endif %}
                </div>
            </div>
        </section>
    {% endif %}
</main>

<script>
(function () {
    var MODELS = {{ (model_by_make or {})|tojson }};
    var ALL_MODELS = {{ (field_options.get('model') or [])|tojson }};
    var $ = function (s, r) { return (r || document).querySelector(s); };
    var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

    function updateCount() {
        var n = $$('.src-grid input[type=text]').filter(function (i) { return i.value.trim() !== ''; }).length;
        var pill = $('#count');
        pill.textContent = n + (n === 1 ? ' detail' : ' details');
        pill.hidden = n === 0;
    }

    function buildOptions(sel, list, cur, txt) {
        while (sel.firstChild) sel.removeChild(sel.firstChild);
        function add(value, label) {
            var o = document.createElement('option');
            o.value = value; o.textContent = label; sel.appendChild(o);
        }
        add('', 'Any');
        list.forEach(function (v) { add(v, v); });
        add('__other', 'Other, type it\u2026');
        if (cur && list.indexOf(cur) > -1) { sel.value = cur; txt.hidden = true; }
        else if (cur) { sel.value = '__other'; txt.hidden = false; }
        else { sel.value = ''; txt.hidden = true; }
    }

    function refreshModels() {
        var p = $('.pick[data-field="model"]');
        if (!p) return;
        var sel = $('.pick-sel', p), txt = $('.pick-txt', p);
        var makeEl = $('#f_make');
        var make = makeEl ? makeEl.value.trim().toLowerCase() : '';
        var key = Object.keys(MODELS).filter(function (k) { return k.toLowerCase() === make; })[0];
        var list = key ? MODELS[key] : ALL_MODELS;
        var cur = txt.value;
        if (key && cur && list.indexOf(cur) === -1) { cur = ''; txt.value = ''; }
        buildOptions(sel, list, cur, txt);
    }

    $$('.pick').forEach(function (p) {
        var sel = $('.pick-sel', p), txt = $('.pick-txt', p), field = p.getAttribute('data-field');
        sel.addEventListener('change', function () {
            if (sel.value === '__other') { txt.hidden = false; txt.value = ''; txt.focus(); }
            else { txt.hidden = true; txt.value = sel.value; }
            if (field === 'make') refreshModels();
            updateCount();
        });
        txt.addEventListener('input', function () {
            if (field === 'make') refreshModels();
            updateCount();
        });
    });
    $$('.src-grid input[type=text]').forEach(function (i) { i.addEventListener('input', updateCount); });

    $('#clear-details').addEventListener('click', function () {
        $$('.src-grid input[type=text]').forEach(function (i) { i.value = ''; });
        $$('.pick').forEach(function (p) { $('.pick-sel', p).value = ''; $('.pick-txt', p).hidden = true; });
        refreshModels();
        updateCount();
    });

    refreshModels();
    updateCount();
})();
</script>
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


def _as_query_list(query):
    """Accept one plate string or a list of corrected variants; return clean keys."""
    queries = [query] if isinstance(query, str) else list(query or [])
    keys = []
    for q in queries:
        key = normalize_plate(q) or ""
        if key and key not in keys:
            keys.append(key)
    return keys


def _rank_plate_candidates(query, limit=FUZZY_TOP_K):
    """Compare the query (or several corrected variants) with live plate identifiers.

    Each registered plate keeps its best score across all variants.
    """
    query_keys = _as_query_list(query)
    if not query_keys:
        return []

    scores = {}
    for raw_plate in list_candidate_plates():
        canonical = normalize_plate(raw_plate)
        if not canonical:
            continue
        score = max(plate_similarity(key, canonical) for key in query_keys)
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


_OPTIONS_TTL = 300      # seconds to reuse the dropdown values
_OUTAGE_TTL = 30        # shorter reuse while the live sources are unreachable
_options_cache = {"at": 0.0, "ttl": 0, "data": {}, "models": {}}
STATIC_OPTIONS = {
    "policy_status": ["Active", "Expired", "No policy"],
    "renewal_status": ["Valid", "Lapsed", "No RTO record"],
    "theft_status": ["Stolen", "Recovered", "Shredded", "No theft record"],
}
OPTION_FIELDS = ("make", "model", "color", "owner_name", "insurer_name",
                 "rto_office", "registration_year", "theft_year")

# Where the project's CSV dataset lives (repo-root /data, or coordinator/data).
_HERE = Path(__file__).resolve().parent
DATA_DIRS = (_HERE.parent / "data", _HERE / "data")


def _read_dataset(filename):
    for folder in DATA_DIRS:
        path = folder / filename
        if path.is_file():
            try:
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    return list(csv.DictReader(handle))
            except Exception as exc:
                print(f"[app] could not read {path}: {exc}")
    return []


def _clean_value(value):
    text = str(value or "").strip()
    return "" if not text or text.startswith("No ") else text


@lru_cache(maxsize=1)
def _dataset_options():
    """Dropdown values taken from the project's CSV dataset.

    Returns (options_by_field, models_by_make). These work even when the
    live databases are down, so the filter always has real choices.
    """
    vehicles = _read_dataset("laptop1_vehicle_registration.csv")
    insurance = _read_dataset("laptop2_insurance.csv")
    rto = _read_dataset("laptop3_rto.csv")
    theft = _read_dataset("laptop4_theft_shredding.csv")

    values = {field: set() for field in OPTION_FIELDS}
    models_by_make = {}
    for row in vehicles:
        for field in ("make", "model", "color", "owner_name"):
            if _clean_value(row.get(field)):
                values[field].add(_clean_value(row[field]))
        make, model = _clean_value(row.get("make")), _clean_value(row.get("model"))
        if make and model:
            models_by_make.setdefault(make, set()).add(model)
    for row in insurance:
        if _clean_value(row.get("insurer_name")):
            values["insurer_name"].add(_clean_value(row["insurer_name"]))
    for row in rto:
        if _clean_value(row.get("rto_office")):
            values["rto_office"].add(_clean_value(row["rto_office"]))
        year = str(row.get("registration_date") or "")[:4]
        if year.isdigit():
            values["registration_year"].add(year)
    for row in theft:
        year = str(row.get("theft_date") or "")[:4]
        if year.isdigit():
            values["theft_year"].add(year)
    return values, models_by_make


def _field_options():
    """Dropdown values per field: CSV dataset merged with the live sources.

    Only distinct *values* are cached (never vehicle rows). Returns
    (options_by_field, models_by_make).
    """
    now = time.time()
    if _options_cache["data"] and now - _options_cache["at"] < _options_cache["ttl"]:
        return _options_cache["data"], _options_cache["models"]

    dataset_values, dataset_models = _dataset_options()
    merged = {field: set(vals) for field, vals in dataset_values.items()}
    models_by_make = {make: set(models) for make, models in dataset_models.items()}

    try:
        profiles = list_vehicle_profiles()
    except Exception:
        profiles = []
    for profile in profiles:
        for field in OPTION_FIELDS:
            if _clean_value(profile.get(field)):
                merged[field].add(_clean_value(profile[field]))
        make, model = _clean_value(profile.get("make")), _clean_value(profile.get("model"))
        if make and model:
            models_by_make.setdefault(make, set()).add(model)

    options = {k: list(v) for k, v in STATIC_OPTIONS.items()}
    for field, vals in merged.items():
        if vals:
            options[field] = sorted(vals, key=str.casefold)
    models = {make: sorted(vals, key=str.casefold)
              for make, vals in sorted(models_by_make.items(), key=lambda kv: kv[0].casefold())}

    _options_cache.update(
        at=now, data=options, models=models,
        ttl=_OPTIONS_TTL if profiles else _OUTAGE_TTL,
    )
    return options, models


@app.context_processor
def _inject_form_data():
    options, models = _field_options()
    return {"sections": SECTIONS, "field_options": options,
            "model_by_make": models, "field_labels": DETAIL_LABELS,
            "field_source": {f: sec["key"] for sec in SECTIONS
                             for f, _label in sec["fields"]}}


@app.context_processor
def _inject_theme():
    """Shared stylesheet, fonts and app bar for every page (presentation only)."""
    return {"theme_css": THEME_CSS, "font_links": FONT_LINKS, "appbar": appbar}


_PLATE_RE = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{1,4})$")


@app.template_filter("fmt_plate")
def _fmt_plate(value):
    """DL01AB1234 -> 'DL 01 AB 1234' (display only)."""
    text = re.sub(r"[\s.-]", "", str(value or "")).upper()
    match = _PLATE_RE.match(text)
    return " ".join(match.groups()) if match else text


def _read_details(source):
    """Optional operator-supplied details (make/model/color/owner/engine/chassis)."""
    return {
        field: (source.get(field) or "").strip()[:60]
        for field in DETAIL_FIELDS
        if (source.get(field) or "").strip()
    }


MAX_DETAIL_VARIANTS = 6   # corrected readings ranked when extra details are supplied


def _rank_unified(query, details, limit=FUZZY_TOP_K):
    """Rank registrations by plate alone, or plate + details when provided.

    `query` is one plate string or a list of corrected variants (best guess first).
    Returns (candidates, best_plate, auto_ok, reason, used_details).
    """
    if details:
        rows = list_vehicle_profiles()
        if rows:
            keys = _as_query_list(query)[:MAX_DETAIL_VARIANTS] or [""]
            merged = {}
            for key in keys:
                for item in rank_with_details(key, details, rows, limit):
                    prev = merged.get(item["plate"])
                    if prev is None or item["score"] > prev["score"]:
                        merged[item["plate"]] = item
            ranked = sorted(merged.values(),
                            key=lambda item: (-item["score"], item["plate"]))[:limit]
            best, auto, reason = decide(ranked, used_details=True)
            return ranked, best, auto, reason, True
        # Registration DB unreachable: fall back to plate-only ranking.
    candidates = _rank_plate_candidates(query, limit)
    best, auto = _fuzzy_decision(candidates)
    return candidates, best, auto, None, False


def _plate_correction(plate):
    """Position-aware correction for a typed/OCR plate, or None when not applicable.

    Skipped when the operator used '?' for unreadable characters: that wildcard
    is handled by the fuzzy matcher, and correct_plate() would turn it into 7/T.
    """
    if not plate or "?" in plate:
        return None
    return correct_plate(plate)


def _correction_queries(correction, fallback):
    """Plates to rank: the corrected plate first, then its alternative readings."""
    variants = (correction or {}).get("variants") or []
    if variants:
        return list(variants)
    corrected = (correction or {}).get("corrected")
    return [corrected] if corrected else [fallback]


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
    health_status = check_source_status() if not plate and not details else {}
    correction = None

    try:
        if plate or details:
            # Keep the typed plate; rank against the position-corrected readings.
            correction = _plate_correction(plate)
            queries = _correction_queries(correction, plate)

            fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
                _rank_unified(queries, details)
            )

            top = fuzzy_candidates[0] if fuzzy_candidates else None
            query_keys = _as_query_list(queries)
            exact = bool(
                top
                and plate
                and normalize_plate(top["plate"]) in query_keys
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

            # Reporting is only triggered for an exact match of the plate AS TYPED, or an
            # explicit selection. A corrected or fuzzy guess is displayed, never written back.
            typed_exact = exact and (
                normalize_plate(resolved_plate) == normalize_plate(plate)
            )
            if result and result.get("found") and (typed_exact or confirmed):
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
        health_status=health_status,
        correction=correction,
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
        # Best OCR reading -> position-aware correction -> fuzzy ranking.
        correction = _plate_correction(query)
        queries = _correction_queries(correction, query)
        fuzzy_candidates, fuzzy_best, fuzzy_auto, decision_reason, used = (
            _rank_unified(queries, details)
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
            correction=correction,
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


# =====================================================================
# Data Cleaning Workbench (/cleaning)
# The registration-plate trace now includes position-aware correction.
# =====================================================================
try:
    from fuzzy_match import IDENTIFIER_PREFIXES, normalize_identifier
except ImportError:
    # Fallbacks: this project's fuzzy_match.py does not define these helpers.
    IDENTIFIER_PREFIXES = {"engine_no": "ENG", "chassis_no": "CH"}

    def normalize_identifier(value, field):
        """Strip the standard prefix (if present) to expose the serial payload."""
        prefix = IDENTIFIER_PREFIXES.get(field, "")
        value = str(value or "")
        return value[len(prefix):] if prefix and value.startswith(prefix) else value

CLEANING_TEMPLATE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Cleaning Workbench</title>
{{ font_links }}
<style>
{{ theme_css }}
.muted{color:var(--muted)}.good{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.clean-hero{position:relative;overflow:hidden;margin-bottom:16px;padding:clamp(22px,4vw,32px);
  border:1px solid rgba(255,255,255,.13);border-radius:18px;color:#fff;
  background:linear-gradient(118deg,#123844 0%,#14515a 52%,#273c67 100%);
  box-shadow:0 22px 50px -26px rgba(14,43,59,.48)}
.clean-hero::after{content:"";position:absolute;right:-88px;top:-178px;width:300px;height:300px;
  border:1px solid rgba(255,255,255,.14);border-radius:50%;box-shadow:0 0 0 28px rgba(255,255,255,.035),0 0 0 58px rgba(255,255,255,.025)}
.clean-hero>*{position:relative;z-index:1}
.clean-kicker{display:inline-flex;align-items:center;gap:8px;color:#c6eee5;font-size:10.5px;
  font-weight:700;letter-spacing:.12em;text-transform:uppercase}
.clean-kicker::before{content:"";width:7px;height:7px;border-radius:50%;background:#65e0ae;box-shadow:0 0 0 4px rgba(101,224,174,.15)}
.clean-hero h1{margin:8px 0;font-size:clamp(26px,3.4vw,35px);font-weight:700;letter-spacing:-.035em;line-height:1.12}
.clean-hero p{max-width:70ch;margin:0;color:#c0d7dc;font-size:13.5px;line-height:1.65}
.clean-features{display:flex;flex-wrap:wrap;gap:8px;margin-top:17px}
.clean-feature{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;color:#e2eff0;
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:999px;font-size:10.5px;font-weight:600}
.clean-feature::before{content:"";width:5px;height:5px;border-radius:50%;background:#ffc56b}
.clean-card{overflow:hidden;margin-bottom:16px}
.clean-card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line)}
.clean-card-head h2{margin:0;font-size:14px;font-weight:650}
.clean-card-head p{margin:3px 0 0;color:var(--muted);font-size:12px}
.clean-form{display:grid;grid-template-columns:minmax(190px,.75fr) minmax(240px,1.5fr) auto;gap:14px;align-items:end;padding:20px}
.clean-form .btn{min-height:38px}
.clean-input-hint{margin:6px 0 0;color:var(--muted);font-size:11px}
.clean-trace-head{align-items:flex-start}
.clean-safe{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid var(--ok-line);
  border-radius:999px;background:var(--ok-bg);color:var(--ok);font-size:10px;font-weight:700;white-space:nowrap}
.clean-safe::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.clean-note{margin:0;padding:13px 20px;color:var(--ink-2);background:#f8faf9;border-bottom:1px solid var(--line);font-size:12px;line-height:1.6}
.clean-steps{display:grid;gap:10px;padding:16px 20px}
.clean-step{position:relative;padding:14px 15px 14px 48px;border:1px solid var(--line);border-radius:10px;
  background:linear-gradient(145deg,#fff,#f8faf9);transition:border-color .16s,box-shadow .16s,transform .16s}
.clean-step:hover{transform:translateY(-1px);border-color:var(--line-2);box-shadow:var(--sh-2)}
.clean-step-index{position:absolute;left:14px;top:14px;display:grid;place-items:center;width:23px;height:23px;
  border-radius:7px;background:var(--brand-50);border:1px solid var(--brand-100);color:var(--brand);font-size:10px;font-weight:750}
.clean-step h3{margin:0 0 4px;font-size:12.5px;font-weight:650}
.clean-step p{margin:0 0 8px;color:var(--ink-2);font-size:12px;line-height:1.55}
.clean-step p:last-child{margin-bottom:0}
.clean-value{padding:8px 10px;border:1px solid var(--line);border-radius:7px;background:#f3f6f5;color:var(--ink);
  font:500 12px/1.5 var(--mono);overflow-wrap:anywhere}
.clean-level{display:inline-flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;font-weight:600}
.clean-level::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.clean-level.good{color:var(--ok)}.clean-level.warn{color:var(--warn)}.clean-level.bad{color:var(--bad)}.clean-level.muted{color:var(--muted)}
.clean-candidates{padding:0 20px 16px}
.clean-candidates h3{margin:0 0 9px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.clean-candidate{display:grid;grid-template-columns:minmax(0,1fr) minmax(100px,160px) 50px;align-items:center;gap:12px;
  padding:9px 11px;border:1px solid var(--line);border-bottom:0;background:#fff}
.clean-candidate:first-of-type{border-radius:9px 9px 0 0}
.clean-candidate:last-child{border-bottom:1px solid var(--line);border-radius:0 0 9px 9px}
.clean-candidate-value{min-width:0;font:500 12px var(--mono);overflow-wrap:anywhere}
.clean-score-track{height:6px;overflow:hidden;border-radius:999px;background:#e8eeeb}
.clean-score-fill{height:100%;border-radius:inherit;background:linear-gradient(90deg,#4d9d80,#4569bb)}
.clean-candidate strong{color:var(--ink-2);font-size:11px;text-align:right;font-variant-numeric:tabular-nums}
.clean-final{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:14px;
  margin:0 20px 20px;padding:16px;border:1px solid var(--brand-100);border-radius:11px;
  background:linear-gradient(120deg,#edf5f1,#eef1f8)}
.clean-final-mark{display:grid;place-items:center;width:38px;height:38px;border-radius:11px;
  background:#fff;border:1px solid var(--brand-100);color:var(--brand);font-size:17px;font-weight:700}
.clean-final h3{margin:0 0 5px;color:var(--brand);font-size:10px;font-weight:750;letter-spacing:.09em;text-transform:uppercase}
.clean-final .clean-value{margin-bottom:6px;background:#fff;font-size:13px;font-weight:600}
.clean-final p{margin:0;font-size:11.5px;font-weight:500;line-height:1.5}
.clean-about{padding:17px 20px}
.clean-about h2{margin:0 0 5px;font-size:13px;font-weight:650}
.clean-about p{margin:0;color:var(--muted);font-size:12px;line-height:1.65}
@media(max-width:720px){
  .clean-form{grid-template-columns:1fr;padding:16px}
  .clean-form .btn{width:100%}
  .clean-card-head{padding:14px 16px}
  .clean-safe{white-space:normal}
  .clean-note{padding:12px 16px}
  .clean-steps{padding:13px 15px}
  .clean-candidates{padding:0 15px 14px}
  .clean-candidate{grid-template-columns:minmax(0,1fr) 44px;gap:6px 10px}
  .clean-score-track{grid-column:1;grid-row:2}
  .clean-candidate strong{grid-column:2;grid-row:1 / span 2}
  .clean-final{margin:0 15px 15px;padding:13px;gap:10px}
}
</style></head><body class="ui">
{{ appbar('cleaning') }}
<main class="wrap page">
<section class="clean-hero">
<span class="clean-kicker">Transparent data preparation</span>
<h1>Data Cleaning Workbench</h1>
<p>Inspect how a value is normalized, validated, and compared with known records. Suggestions are shown for review—your input is never silently rewritten or saved.</p>
<div class="clean-features"><span class="clean-feature">Formatting trace</span><span class="clean-feature">Validation checks</span><span class="clean-feature">Position-aware correction</span><span class="clean-feature">Evidence-based suggestions</span></div>
</section>
<section class="card clean-card">
<div class="clean-card-head"><div><h2>Inspect a value</h2><p>Choose a field and enter the value you want to review.</p></div></div>
<form method="post" action="/cleaning" class="clean-form">
<div><label for="field">Field to inspect</label><select id="field" name="field">
{% for key,label in fields %}<option value="{{ key }}" {% if selected_field==key %}selected{% endif %}>{{ label }} ({{ key }})</option>{% endfor %}
</select></div>
<div><label for="raw">Input value</label><input id="raw" name="raw" value="{{ raw }}" placeholder="e.g. DL 01 AB 1002" autocomplete="off" required><p class="clean-input-hint">Your value is inspected only; no database changes are made.</p></div>
<button class="btn" type="submit">Inspect value <span aria-hidden="true">&rarr;</span></button></form></section>
{% if result %}<section class="card clean-card" aria-labelledby="trace-title">
<div class="clean-card-head clean-trace-head"><div><h2 id="trace-title">Cleaning trace</h2><p>{{ selected_label }} · {{ result.steps|length }} processing steps</p></div><span class="clean-safe">No changes saved</span></div>
<p class="clean-note">The original input is preserved. Any suggested correction is based on available matching evidence and should be reviewed before use.</p>
<div class="clean-steps">
{% for step in result.steps %}<article class="clean-step"><span class="clean-step-index" aria-hidden="true">{{ '%02d'|format(loop.index) }}</span><h3>{{ step.title }}</h3><p>{{ step.description }}</p>{% if step.value is not none %}<div class="clean-value">{{ step.value if step.value else '(empty)' }}</div>{% endif %}{% if step.note %}<p class="clean-level {{ step.level or 'muted' }}">{{ step.note }}</p>{% endif %}</article>{% endfor %}
</div>
{% if result.candidates %}<div class="clean-candidates"><h3>Closest known values</h3>{% for c in result.candidates %}<div class="clean-candidate"><span class="clean-candidate-value">{{ c.value }}</span><span class="clean-score-track" aria-hidden="true"><span class="clean-score-fill" style="display:block;width:{{ '%.1f'|format(c.score*100) }}%"></span></span><strong>{{ '%.1f'|format(c.score*100) }}%</strong></div>{% endfor %}</div>{% endif %}
<div class="clean-final"><span class="clean-final-mark" aria-hidden="true">&rarr;</span><div><h3>Suggested output</h3><div class="clean-value">{{ result.output or '(empty)' }}</div><p class="{{ result.level }}">{{ result.status }}</p></div></div>
</section>{% endif %}
<section class="card clean-about"><h2>How the workbench handles data</h2><p>Registration plates use normalization, position-aware character correction (letters where letters belong, digits where digits belong) and OCR-aware similarity matching. Engine and chassis identifiers use prefix and formatting checks, while model values are compared with known records when available. Ambiguous matches stay suggestions for manual review—no value is automatically written back to the databases.</p></section>
</main></body></html>
"""

CLEANING_FIELDS = [
    ("reg_plate", "Registration plate"),
    ("engine_no", "Engine number"),
    ("chassis_no", "Chassis number"),
    ("model", "Vehicle model"),
]


def _cleaning_normalize(field, raw):
    """Formatting-only normalization. Does not guess character corrections."""
    import re
    value = str(raw or "").strip()
    if field in ("reg_plate", "engine_no", "chassis_no"):
        return re.sub(r"[\s.-]", "", value.upper())
    if field == "model":
        return re.sub(r"\s+", " ", value).strip().title()
    return value


def _cleaning_candidates(field, normalized, limit=5, variants=None):
    """Fetch known candidate values via existing mediator lookups where possible.

    For registration plates, `variants` (position-corrected readings) are compared
    too and each registered plate keeps its best score.
    """
    from difflib import SequenceMatcher
    candidates = []
    try:
        plates = list_candidate_plates() or []
    except Exception:
        plates = []
    if field == "reg_plate":
        keys = [k for k in dict.fromkeys([normalized] + list(variants or [])) if k]
        best_by_plate = {}
        for plate in plates:
            canonical = normalize_plate(plate)
            if not canonical:
                continue
            score = max(float(plate_similarity(key, canonical)) for key in keys)
            if canonical not in best_by_plate or score > best_by_plate[canonical]:
                best_by_plate[canonical] = score
        candidates = [{"value": p, "score": s} for p, s in best_by_plate.items()]
    else:
        # query_vehicle exposes the vehicle fields used by the existing lookup page.
        # We only use values that the mediator actually returns; no values are fabricated.
        seen = set()
        for plate in plates:
            try:
                record = query_vehicle(plate)
            except Exception:
                continue
            if not isinstance(record, dict) or not record.get("found"):
                continue
            key_map = {"model": "model", "engine_no": "engine_no", "chassis_no": "chassis_no"}
            value = str(record.get(key_map[field]) or "").strip()
            if not value:
                continue
            normalized_candidate = _cleaning_normalize(field, value)
            if normalized_candidate in seen:
                continue
            seen.add(normalized_candidate)
            score = SequenceMatcher(None, normalized.casefold(), normalized_candidate.casefold(), autojunk=False).ratio()
            candidates.append({"value": value, "score": score})
    candidates.sort(key=lambda item: (-item["score"], item["value"]))
    return candidates[:limit]


def _describe_changes(changes):
    """'position 3: @ -> 0 (expected a digit); ...' for the trace."""
    return "; ".join(
        f"position {pos + 1}: {old} \u2192 {new} (expected a {kind})"
        for pos, old, new, kind in changes
    )


def _build_cleaning_trace(field, raw):
    import re
    original = str(raw or "")
    normalized = _cleaning_normalize(field, original)
    steps = [
        {"title": "Original input", "description": "The value exactly as entered by the user; it is not overwritten.", "value": original, "note": "Source value preserved.", "level": "muted"},
        {"title": "Normalize formatting", "description": "Remove spaces, hyphens and dots and standardize case for identifiers; collapse repeated spaces for model names.", "value": normalized, "note": "Formatting normalization is not the same as correcting an incorrect character.", "level": "good" if normalized != original else "muted"},
    ]
    output = normalized
    status = "Normalized only. No correction was made automatically."
    level = "warn"
    candidates = []
    if field == "reg_plate":
        valid = bool(re.fullmatch(r"[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}", normalized))
        steps.append({"title": "Plate-format validation", "description": "Check the normalized value against the expected Indian registration-plate pattern.", "value": normalized, "note": "Format looks valid." if valid else "Format does not match the expected pattern; applying position-aware correction.", "level": "good" if valid else "warn"})

        # Position-aware correction: letters where letters belong, digits where digits belong.
        fix = correct_plate(original) if "?" not in original else None
        corrected = (fix or {}).get("corrected")
        variants = (fix or {}).get("variants") or []
        if fix is not None:
            if corrected:
                changes = fix.get("changes") or []
                if changes:
                    note = "Corrected by character position \u2014 " + _describe_changes(changes) + "."
                else:
                    note = "No character changes were needed."
                lvl = "good"
                if not fix.get("valid"):
                    note += f" Warning: state code {corrected[:2]} is not a known Indian state/UT code."
                    lvl = "warn"
                steps.append({"title": "Position-aware correction", "description": "Plate layout is state (2 letters) + district (2 digits) + series (1\u20133 letters) + number (4 digits). Each wrong character is replaced by its nearest look-alike for that position (S\u21925, O\u21920, T\u21927 in digit slots; 5\u2192S, 0\u2192O in letter slots; special characters follow the slot they sit in).", "value": corrected, "note": note, "level": lvl})
            else:
                steps.append({"title": "Position-aware correction", "description": "Fit the value to the plate layout and fix characters by position.", "value": None, "note": "The value has too few or too many characters to fit a plate (9\u201311 expected); no correction was guessed.", "level": "warn"})

        plate_variants = variants or ([normalized] if normalized else [])
        candidates = _cleaning_candidates(field, normalized, variants=plate_variants)
        variant_keys = {normalize_plate(v) for v in plate_variants}
        if candidates:
            best = candidates[0]
            margin = best["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0.0)
            clear = best["score"] >= 0.82 and margin >= 0.05
            exact = best["score"] >= 0.999 and best["value"] in variant_keys
            steps.append({"title": "Registered-plate matching", "description": "Rank known registration plates with the project's OCR-aware plate similarity function, using the corrected reading and its alternatives.", "value": best["value"], "note": f"Best candidate similarity: {best['score']:.1%}. " + ("The candidate is a strong suggestion, but should still be confirmed." if (clear or exact) else "The match is weak or ambiguous; manual review is required."), "level": "good" if (clear or exact) else "warn"})
            if exact:
                output = best["value"]
                status = "Exact registered plate match after position-aware correction." if best["value"] != normalized else "Exact registered plate match."
                level = "good"
            elif clear:
                output = best["value"]
                status = "Strong candidate suggested; confirm before using it."
                level = "good"
            elif corrected:
                output = corrected
                status = "No registered plate confirmed this reading. Showing the position-aware correction for review."
                level = "warn"
            else:
                status = "No unique high-confidence correction. Original normalized value retained for review."
        else:
            steps.append({"title": "Registered-plate matching", "description": "Compare against known registered plates.", "value": None, "note": "No candidate values were available from the mediator.", "level": "warn"})
            if corrected:
                output = corrected
                status = "Position-aware correction suggested; no registered plates were available to confirm it."
                level = "warn"
    elif field in ("engine_no", "chassis_no"):
        candidates = _cleaning_candidates(field, normalized)
        prefix = IDENTIFIER_PREFIXES.get(field, "")
        identifier = normalize_identifier(normalized, field)
        has_prefix = normalized.startswith(prefix)
        steps.append({"title": "Identifier prefix and payload", "description": f"Expected standard prefix: {prefix}. The prefix is separated from the serial payload for comparison.", "value": identifier, "note": "Standard prefix present." if has_prefix else f"Prefix {prefix} is missing or not in the expected position; this is not enough evidence by itself to rebuild the identifier.", "level": "good" if has_prefix else "warn"})
        if candidates:
            best = candidates[0]
            steps.append({"title": "Compare with registered identifiers", "description": "Compare the input with identifier values actually returned by the mediator, when that field is exposed.", "value": best["value"], "note": f"Best text similarity: {best['score']:.1%}. Treat this as a suggestion, not proof of identity.", "level": "good" if best["score"] >= 0.9 else "warn"})
            if best["score"] >= 0.9:
                output = best["value"]
                status = "High-similarity candidate suggested; verify cross-field consistency before acceptance."
                level = "good"
            else:
                status = "No sufficiently strong identifier match; manual review required."
        else:
            steps.append({"title": "Cross-field consistency", "description": "A safe repair may require engine/chassis relationships learned from registry records.", "value": None, "note": "The mediator did not expose candidate identifiers for this field, so no correction is guessed.", "level": "warn"})
    elif field == "model":
        candidates = _cleaning_candidates(field, normalized)
        if candidates:
            best = candidates[0]
            margin = best["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0.0)
            clear = best["score"] >= 0.78 and margin >= 0.05
            steps.append({"title": "Known-model fuzzy matching", "description": "Compare the normalized input with model names returned by vehicle records.", "value": best["value"], "note": f"Best similarity: {best['score']:.1%}. " + ("Unique high-confidence suggestion." if clear else "Low-confidence or ambiguous match; review required."), "level": "good" if clear else "warn"})
            if clear:
                output = best["value"]
                status = "Known-model suggestion found; confirm before acceptance."
                level = "good"
            else:
                status = "No unique high-confidence model correction; normalized value retained."
        else:
            steps.append({"title": "Known-model matching", "description": "Compare against models exposed by the existing mediator lookup.", "value": None, "note": "No known model values were available, so no correction is guessed.", "level": "warn"})
    return {"steps": steps, "candidates": candidates, "output": output, "status": status, "level": level}


@app.route("/cleaning", methods=["GET", "POST"])
def data_cleaning_workbench():
    selected_field = request.values.get("field", "reg_plate")
    if selected_field not in {field for field, _label in CLEANING_FIELDS}:
        selected_field = "reg_plate"
    raw = request.values.get("raw", "")
    result = _build_cleaning_trace(selected_field, raw) if request.method == "POST" and raw.strip() else None
    return render_template_string(CLEANING_TEMPLATE, fields=CLEANING_FIELDS,
                                  selected_field=selected_field,
                                  selected_label=dict(CLEANING_FIELDS)[selected_field],
                                  raw=raw, result=result)


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
