# BusBot 🚌

A context-aware AI customer service agent for bus bookings, built with Python and Claude.

Unlike typical chatbots, BusBot knows the caller before they explain anything — their booking history, upcoming trips, past cancellations — and acts on real inventory, never inventing buses, prices, or times.

## Features
- Identifies caller and greets them using their real booking history
- Books real seats against live inventory (grounded, no hallucination)
- Cancels bookings and processes refunds, returning seats to inventory
- Searches routes naturally ("any buses from Pune?")
- Persists all state across sessions (JSON-backed)

## Stack
Python, Anthropic Claude API (tool use / agents)

## Run it
\`\`\`bash
pip install anthropic
export ANTHROPIC_API_KEY="your-key"
python bot.py
\`\`\`
