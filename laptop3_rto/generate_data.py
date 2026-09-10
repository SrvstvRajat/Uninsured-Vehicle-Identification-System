import mysql.connector
from datetime import date, timedelta

PASSWORD = ""
PLATES = [f"DL{str(i).zfill(2)}AB{1000+i}" for i in range(1, 41)]

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=PASSWORD,
    database="rto_db",
)
cur = conn.cursor()

offices = ["RTO Delhi Central", "RTO Delhi North", "RTO Delhi South"]

for i, plate in enumerate(PLATES, start=1):
    stored_plate = plate
    if i in {4, 14, 24, 34}:
        stored_plate = f"{plate[:2]}-{plate[2:4]}-{plate[4:6]}-{plate[6:]}"

    registration_date = date.today() - timedelta(days=1000 + i * 10)
    renewal_date = date.today() + timedelta(days=100 + i)

    cur.execute(
        """
        INSERT INTO rto_records
        (car_id, registration_date, renewal_date, rto_office)
        VALUES (%s,%s,%s,%s)
        """,
        (stored_plate, registration_date, renewal_date, offices[(i-1) % len(offices)])
    )

# Data-quality anomaly: RTO knows about a vehicle that is absent
# from the main vehicle registration/description source.
cur.execute(
    """
    INSERT INTO rto_records
    (car_id, registration_date, renewal_date, rto_office)
    VALUES (%s,%s,%s,%s)
    """,
    ("DL99ZZ9998", date.today() - timedelta(days=400),
     date.today() + timedelta(days=200), "RTO Delhi Central")
)

conn.commit()
cur.close()
conn.close()
print("Inserted 40 normal RTO records + 1 RTO-only anomaly.")
