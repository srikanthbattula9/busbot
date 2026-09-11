import json
import anthropic
from datetime import date

TODAY = "2026-09-10"

# ---------- Load data ----------
with open("customers.json") as f:
    data = json.load(f)
with open("buses.json") as f:
    buses = json.load(f)

# ---------- Who is calling ----------
name = input("Who is calling? ").strip()

found = None
for customer in data["customers"]:
    if name.lower() in customer["name"].lower():
        found = customer
        break

if not found:
    print("Unknown caller.")
    exit()

from datetime import date as date_type

def days_until(date_str):
    y, m, d = map(int, date_str.split("-"))
    today_y, today_m, today_d = map(int, TODAY.split("-"))
    return (date_type(y, m, d) - date_type(today_y, today_m, today_d)).days

def build_insights(customer):
    insights = []
    reserved = [b for b in customer["bookings"] if b["status"] == "reserved"]
    cancelled = [b for b in customer["bookings"] if b["status"] == "cancelled"]

    for b in reserved:
        d = days_until(b["date"])
        if d < 0:
            insights.append(f"Their {b['route']} trip on {b['date']} has already passed — status may need updating.")
        elif d == 0:
            insights.append(f"URGENT: Their {b['route']} trip is TODAY.")
        elif d <= 2:
            insights.append(f"Their {b['route']} trip is in {d} day(s) — worth a proactive check-in.")
        elif d <= 7:
            insights.append(f"Their {b['route']} trip is coming up in {d} days.")

    if cancelled and not reserved:
        insights.append(f"They recently cancelled their {cancelled[-1]['route']} trip and have nothing else booked — a good moment to offer to rebook.")

    routes = [b["route"] for b in customer["bookings"]]
    if len(routes) != len(set(routes)):
        insights.append("They've booked the same route more than once — likely a regular on this route, mention it feels familiar.")

    return insights if insights else ["No urgent items. Standard friendly greeting."]

# ---------- TOOLS: your code does the real work ----------

def save_all():
    with open("customers.json", "w") as f:
        json.dump(data, f, indent=2)
    with open("buses.json", "w") as f:
        json.dump(buses, f, indent=2)

def book_bus(bus_id, seat_preference, travel_date):
    for bus in buses["available_buses"]:
        if bus["bus_id"] == bus_id:
            if bus["seats_left"] <= 0:
                return "FAILED: no seats left on this bus."
            bus["seats_left"] -= 1
            found["bookings"].append({
                "route": bus["route"],
                "date": travel_date,
                "bus": bus["operator"],
                "seat": seat_preference,
                "price_inr": bus["price_inr"],
                "status": "reserved"
            })
            save_all()
            return f"SUCCESS: Reserved {bus['operator']} ({bus['route']}) on {travel_date}, seat: {seat_preference}, Rs.{bus['price_inr']}. Seats left: {bus['seats_left']}"
    return "FAILED: bus_id not found."

def cancel_booking(route, travel_date):
    for b in found["bookings"]:
        if route.lower() in b["route"].lower() and b["date"] == travel_date and b["status"] == "reserved":
            b["status"] = "cancelled"
            for bus in buses["available_buses"]:
                if bus["operator"] == b["bus"] and bus["route"] == b["route"]:
                    bus["seats_left"] += 1
            save_all()
            return f"SUCCESS: Cancelled {b['bus']} on {travel_date}. Refund Rs.{b['price_inr']} in 5-7 business days."
    return "FAILED: no matching reserved booking for that route and date."

def search_buses(route_query):
    matches = [b for b in buses["available_buses"] if route_query.lower() in b["route"].lower()]
    if not matches:
        return f"No buses found matching '{route_query}'. Available routes: " + ", ".join(sorted(set(b["route"] for b in buses["available_buses"])))
    return json.dumps(matches, indent=2)

TOOL_FUNCTIONS = {
    "book_bus": lambda i: book_bus(i["bus_id"], i["seat_preference"], i["travel_date"]),
    "cancel_booking": lambda i: cancel_booking(i["route"], i["travel_date"]),
    "search_buses": lambda i: search_buses(i["route_query"]),
}

tools = [
    {
        "name": "book_bus",
        "description": "Reserve a bus. Only after the customer clearly confirms bus AND travel date.",
        "input_schema": {"type": "object", "properties": {
            "bus_id": {"type": "string", "description": "bus_id from inventory, e.g. B003"},
            "seat_preference": {"type": "string", "description": "window, aisle, or any"},
            "travel_date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["bus_id", "seat_preference", "travel_date"]}
    },
    {
        "name": "cancel_booking",
        "description": "Cancel a reserved booking. Only after customer clearly confirms, and confirm WHICH booking if they have several.",
        "input_schema": {"type": "object", "properties": {
            "route": {"type": "string", "description": "route of booking to cancel"},
            "travel_date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["route", "travel_date"]}
    },
    {
        "name": "search_buses",
        "description": "Search current bus inventory by route or city name. Use this to answer ANY availability question instead of memory.",
        "input_schema": {"type": "object", "properties": {
            "route_query": {"type": "string", "description": "city or route text, e.g. 'Pune' or 'Hyderabad to Vizag'"}},
            "required": ["route_query"]}
    }
]
insights = build_insights(found)
system_prompt = f"""You are Maya, RedBus's personal travel assistant, on a call with {found['name']}.
Today's date: {TODAY}.

CUSTOMER'S FULL BOOKING HISTORY (oldest to newest):
{json.dumps(found['bookings'], indent=2)}

THINGS YOU'VE NOTICED ABOUT THIS CUSTOMER (weave ONE into your opening naturally, don't list them):
{chr(10).join('- ' + i for i in insights)}

PERSONALITY:
- Warm, human, brief — like a great phone agent, not a form. No emojis.
- Use their name naturally, not constantly.
- Notice things: upcoming trips soon ("your Vizag trip is in 2 days — all set?"), repeated routes, their usual seat choice — and mention ONE such observation in your first reply.
- After any completed booking, offer ONE smart follow-up (return trip, or note their usual preference).

RULES:
- NEVER invent buses, times, or prices. Use search_buses for ALL availability questions.
- Book only after clear confirmation of bus + travel date. Ask for date if missing; convert natural dates ("25th sep") using today's date.
- Cancel only after clear confirmation; if multiple bookings, confirm which.
- Report tool results honestly, including failures.
- If a request is impossible (no such route), say so plainly and offer what exists."""

client = anthropic.Anthropic()
messages = []

# ---------- Opening greeting: Maya speaks FIRST ----------
messages.append({"role": "user", "content": "[The customer has just connected to the call. Greet them.]"})
response = client.messages.create(
    model="claude-sonnet-4-6", max_tokens=500,
    system=system_prompt, tools=tools, messages=messages
)
greeting = "".join(b.text for b in response.content if b.type == "text")
print(f"\nMaya: {greeting}\n")
messages.append({"role": "assistant", "content": response.content})

# ---------- Chat loop ----------
while True:
    user_input = input(f"{found['name']}: ").strip()
    if user_input == "":
        continue
    if user_input.lower() in ["bye", "quit", "exit"]:
        print("Maya: Thank you for calling RedBus. Safe travels!")
        break
    messages.append({"role": "user", "content": user_input})
    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=500,
        system=system_prompt, tools=tools, messages=messages
    )

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"\n[System: {block.name} → {block.input}]")
                result = TOOL_FUNCTIONS[block.name](block.input)
                print(f"[System: {result}]\n")
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=500,
            system=system_prompt, tools=tools, messages=messages
        )

    reply = "".join(b.text for b in response.content if b.type == "text")
    print(f"Maya: {reply}\n")
    messages.append({"role": "assistant", "content": response.content})