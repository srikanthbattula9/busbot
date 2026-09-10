import json

# Read the customer file
with open("customers.json") as f:
    data = json.load(f)

# Ask who is calling
name = input("Who is calling? ")

# Search for them
found = None
for customer in data["customers"]:
    if name.lower() in customer["name"].lower():
        found = customer
        break

# Show what we know
if found:
    booking = found["last_booking"]
    print(f"\nCaller identified: {found['name']}")
    print(f"Last booking: {booking['route']} on {booking['date']}")
    print(f"Bus: {booking['bus']}, Seat {booking['seat']}")
    print(f"Status: {booking['status']}")
else:
    print("\nUnknown caller.")