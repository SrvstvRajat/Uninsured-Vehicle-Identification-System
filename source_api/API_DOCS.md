# Switching the Coordinator from direct DB access to REST APIs

The decomposition logic is unchanged (parse -> split per source -> push down filters -> fetch in
parallel -> integrate). Only the transport changed: each sub-query now goes to the owning laptop's
REST API instead of a MySQL connection.

```
Coordinator (federated_sql.py)  --HTTP + token-->  source_api.py  --local-->  that laptop's MySQL
```

## Files
| File | Where | Status |
|---|---|---|
| `source_api/source_api.py` | every source laptop (repo copy) | NEW |
| `coordinator/federated_sql.py` | coordinator | REPLACE |
| `coordinator/sql_console.py` | coordinator | REPLACE (shows the REST endpoint in the plan) |

No new pip packages. `config.py`, `app.py` and `requirements.txt` stay as they are
(`config.py` already had the `*_API_URL` / `*_API_TOKEN` settings).

## 1. On EACH source laptop
Pick a token per source (8+ characters) and add it to that laptop's `.env`
(the coordinator laptop needs the same values, see step 2):

```
VEHICLES_API_TOKEN=pick-a-secret-1        # only the line for the source this laptop owns
COORDINATOR_USER=coordinator              # the MySQL account the API uses LOCALLY (already in .env)
COORDINATOR_PASSWORD=...
# SOURCE_API_ALLOW_WRITES=true            # only if INSERT/UPDATE/DELETE must work for this source
```

Start it (one terminal per source; the source name is the argument):

```bash
python3 source_api/source_api.py vehicles     # registration laptop, port 5101
python3 source_api/source_api.py insurance    # insurance laptop,    port 5102
python3 source_api/source_api.py rto          # RTO laptop,          port 5103
python3 source_api/source_api.py theft        # theft laptop,        port 5104
python3 source_api/source_api.py mot          # MoT laptop,          port 5105
```
If theft and MoT are on the same laptop, run both commands in two terminals.
Allow inbound TCP on that port in the laptop's firewall. MySQL port 3306 no longer has to be
reachable from the network, so you can set `bind-address = 127.0.0.1` in MySQL.

Check it from the coordinator laptop:
```bash
curl http://<laptop-ip>:5101/api/health
```

## 2. On the Coordinator laptop: add to `.env`
```
VEHICLES_API_URL=http://192.168.84.129:5101
VEHICLES_API_TOKEN=pick-a-secret-1
INSURANCE_API_URL=http://192.168.52.159:5102
INSURANCE_API_TOKEN=...
RTO_API_URL=http://192.168.42.188:5103
RTO_API_TOKEN=...
THEFT_API_URL=http://localhost:5104
THEFT_API_TOKEN=...
MOT_API_URL=http://localhost:5105
MOT_API_TOKEN=...
SQL_CONSOLE_ALLOW_WRITES=true             # only if you want writes from the console
```
Then restart `python3 coordinator/app.py`. The plan panel shows "Served via REST API: POST ...".

## Writes need TWO switches (and MySQL's grants)
1. Coordinator: `SQL_CONSOLE_ALLOW_WRITES=true`
2. That source laptop: `SOURCE_API_ALLOW_WRITES=true`, then restart `source_api.py`
3. The MySQL account the API uses on that laptop must hold the right (`GRANT INSERT ON ...`).
   The error message names the account and the exact GRANT line when MySQL refuses.

## What the source API accepts
`POST /api/query` takes ONE plain `SELECT` on that source's own table only. It rejects other tables or
databases, `INTO OUTFILE`, locking reads, variables, `SLEEP`/`BENCHMARK`/`LOAD_FILE`, `/*! */`
comments and stacked statements; it runs the regenerated SQL in a READ ONLY session with a time limit.
`POST /api/execute` takes ONE `INSERT`/`UPDATE`/`DELETE` on its table (no DDL). Every call needs the token.

## Not changed
`mediator.py` (the plate-lookup page) and `reporting.py` still open direct MySQL connections, because
the request was for the decomposition logic only. They can be moved onto the same API the same way.