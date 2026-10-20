# Four Simple Laptop UIs

Each source laptop now has a small Flask UI that talks only to its own local MySQL database. The UIs are intentionally read-only so they do not bypass the existing Coordinator permissions or alter the federation architecture.

## Setup on each laptop

From that laptop's folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask mysql-connector-python python-dotenv
```

Set the local database credentials before starting. Example:

```bash
export DB_USER=root
export DB_PASSWORD='YOUR_MYSQL_PASSWORD'
export DB_HOST=127.0.0.1
export DB_PORT=3306
```

Then run:

- Laptop 1: `python3 app.py` → http://localhost:5001
- Laptop 2: `python3 app.py` → http://localhost:5002
- Laptop 3: `python3 app.py` → http://localhost:5003
- Laptop 4: `python3 app.py` → http://localhost:5004

The app searches the exact vehicle identifier used by that source schema:

- Laptop 1: `reg_plate`
- Laptop 2: `vehicle_number`
- Laptop 3: `car_id`
- Laptop 4: `plate_no`

For the distributed demo, keep MySQL on each laptop and point the Coordinator's `.env` hosts to the four laptop IP addresses. The Coordinator/mediator remains responsible for federation and Vehicle 360.
