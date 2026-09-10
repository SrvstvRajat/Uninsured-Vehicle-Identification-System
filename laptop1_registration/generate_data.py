import mysql.connector
from faker import Faker

PASSWORD = ""
fake = Faker()

PLATES = [f"DL{str(i).zfill(2)}AB{1000+i}" for i in range(1, 41)]
vehicles = [
    ("Maruti", "Swift", "White"),
    ("Hyundai", "i20", "Blue"),
    ("Tata", "Nexon", "Red"),
    ("Honda", "City", "Black"),
    ("Toyota", "Innova", "Silver"),
    ("Kia", "Seltos", "Grey"),
]

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password=PASSWORD,
    database="vehicle_registration_db",
)
cur = conn.cursor()

for i, plate in enumerate(PLATES):
    make, model, color = vehicles[i % len(vehicles)]
    cur.execute(
        """
        INSERT INTO vehicles
        (reg_plate, make, model, color, owner_name, engine_no, chassis_no)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
        make=VALUES(make), model=VALUES(model), color=VALUES(color),
        owner_name=VALUES(owner_name), engine_no=VALUES(engine_no),
        chassis_no=VALUES(chassis_no)
        """,
        (plate, make, model, color, fake.name(), f"ENG{1000000+i}", f"CHS{100000000+i}")
    )

conn.commit()
cur.close()
conn.close()
print(f"Inserted/verified {len(PLATES)} vehicles.")
