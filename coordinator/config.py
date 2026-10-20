import os

from dotenv import load_dotenv

# Load variables from the project's .env file
load_dotenv()


COORDINATOR_USER = os.getenv("COORDINATOR_USER")
COORDINATOR_PASSWORD = os.getenv("COORDINATOR_PASSWORD")
DB_PORT = int(os.getenv("DB_PORT", "3306"))


DB_CONFIGS = {
    "vehicles": {
        "host": os.getenv("VEHICLES_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "vehicle_registration_db",
    },
    "insurance": {
        "host": os.getenv("INSURANCE_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "insurance_db",
    },
    "rto": {
        "host": os.getenv("RTO_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "rto_db",
    },
    "theft": {
        "host": os.getenv("THEFT_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "theft_db",
    },
    "mot": {
        "host": os.getenv("MOT_HOST"),
        "port": DB_PORT,
        "user": COORDINATOR_USER,
        "password": COORDINATOR_PASSWORD,
        "database": "mot_db",
    },
}


SOURCE_NAMES = {
    "vehicles": "Vehicle Registration / Description",
    "insurance": "Insurance",
    "rto": "RTO / Registration Authority",
    "theft": "Theft & Shredding",
}