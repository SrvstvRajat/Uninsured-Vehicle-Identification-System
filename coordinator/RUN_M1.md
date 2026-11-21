# Phase 3 — M1 (Coordinator) — run guide

Copy these files into your `coordinator/` folder (replace the old ones), then restart
`app.py`. No new `.env` settings are needed: the coordinator uses the same
`<SOURCE>_API_URL` / `<SOURCE>_API_TOKEN` lines as Phase 2.

| File | Status | What it does |
|---|---|---|
| `context_engine.py` | NEW | query understanding → vehicle (Phase 2 entity matching) → round 1: every database discovers its own context (`/api/context`) → round 2: discovered identifiers into the other databases → accumulate + prune |
| `unstructured.py` | NEW | sends the query context to every laptop's `/api/docsearch`, merges, attaches each document to the context row it documents |
| `context_page.py` | NEW | the **Context search** page `/context` and the JSON API `/context/api` |
| `phase3_eval.py` | NEW | evaluation: context rows, recall / precision of documents, context vs query-only baseline |
| `source_client.py` | changed | `context()`, `docsearch()`; similarity on any table (e.g. `owners.full_name`) |
| `federated_sql.py` | changed | SQL console knows the 16 new Phase 3 tables (+ new FK columns); fuzzy names keep only close matches |
| `app.py` | changed | 2 lines: registers the Context search page |
| `ui_theme.py` | changed | "Context search" in the top navigation |
| `source_api/source_api.py` | changed | same file as on the laptops (ownership intent includes the owner's other vehicles; documents carry their dates) — copy it to M2 as well |

## Run

```bash
python3 app.py                         # then open http://localhost:5001/context
```

Try: `Is UP09AI8815 insured and was it ever stolen?`, `Ownership history of UP09AI8815`,
`What vehicles does the person with phone 9876543210 own?` (use real plates / phones
from your data).

The page shows, in order: what was understood (plates, phones, intents) · the vehicle
(Phase 2) · every federated sub-query (round, machine, seed, status, rows, ms) · the
context per database (hop, FK path, relevance; round-2 rows marked) · cross-database
links · the correlated documents with *why* they matched and which row they belong to.
`/context/api?q=...` returns the same as JSON.

Laptops that are not migrated yet are handled: `not_served` (Phase 3 tables missing:
its Phase 2 record is used), `unreachable` (laptop off), `no_index` (no documents yet).

## Evaluate (Rubric 2 + 3 evidence)

Copy from each laptop: `unstructured/manifest.csv` → `phase3/eval/manifests/<source>.csv`
(e.g. `vehicles.csv`), and from M2 the folder `phase3/data/M2_registration` →
`phase3/eval/M2_registration`. These are ground truth for scoring only.

```bash
python3 phase3_eval.py --auto 20                       # plate questions
python3 phase3_eval.py --auto-phone 20                 # phone-only questions
```

Writes `phase3/evidence/eval_<time>.csv` and `.md` (a table for the report). The
baseline column is the same search with only what the user typed (no context).
