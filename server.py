import json
import anthropic
from datetime import date as date_type
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import sqlite3

TODAY = "2026-09-10"
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
client = anthropic.Anthropic()

# ---------- Database helpers ----------
def get_db():
    conn = sqlite3.connect("busbot.db")
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn

def find_customer(name):
    conn = get_db()
    row = conn.execute("SELECT * FROM customers WHERE name LIKE ?", (f"{name}%",)).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row["id"], "name": row["name"], "phone": row["phone"]}

def get_bookings(customer_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM bookings WHERE customer_id = ?", (customer_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def days_until(date_str):
    y, m, d = map(int, date_str.split("-"))
    ty, tm, td = map(int, TODAY.split("-"))
    return (date_type(y, m, d) - date_type(ty, tm, td)).days

def build_insights(customer_id):
    bookings = get_bookings(customer_id)
    insights = []
    reserved = [b for b in bookings if b["status"] == "reserved"]
    cancelled = [b for b in bookings if b["status"] == "cancelled"]
    for b in reserved:
        d = days_until(b["date"])
        if d < 0:
            insights.append(f"Their {b['route']} trip on {b['date']} has already passed.")
        elif d == 0:
            insights.append(f"URGENT: Their {b['route']} trip is TODAY.")
        elif d <= 2:
            insights.append(f"Their {b['route']} trip is in {d} day(s) — proactive check-in worth it.")
        elif d <= 7:
            insights.append(f"Their {b['route']} trip is coming up in {d} days.")
    if cancelled and not reserved:
        insights.append(f"They recently cancelled {cancelled[-1]['route']} and have nothing else booked.")
    return insights if insights else ["No urgent items."]

def book_bus(customer_id, bus_id, seat_preference, travel_date):
    conn = get_db()
    bus = conn.execute("SELECT * FROM buses WHERE bus_id = ?", (bus_id,)).fetchone()
    if not bus:
        conn.close()
        return "FAILED: bus_id not found."
    if bus["seats_left"] <= 0:
        conn.close()
        return "FAILED: no seats left."
    conn.execute("UPDATE buses SET seats_left = seats_left - 1 WHERE bus_id = ?", (bus_id,))
    conn.execute("""INSERT INTO bookings (customer_id, route, date, bus, seat, price_inr, status)
                     VALUES (?, ?, ?, ?, ?, ?, 'reserved')""",
                (customer_id, bus["route"], travel_date, bus["operator"], seat_preference, bus["price_inr"]))
    conn.commit()
    new_seats = bus["seats_left"] - 1
    conn.close()
    return f"SUCCESS: Reserved {bus['operator']} on {travel_date}, seat {seat_preference}, Rs.{bus['price_inr']}. Seats left: {new_seats}"

def cancel_booking(customer_id, route, travel_date):
    conn = get_db()
    booking = conn.execute("""SELECT * FROM bookings WHERE customer_id = ? AND route LIKE ?
                               AND date = ? AND status = 'reserved'""",
                           (customer_id, f"%{route}%", travel_date)).fetchone()
    if not booking:
        conn.close()
        return "FAILED: no matching booking."
    conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking["id"],))
    conn.execute("UPDATE buses SET seats_left = seats_left + 1 WHERE operator = ? AND route = ?",
                (booking["bus"], booking["route"]))
    conn.commit()
    conn.close()
    return f"SUCCESS: Cancelled. Refund Rs.{booking['price_inr']} in 5-7 days."

def search_buses(route_query):
    conn = get_db()
    rows = conn.execute("SELECT * FROM buses WHERE route LIKE ?", (f"%{route_query}%",)).fetchall()
    conn.close()
    if not rows:
        return f"No matches for '{route_query}'."
    return json.dumps([dict(r) for r in rows], indent=2)

# ---------- Tool definitions for the AI ----------
tools = [
    {"name": "book_bus", "description": "Reserve a bus. Only after clear confirmation of bus AND date.",
     "input_schema": {"type": "object", "properties": {
        "bus_id": {"type": "string"}, "seat_preference": {"type": "string"}, "travel_date": {"type": "string"}},
        "required": ["bus_id", "seat_preference", "travel_date"]}},
    {"name": "cancel_booking", "description": "Cancel a reserved booking.",
     "input_schema": {"type": "object", "properties": {
        "route": {"type": "string"}, "travel_date": {"type": "string"}},
        "required": ["route", "travel_date"]}},
    {"name": "search_buses", "description": "Search inventory by route or city.",
     "input_schema": {"type": "object", "properties": {"route_query": {"type": "string"}},
        "required": ["route_query"]}}
]

def run_tool(customer_id, name, inputs):
    if name == "book_bus":
        return book_bus(customer_id, inputs["bus_id"], inputs["seat_preference"], inputs["travel_date"])
    if name == "cancel_booking":
        return cancel_booking(customer_id, inputs["route"], inputs["travel_date"])
    if name == "search_buses":
        return search_buses(inputs["route_query"])

def make_system_prompt(customer):
    bookings = get_bookings(customer["id"])
    insights = build_insights(customer["id"])
    return f"""You are Maya, RedBus's travel assistant, speaking with {customer['name']}.
Today's date: {TODAY}.
BOOKING HISTORY: {json.dumps(bookings, indent=2)}
NOTICED: {chr(10).join('- ' + i for i in insights)}
RULES: Only offer real buses via search_buses. Never invent. Confirm before booking/cancelling. No emojis."""

# ---------- Per-customer conversation memory ----------
conversations = {}  # {customer_id: [messages]}

# ---------- API request/response shapes ----------
class ChatRequest(BaseModel):
    customer_name: str
    message: str

class ChatResponse(BaseModel):
    reply: str

# ---------- THE ENDPOINT ----------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    customer = find_customer(req.customer_name)
    if not customer:
        return ChatResponse(reply="Unknown caller.")

    cid = customer["id"]
    if cid not in conversations:
        conversations[cid] = []
    messages = conversations[cid]

    messages.append({"role": "user", "content": req.message})
    system_prompt = make_system_prompt(customer)

    response = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=500,
        system=system_prompt, tools=tools, messages=messages
    )

    while response.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                result = run_tool(cid, block.name, block.input)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": results})
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=500,
            system=system_prompt, tools=tools, messages=messages
        )

    reply = "".join(b.text for b in response.content if b.type == "text")
    messages.append({"role": "assistant", "content": response.content})
    return ChatResponse(reply=reply)

@app.get("/")
def home():
    return {"status": "Maya is running"}

@app.get("/chatui")
def chat_ui():
    return FileResponse("static/index.html")