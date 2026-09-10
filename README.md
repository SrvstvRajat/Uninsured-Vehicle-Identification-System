# Identification of Uninsured Vehicles

A heterogeneous vehicle-data integration system that combines vehicle registration, insurance, RTO, theft/shredding, and Ministry of Transport data to build a unified vehicle profile, identify suspicious/flagged vehicles, and generate a Ministry compliance report.

> **Current version:** Single-machine setup. All five MySQL databases and the Python Coordinator run on the same machine.

---

## 1. Architecture

```text
                    SINGLE MACHINE
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  MySQL                                                   │
│  ├── vehicle_registration_db  → vehicles                │
│  ├── insurance_db             → insurance_policies      │
│  ├── rto_db                  → rto_records              │
│  ├── theft_db                → theft_records             │
│  └── mot_db                  → mot_reports               │
│                                                          │
│                    ↓                                     │
│            Python Coordinator                            │
│            ├── integration_engine.py                     │
│            ├── query_tool.py                             │
│            ├── generate_report.py                        │
│            └── app.py                                    │
│                    ↓                                     │
│          Integrated Vehicle Master                       │
│                    ↓                                     │
│       Vehicle 360° Profile / Decision                    │
│                    ↓                                     │
│          Ministry Compliance Report                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 2. Project Structure

```text
.
├── requirements.txt
├── .env
├── laptop1_registration/
│   ├── schema.sql
│   ├── coordinator_user.sql
│   └── generate_data.py
├── laptop2_insurance/
│   ├── schema.sql
│   ├── coordinator_user.sql
│   └── generate_data.py
├── laptop3_rto/
│   ├── schema.sql
│   ├── coordinator_user.sql
│   └── generate_data.py
├── laptop4_theft/
│   ├── schema.sql
│   ├── coordinator_user.sql
│   └── generate_data.py
├── laptop5_mot/
│   ├── schema.sql
│   └── coordinator_user.sql
└── coordinator/
    ├── config.py
    ├── integration_engine.py
    ├── query_tool.py
    ├── generate_report.py
    └── app.py
```

---

# 3. Requirements

- MySQL Server
- Python 3.10+
- pip
- Git (optional)

Check installations:

```bash
mysql --version
python3 --version
pip3 --version
```

If `mysql` is not in PATH on macOS with Homebrew, use:

```bash
/opt/homebrew/opt/mysql/bin/mysql --version
```

---

# 4. Start MySQL

For Homebrew MySQL on macOS:

```bash
brew services start mysql
```

Check:

```bash
brew services list | grep mysql
```

Test MySQL:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root
```

If your root account requires a password:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root -p
```

---

# 5. Create Python Virtual Environment

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Verify:

```bash
pip list
```

The project requires packages including:

```text
mysql-connector-python
pandas
faker
tabulate
flask
python-dotenv
```

---

# 6. Create the Five Databases

Run the schema files from the project root.

If `mysql` is available in PATH:

```bash
mysql -u root -p < laptop1_registration/schema.sql
mysql -u root -p < laptop2_insurance/schema.sql
mysql -u root -p < laptop3_rto/schema.sql
mysql -u root -p < laptop4_theft/schema.sql
mysql -u root -p < laptop5_mot/schema.sql
```

For Homebrew MySQL on macOS:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop1_registration/schema.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop2_insurance/schema.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop3_rto/schema.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop4_theft/schema.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop5_mot/schema.sql
```

If root requires a password, add `-p`.

---

# 7. Verify the Databases

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root -e "SHOW DATABASES;"
```

You should see:

```text
vehicle_registration_db
insurance_db
rto_db
theft_db
mot_db
```

Check tables:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root vehicle_registration_db -e "SHOW TABLES;"
/opt/homebrew/opt/mysql/bin/mysql -u root insurance_db -e "SHOW TABLES;"
/opt/homebrew/opt/mysql/bin/mysql -u root rto_db -e "SHOW TABLES;"
/opt/homebrew/opt/mysql/bin/mysql -u root theft_db -e "SHOW TABLES;"
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SHOW TABLES;"
```

Expected tables:

```text
vehicles
insurance_policies
rto_records
theft_records
mot_reports
```

---

# 8. Generate Synthetic Data

Run each generator **once**.

```bash
python laptop1_registration/generate_data.py
python laptop2_insurance/generate_data.py
python laptop3_rto/generate_data.py
python laptop4_theft/generate_data.py
```

The Ministry database does not need a data generator because reports are inserted by the Coordinator.

## Important

Do not repeatedly run the generators if they insert rows without clearing the table first, otherwise duplicate records may be created.

If you need to regenerate a table:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root vehicle_registration_db -e "TRUNCATE TABLE vehicles;"
/opt/homebrew/opt/mysql/bin/mysql -u root insurance_db -e "TRUNCATE TABLE insurance_policies;"
/opt/homebrew/opt/mysql/bin/mysql -u root rto_db -e "TRUNCATE TABLE rto_records;"
/opt/homebrew/opt/mysql/bin/mysql -u root theft_db -e "TRUNCATE TABLE theft_records;"
```

Then run the required generator again.

---

# 9. Verify Record Counts

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root vehicle_registration_db -e "SELECT COUNT(*) AS vehicles FROM vehicles;"
/opt/homebrew/opt/mysql/bin/mysql -u root insurance_db -e "SELECT COUNT(*) AS policies FROM insurance_policies;"
/opt/homebrew/opt/mysql/bin/mysql -u root rto_db -e "SELECT COUNT(*) AS rto_records FROM rto_records;"
/opt/homebrew/opt/mysql/bin/mysql -u root theft_db -e "SELECT COUNT(*) AS theft_records FROM theft_records;"
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SELECT COUNT(*) AS reports FROM mot_reports;"
```

The Ministry report table should initially contain:

```text
reports
-------
0
```

---

# 10. Create the Coordinator MySQL User

Run the Coordinator user SQL files.

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop1_registration/coordinator_user.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop2_insurance/coordinator_user.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop3_rto/coordinator_user.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop4_theft/coordinator_user.sql
/opt/homebrew/opt/mysql/bin/mysql -u root < laptop5_mot/coordinator_user.sql
```

If your root account requires a password, use `-p`.

The Coordinator account should have:

```text
SELECT → Registration DB
SELECT → Insurance DB
SELECT → RTO DB
SELECT → Theft DB
SELECT/INSERT/UPDATE → Ministry DB
```

---

# 11. Configure `.env`

Create `.env` in the project root:

```env
VEHICLES_HOST=localhost
INSURANCE_HOST=localhost
RTO_HOST=localhost
THEFT_HOST=localhost
MOT_HOST=localhost

DB_PORT=3306
COORDINATOR_USER=coordinator
COORDINATOR_PASSWORD=your_coordinator_password
```

For the single-machine setup, all five hosts are:

```text
localhost
```

Do not commit `.env` to Git.

---

# 12. Test Coordinator Database Access

Activate the environment:

```bash
source .venv/bin/activate
```

Go to the Coordinator directory:

```bash
cd coordinator
```

Test the configuration:

```bash
python -c "from config import DB_CONFIGS; print(DB_CONFIGS)"
```

Test the Coordinator login manually:

```bash
/opt/homebrew/opt/mysql/bin/mysql -h localhost -u coordinator -p vehicle_registration_db -e "SELECT COUNT(*) FROM vehicles;"
/opt/homebrew/opt/mysql/bin/mysql -h localhost -u coordinator -p insurance_db -e "SELECT COUNT(*) FROM insurance_policies;"
/opt/homebrew/opt/mysql/bin/mysql -h localhost -u coordinator -p rto_db -e "SELECT COUNT(*) FROM rto_records;"
/opt/homebrew/opt/mysql/bin/mysql -h localhost -u coordinator -p theft_db -e "SELECT COUNT(*) FROM theft_records;"
/opt/homebrew/opt/mysql/bin/mysql -h localhost -u coordinator -p mot_db -e "SELECT COUNT(*) FROM mot_reports;"
```

---

# 13. Build the Integrated Vehicle Master

From `coordinator/`:

```bash
python integration_engine.py
```

Expected result:

```text
INTEGRATED VEHICLE MASTER
Vehicles: 40
Cache: vehicle_master.pkl
```

The Coordinator:

1. Connects to all source databases.
2. Reads the heterogeneous schemas.
3. Normalizes vehicle identifiers.
4. Merges the information in memory.
5. Creates `vehicle_master.pkl`.

If source data changes, rebuild the master:

```bash
python integration_engine.py
```

---

# 14. Test Vehicle Queries

Run:

```bash
python query_tool.py
```

Enter a registration number when prompted.

## Test 1 — Insured and Clear

```text
DL01AB1001
```

Expected:

```text
Decision : OK — INSURED AND CLEAR
```

## Test 2 — Uninsured

```text
DL02AB1002
```

Expected:

```text
Decision : UNINSURED
```

and:

```text
UNINSURED — no policy on record
```

## Test 3 — Stolen + Expired Insurance

```text
DL03AB1003
```

Expected flags include:

```text
INSURANCE EXPIRED
VEHICLE FLAGGED: STOLEN
```

and:

```text
Theft Status : stolen
```

## Test 4 — Identifier Normalization

The Coordinator removes spaces and hyphens from vehicle identifiers.

For example:

```text
DL 04 AB 1004
```

should resolve to:

```text
DL04AB1004
```

This demonstrates integration across heterogeneous identifier formats.

---

# 15. Test Direct Database Data

Registration:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root vehicle_registration_db -e "SELECT * FROM vehicles LIMIT 5;"
```

Insurance:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root insurance_db -e "SELECT * FROM insurance_policies LIMIT 5;"
```

RTO:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root rto_db -e "SELECT * FROM rto_records LIMIT 5;"
```

Theft:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root theft_db -e "SELECT * FROM theft_records;"
```

Ministry reports:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SELECT * FROM mot_reports;"
```

---

# 16. Test Uninsured Vehicles Directly

Example query:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root -e "
SELECT v.reg_plate
FROM vehicle_registration_db.vehicles v
LEFT JOIN insurance_db.insurance_policies i
ON REPLACE(REPLACE(UPPER(v.reg_plate), ' ', ''), '-', '')
 = REPLACE(REPLACE(UPPER(i.vehicle_number), ' ', ''), '-', '')
WHERE i.vehicle_number IS NULL;
"
```

This identifies registration vehicles for which no matching insurance record exists.

---

# 17. Generate the Ministry Compliance Report

From `coordinator/`:

```bash
python generate_report.py
```

The Coordinator scans the integrated vehicle master and generates flags such as:

```text
UNINSURED
INSURANCE EXPIRED
VEHICLE FLAGGED: STOLEN
```

The report is:

1. Written to a CSV file.
2. Inserted into `mot_db.mot_reports`.

---

# 18. Verify the Ministry Report

Check the database:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SELECT * FROM mot_reports;"
```

Count reports:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SELECT COUNT(*) AS total_reports FROM mot_reports;"
```

Check reports for one vehicle:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db -e "SELECT * FROM mot_reports WHERE vehicle_plate='DL03AB1003';"
```

For `DL03AB1003`, there should be separate flags for:

```text
INSURANCE EXPIRED
VEHICLE FLAGGED: STOLEN
```

---

# 19. Run the Optional Flask Web Interface

From `coordinator/`:

```bash
python app.py
```

The terminal will display the local Flask address.

Open that address in a browser and test vehicle searches through the web interface.

Stop the server with:

```text
Ctrl+C
```

---

# 20. Complete End-to-End Test

A clean test sequence is:

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Go to Coordinator
cd coordinator

# 3. Rebuild integrated master
python integration_engine.py

# 4. Test vehicle queries
python query_tool.py

# 5. Generate Ministry report
python generate_report.py

# 6. Verify Ministry reports
/opt/homebrew/opt/mysql/bin/mysql -u root mot_db \
-e "SELECT * FROM mot_reports;"
```

---

# 21. Expected End-to-End Flow

```text
Five Heterogeneous MySQL Databases
                ↓
        Coordinator connects
                ↓
      Identifier normalization
                ↓
        Data integration
                ↓
     Integrated Vehicle Master
                ↓
        Vehicle 360° Query
                ↓
       Decision + Trust Score
                ↓
     Flag uninsured/suspicious
                ↓
      Ministry Compliance Report
                ↓
          mot_reports
```

---

# 22. Troubleshooting

### MySQL command not found

On Apple Silicon macOS:

```bash
/opt/homebrew/opt/mysql/bin/mysql --version
```

### MySQL is not running

```bash
brew services start mysql
```

### Check MySQL status

```bash
brew services list | grep mysql
```

### Python cannot find `mysql`

Make sure the virtual environment is active:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Python cannot find `dotenv`

```bash
pip install python-dotenv
```

### Coordinator cannot connect

Check:

```bash
python -c "from config import DB_CONFIGS; print(DB_CONFIGS)"
```

For the single-machine setup, every host should be:

```text
localhost
```

and the port should normally be:

```text
3306
```

### Integrated master is outdated

Rebuild it:

```bash
python integration_engine.py
```

### Accidentally generated duplicate data

Truncate the affected table and run its generator once:

```bash
/opt/homebrew/opt/mysql/bin/mysql -u root rto_db \
-e "TRUNCATE TABLE rto_records;"
```

Then:

```bash
python laptop3_rto/generate_data.py
```

---

## 23. Main Commands — Quick Reference

```bash
# Activate environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Generate data
python laptop1_registration/generate_data.py
python laptop2_insurance/generate_data.py
python laptop3_rto/generate_data.py
python laptop4_theft/generate_data.py

# Run from coordinator/
cd coordinator

# Build integration
python integration_engine.py

# Query vehicles
python query_tool.py

# Generate Ministry report
python generate_report.py

# Optional web application
python app.py
```

---

## 24. Demo Vehicles

| Vehicle      | Demonstrates               |
| ------------ | -------------------------- |
| `DL01AB1001` | Insured and clear          |
| `DL02AB1002` | Uninsured                  |
| `DL03AB1003` | Stolen + expired insurance |
| `DL04AB1004` | Identifier normalization   |
