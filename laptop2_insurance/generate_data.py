import mysql.connector
from datetime import date, timedelta

PASSWORD = ""
PLATES = [f"DL{str(i).zfill(2)}AB{1000+i}" for i in range(1, 41)]

# 1002/1007: no policy
# 1003/1006: expired
# 1004: active policy but formatted with spaces
today = date.today()

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=PASSWORD,
    database="insurance_db",
)
cur = conn.cursor()

insurers = ["ICICI Lombard", "HDFC Ergo", "Bajaj Allianz", "TATA AIG"]

for i, plate in enumerate(PLATES, start=1):
    if i in {2, 7, 12, 17, 22, 27, 32, 37}:
        continue

    if i in {3, 6, 13, 23}:
        start = today - timedelta(days=700)
        end = today - timedelta(days=30)
    else:
        start = today - timedelta(days=60)
        end = today + timedelta(days=300)

    stored_plate = "DL 01 AB 1004" if i == 4 else plate

    cur.execute(
        """
        INSERT INTO insurance_policies
        (vehicle_number, insurer_name, policy_no, policy_start_date,
         policy_end_date, premium_amount)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (stored_plate, insurers[(i-1) % len(insurers)], f"POL-{i:07d}",
         start, end, 5000 + i * 250)
    )

conn.commit()
cur.close()
conn.close()
print("Insurance seed complete.")
