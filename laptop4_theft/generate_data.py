import mysql.connector
from datetime import date, timedelta
import os
from dotenv import load_dotenv
from faker import Faker

load_dotenv()

PASSWORD = os.getenv("MYSQL_ROOT_PASSWORD")

fake = Faker()

cases = [
    ("DL01AB1003", "stolen"),
    ("DL01AB1008", "recovered"),
    ("DL01AB1015", "shredded"),
    ("DL01AB1025", "stolen"),
]

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=PASSWORD,
    database="theft_db",
)
cur = conn.cursor()

for i, (plate, status) in enumerate(cases, start=1):
    theft_date = date.today() - timedelta(days=100 + i * 20)
    shredded_date = date.today() - timedelta(days=10) if status == "shredded" else None

    cur.execute(
        """
        INSERT INTO theft_records
        (plate_no, theft_date, status, shredded_date)
        VALUES (%s,%s,%s,%s)
        """,
        (plate, theft_date, status, shredded_date)
    )

conn.commit()
cur.close()
conn.close()
print(f"Inserted {len(cases)} theft/shredding records.")
