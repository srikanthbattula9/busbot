import sqlite3
import json

conn = sqlite3.connect("busbot.db")
c = conn.cursor()

# ---------- Create tables ----------
c.execute("""
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    route TEXT,
    date TEXT,
    bus TEXT,
    seat TEXT,
    price_inr INTEGER,
    status TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS buses (
    bus_id TEXT PRIMARY KEY,
    route TEXT,
    operator TEXT,
    departure TEXT,
    price_inr INTEGER,
    seats_left INTEGER
)
""")

# ---------- Migrate existing JSON data in ----------
with open("customers.json") as f:
    data = json.load(f)

for customer in data["customers"]:
    c.execute("INSERT OR REPLACE INTO customers (id, name, phone) VALUES (?, ?, ?)",
               (customer["id"], customer["name"], customer["phone"]))
    for b in customer["bookings"]:
        c.execute("""INSERT INTO bookings (customer_id, route, date, bus, seat, price_inr, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (customer["id"], b["route"], b["date"], b["bus"], b["seat"], b["price_inr"], b["status"]))

with open("buses.json") as f:
    buses = json.load(f)

for bus in buses["available_buses"]:
    c.execute("""INSERT OR REPLACE INTO buses (bus_id, route, operator, departure, price_inr, seats_left)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (bus["bus_id"], bus["route"], bus["operator"], bus["departure"], bus["price_inr"], bus["seats_left"]))

conn.commit()
conn.close()
print("Database created and populated: busbot.db")