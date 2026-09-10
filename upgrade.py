import json

with open("customers.json") as f:
    data = json.load(f)

for customer in data["customers"]:
    if "last_booking" in customer:
        # Turn the single booking into a list with one item
        customer["bookings"] = [customer["last_booking"]]
        del customer["last_booking"]

with open("customers.json", "w") as f:
    json.dump(data, f, indent=2)

print("Upgraded! Every customer now has a bookings list.")