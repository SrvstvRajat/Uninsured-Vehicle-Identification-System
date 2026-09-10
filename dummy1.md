# Project 1 — Identification of Uninsured Vehicles

This implementation follows the uploaded guide's architecture:

- Laptop 1 → Vehicle Registration / Description DB
- Laptop 2 → Insurance Details DB
- Laptop 3 → RTO / Registration Authority DB
- Laptop 4 → Theft & Shredding DB
- Laptop 5 → Ministry of Transportation Reports DB
- Coordinator laptop → Python integration engine

Each database laptop runs its own MySQL database. The Coordinator communicates with the five
database laptops over the network.

If only five laptops are available, one laptop can also run the Coordinator.

## Flow

Camera/vehicle query
→ Coordinator
→ remote source databases
→ normalization
→ entity resolution
→ integration
→ decision
→ Ministry report
→ Laptop 5

## Setup

1. Install MySQL Server on laptops 1–5.
2. Run the relevant `schema.sql` on each laptop.
3. Run `generate_data.py` on laptops 1–4.
4. Create the `coordinator` MySQL user using `coordinator_user.sql`.
5. Enable remote MySQL access and firewall port 3306.
6. Put the real IP addresses and coordinator password in `coordinator/config.py`.
7. On the Coordinator:

```bash
pip install -r requirements.txt
cd coordinator
python integration_engine.py
python query_tool.py
```

8. Generate the Ministry report:

```bash
python generate_report.py
```

This creates `ministry_report.csv` and writes the same report rows to Laptop 5's `mot_reports`
table over the network.

## Optional browser UI

From `coordinator/`:

```bash
python app.py
```

Then open:

```text
http://COORDINATOR_IP:5000
```

## Demonstration plates

- `DL01AB1001` → insured and clear
- `DL01AB1002` → no insurance row
- `DL01AB1003` → expired insurance + stolen
- `DL-01-AB-1004` → formatting mismatch, but should resolve correctly
- `DL01AB1015` → shredded
- `DL99ZZ9999` → nonexistent
- `DL99ZZ9998` → RTO-only anomaly

The data is deterministic so the same demo cases can be reproduced.

## Important

Laptop 5 is an output/report destination. It is not treated as one of the vehicle-information
sources during integration. This matches the guide's flow: the Coordinator reads the source
databases and writes flagged compliance reports to the Ministry database.
