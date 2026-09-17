import os

from dotenv import load_dotenv

# Load variables from the project's .env file
load_dotenv()


COORDINATOR_USER = os.getenv("COORDINATOR_USER")
COORDINATOR_PASSWORD = os.getenv("COORDINATOR_PASSWORD")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

# Fail fast instead of hanging when a source DB is unreachable at the
# network level (host down, firewalled, etc). Without this, a dead host
# can block on the TCP connect for a long time (OS-level timeout),
# which stalls the whole request.
DB_CONNECT_TIMEOUT = 3  # seconds


DB_CONFIGS = {
    "vehicles": {
        "host": os.getenv("VEHICLES_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "vehicle_registration_db",
        "connection_timeout": DB_CONNECT_TIMEOUT,
    },
    "insurance": {
        "host": os.getenv("INSURANCE_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "insurance_db",
        "connection_timeout": DB_CONNECT_TIMEOUT,
    },
    "rto": {
        "host": os.getenv("RTO_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "rto_db",
        "connection_timeout": DB_CONNECT_TIMEOUT,
    },
    "theft": {
        "host": os.getenv("THEFT_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "theft_db",
        "connection_timeout": DB_CONNECT_TIMEOUT,
    },
    "mot": {
        "host": os.getenv("MOT_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "mot_db",
        "connection_timeout": DB_CONNECT_TIMEOUT,
    },
}


SOURCE_NAMES = {
    "vehicles": "Vehicle Registration / Description",
    "insurance": "Insurance",
    "rto": "RTO / Registration Authority",
    "theft": "Theft & Shredding",
}