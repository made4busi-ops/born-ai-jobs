#!/usr/bin/env python3
"""NeverX008 v1 - The Pen. Claude-powered writer. Guarded, metered, never sends.
Now reads from the Ledger and writes drafts back to it."""

import os
import sys
import json
import re
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
FUEL_LOG = os.path.join(BASE_DIR, "fuel_log.json")
DB_PATH = os.path.join(BASE_DIR, "data", "leads.db")

from dotenv import load_dotenv
load_dotenv(ENV_PATH)
import anthropic

# ============================================================
# FUEL GAUGE
# ============================================================
def load_fuel():
    if os.path.exists(FUEL_LOG):
        with open(FUEL_LOG) as f: return json.load(f)
    return {"total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0, "estimated_cost_usd": 0.0, "history": []}

def save_fuel(fuel):
    with open(FUEL_LOG, "w") as f: json.dump(fuel, f, indent=2)

def log_fuel(usage, model):
    fuel = load_fuel()
    cost = (usage.input_tokens * 3.0 / 1_000_000) + (usage.output_tokens * 15.0 / 1_000_000)
    fuel["total_calls"] += 1
    fuel["total_tokens_in"] += usage.input_tokens
    fuel["total_tokens_out"] += usage.output_tokens
    fuel["estimated_cost_usd"] = round(fuel["estimated_cost_usd"] + cost, 6)
    fuel["history"].append({"timestamp": datetime.now().isoformat(), "cost_usd": round(cost, 6)})
    save_fuel(fuel)
    return fuel

# ============================================================
# THE MONSTER
# ============================================================
def monster_check(text):
    violations = []
    lower = text.lower()
    for pattern in [r'\[.*?(your|name|insert|here|fill|placeholder).*?\]', r'\{.*?(your|name|insert|here|fill).*?\}']:
        for m in re.findall(pattern, lower, re.IGNORECASE): violations.append(f"Placeholder found: {m}")
    for phrase in ["as an ai", "i cannot", "i can't", "i'm sorry", "as a language model", "i don't have access"]:
        if phrase in lower: violations.append(f"AI leakage: '{phrase}'")
    wc = len(text.split())
    if wc < 50: violations.append(f"Too short: {wc} words (min 50)")
    if wc > 300: violations.append(f"Too long: {wc} words (max 300)")
    if not any(w in lower for w in ["call", "reply", "text", "email", "reach", "contact", "respond", "let's", "let me", "shoot me"]):
        violations.append("No call to action found")
    return violations

# ============================================================
# THE PEN
# ============================================================
SYSTEM_PROMPT = """You are The Pen — a direct-mail copywriter for Born AI Jobs.
You write short, punchy pitches to small business owners (landlords, Airbnb hosts, florists, etc.) offering them a custom video commercial.

Your voice:
- Write like a real person talking to a real person. No corporate speak.
- 100-200 words. Every word earns its place.
- Address the owner by name if known.
- Reference ONE specific detail about their business (from the lead).
- Be direct, not desperate. You're offering value, not begging.
- End with ONE clear call to action.

Forbidden:
- Never use placeholders like [YOUR NAME] or {INSERT}. Write around what you don't know.
- Never mention AI, Claude, automation, or that this was generated.
- Never apologize or hedge ("I'm sorry if this is unwanted").
- Never use "revolutionary", "game-changing", or "synergy".

Write the pitch now. Plain text. No subject line. No headers. Just the message."""

def write_pitch(lead):
    client = anthropic.Anthropic()
    model = "claude-sonnet-4-5-20250929"
    
    user_prompt = f"""Write a pitch to this business owner:
Name: {lead.get('name', 'the owner')}
Business: {lead.get('business', 'a local business')}
Platform: {lead.get('platform', 'online')}
Details: {lead.get('details', 'No additional details available.')}
Write the pitch now."""

    try:
        response = client.messages.create(model=model, max_tokens=600, system=SYSTEM_PROMPT, messages=[{"role": "user", "content": user_prompt}])
    except anthropic.APIError as e:
        return {"status": "ERROR", "error": str(e)}

    fuel = log_fuel(response.usage, model)
    text = response.content[0].text.strip()
    violations = monster_check(text)

    if violations:
        return {"status": "REJECTED", "violations": violations, "raw_output": text, "fuel": fuel}
    
    return {"status": "DRAFT", "pitch": text, "word_count": len(text.split()), "fuel": fuel}

# ============================================================
# LEDGER CONNECTION
# ============================================================
def get_next_lead():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE status='NEW' ORDER BY created_at LIMIT 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_pitch_to_ledger(lead_id, pitch_text):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO pitches (lead_id, pitch_text, status) VALUES (?, ?, 'DRAFT')", (lead_id, pitch_text))
    c.execute("UPDATE leads SET status='PITCHED' WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()

# ============================================================
# MAIN RUNNER
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("NEVERX008 v1 - THE PEN (Live Ledger Run)")
    print("=" * 60)
    
    lead = get_next_lead()
    if not lead:
        print("No NEW leads in the Ledger. The Pen is resting.")
        sys.exit(0)
        
    print(f"Found Lead ID {lead['id']}: {lead['name']} - {lead['business']}")
    print("-" * 60)
    
    result = write_pitch(lead)
    f = result.get("fuel", load_fuel())
    
    if result["status"] == "DRAFT":
        print("STATUS: DRAFT  (monster passed)")
        print(f"WORDS: {result['word_count']}")
        print("-" * 60)
        print(result["pitch"])
        print("-" * 60)
        save_pitch_to_ledger(lead["id"], result["pitch"])
        print(f"\n[LEDGER] Pitch saved for Lead ID {lead['id']}. Status updated to PITCHED.")
        print(f"FUEL: {f['total_calls']} call(s) | ${f['estimated_cost_usd']:.4f} spent total")
    elif result["status"] == "REJECTED":
        print("STATUS: REJECTED  (monster caught violations)")
        for v in result["violations"]: print(f"  X {v}")
        print("-" * 60)
        print(result["raw_output"])
        print(f"\nFUEL: {f['total_calls']} call(s) | ${f['estimated_cost_usd']:.4f} spent total")
    else:
        print(f"STATUS: ERROR\n  {result['error']}")
