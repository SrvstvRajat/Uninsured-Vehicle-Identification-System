# Phase 3 — Theft laptop (M5) — complete setup

Everything is in this one folder. Open a terminal **inside `TheftDB`** and run every
command from here:

```bash
cd IIA_Project_1/TheftDB
```

Windows: use `python` instead of `python3` (PowerShell notes at the end).

## Folder contents

| File / folder | What it is |
|---|---|
| `app.py`, `schema.sql`, `coordinator_user.sql` | your Phase 2 theft app and schema (unchanged) |
| `source_api.py` | the REST API the coordinator calls (Phase 2 + Phase 3 endpoints) |
| `fuzzy_match.py` | similarity library used by the API |
| `schema_theft.sql`, `schema_theft_fk.sql` | Phase 3 tables + foreign keys |
| `gen_theft.py`, `setup_theft.py` | generate the new rows; create tables, load, add FKs, verify |
| `generate_documents.py`, `build_doc_index.py` | FIR / recovery / news documents and their search index |
| `check_source_api.py` | end-to-end check, saves evidence |
| `p3_common.py`, `p3_setup.py` | helpers |
| `templates/` | the 3 document templates (already filled in) |
| `data/M2_registration/` | **put the registration laptop's CSVs here** |
| created when you run: `data/M5_theft/`, `docs_out/`, `unstructured/`, `evidence/` | outputs |

## Step 0 — Copy from the registration laptop

Copy everything in the registration laptop's `phase3/data/M2_registration/`
(`vehicles.csv`, `owners.csv`, `ownership_transfers.csv`, …) into **`data/M2_registration/`**.

## Step 1 — Python packages

```bash
pip install flask mysql-connector-python python-dotenv sqlglot numpy
```

(inside your project's `.venv` if you use one)

## Step 2 — `.env`

Use your existing `.env` (in `IIA_Project_1/` or here). It must contain:

```
COORDINATOR_USER=coordinator              # Phase 2: the API logs in with this
COORDINATOR_PASSWORD=...
THEFT_API_TOKEN=SAME_TOKEN_AS_THE_COORDINATOR_USES
SOURCE_API_VERBOSE=true
PHASE3_DB_USER=root                       # admin login for creating tables
PHASE3_DB_PASSWORD=YOUR_MYSQL_ROOT_PASSWORD
```

## Step 3 — Check the Phase 2 data, back up

```bash
mysql -u root -p -e "SELECT status, COUNT(*) FROM theft_db.theft_records GROUP BY status;"
mysqldump -u root -p --result-file=backup_theft.sql theft_db
```

## Step 4 — Generate the new data (Rubric 1)

```bash
python3 gen_theft.py
```

Expected: `police_stations · firs (one per theft) · recoveries · shredding_certificates ·
written to …/TheftDB/data/M5_theft/`.

## Step 5 — Tables, data, foreign keys

```bash
python3 setup_theft.py all
```

Check: 5 tables InnoDB · **foreign keys total: 5** · **all orphan checks = 0**.
Saved to `evidence/M5_theft_verify.txt` — screenshot it.
Safe to re-run. To reload: `python3 setup_theft.py reset`, then `load`, then `fk`.

## Step 6 — Documents (Rubric 3)

```bash
python3 generate_documents.py --data data --docs-root docs_out --types fir_narrative recovery_report news_article --reuse-templates
```

macOS / Linux:
```bash
rm -rf unstructured && mkdir unstructured
cp -r docs_out/M5_theft/docs unstructured/docs
cp docs_out/M5_theft/manifest.csv unstructured/
python3 build_doc_index.py
```

Windows PowerShell:
```powershell
Remove-Item -Recurse -Force unstructured -ErrorAction SilentlyContinue
New-Item -ItemType Directory unstructured | Out-Null
Copy-Item -Recurse docs_out\M5_theft\docs unstructured\docs
Copy-Item docs_out\M5_theft\manifest.csv unstructured\
python build_doc_index.py
```

## Step 7 — Start the API (keep this window open)

```bash
python3 source_api.py theft
```

First line ends with `similarity=ON   response-log=ON`. Records page: `http://localhost:5104/`.
(Your Phase 2 UI `python3 app.py` still runs separately on port 5002.)

## Step 8 — Check (second window, also inside TheftDB)

```bash
mysql -u root -p -e "SELECT plate_no, status FROM theft_db.theft_records LIMIT 5;"
python3 check_source_api.py --source theft --plate PLATE_FROM_ABOVE --terms stolen recovered
```

Expected: 5 tables · 5 FKs · context: theft → FIR, police station, recovery ·
documents: that theft's FIR narrative / recovery report. Saved in `evidence/`.

## Step 9 — Coordinator (same laptop) and hand-offs

* Coordinator `.env`: `THEFT_API_URL=http://127.0.0.1:5104` and the same `THEFT_API_TOKEN`.
  Start the coordinator in another window: `cd IIA_Project_1/coordinator` → `python3 app.py`.
* Give **`data/M5_theft/theft_records.csv`** to the RTO laptop (its `phase3/data/M5_theft/`)
  and the insurance laptop (`--theft-csv`).
* Evaluation: copy `unstructured/manifest.csv` to `coordinator/phase3/eval/manifests/theft.csv`.

## If something goes wrong

| Message | Fix |
|---|---|
| `M2 data not found in …/data/M2_registration` | step 0 |
| `Access denied` | `PHASE3_DB_*` (setup scripts) or `COORDINATOR_*` (API) wrong in `.env` |
| `Table … already has rows` | `python3 setup_theft.py reset`, then `load`, then `fk` |
| `Refusing to start: set THEFT_API_TOKEN` | add it to `.env` (8+ characters) |
| `fir_narrative: no templates` | the `templates/` folder is missing — it ships in this folder |
| coordinator shows theft `unreachable` / `HTTP 401` | API not running / tokens differ |

## Windows PowerShell notes

`python3` → `python` · `mysql … < f.sql` → `mysql … -e "source f.sql"` ·
`mysqldump … > f.sql` → `mysqldump … --result-file=f.sql` · one command per line.
