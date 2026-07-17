#!/usr/bin/env python3
"""NeverX004 v1 - The Logic Brain (Claude Haiku Mini-Me v2).
Specialty: Structural precision, rule-following, factual analysis.
Reads config.json. Enforces Honesty Law. Monster guard checks output.
"""
import os, sys, json, re, sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
FUEL_LOG = os.path.join(BASE_DIR, "fuel_log.json")
DB_PATH = os.path.join(BASE_DIR, "data", "leads.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

from dotenv import load_dotenv
load_dotenv(ENV_PATH)
import anthropic

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f: return json.load(f)
    return {"business_name": "UNKNOWN", "sender_name": "UNKNOWN", "phone": "UNKNOWN", "email": "UNKNOWN", "approved_statistics": []}

def load_fuel():
    if os.path.exists(FUEL_LOG):
        with open(FUEL_LOG) as f: return json.load(f)
    return {"total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0, "estimated_cost_usd": 0.0, "history": []}

def save_fuel(fuel):
    with open(FUEL_LOG, "w") as f: json.dump(fuel, f, indent=2)

def log_fuel(usage, model):
    fuel = load_fuel()
    cost = (usage.input_tokens / 1_000_000) * 1.00 + (usage.output_tokens / 1_000_000) * 5.00
    fuel["total_calls"] += 1
    fuel["total_tokens_in"] += usage.input_tokens
    fuel["total_tokens_out"] += usage.output_tokens
    fuel["estimated_cost_usd"] = round(fuel["estimated_cost_usd"] + cost, 6)
    fuel["history"].append({"timestamp": datetime.now().isoformat(), "agent": "X004", "cost_usd": round(cost, 6)})
    fuel["history"] = fuel["history"][-100:]
    save_fuel(fuel)

def monster_check(text, config):
    if '[' in text or '{' in text or 'TODO' in text.upper(): return False, "Placeholder detected"
    if len(text.split()) < 50: return False, "Too short"
    ai_phrases = ['as an ai', 'i cannot', 'i apologize', 'here is a', 'certainly!', 'of course!', "i'm sorry"]
    for phrase in ai_phrases:
        if phrase in text.lower(): return False, f"AI leakage: '{phrase}'"
    
    phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
    real_phone = re.sub(r'\D', '', config.get('phone', ''))[-10:]
    for phone in re.findall(phone_pattern, text):
        if re.sub(r'\D', '', phone)[-10:] != real_phone: return False, f"Fake phone detected: {phone}"
            
    approved_stats = [s.lower().strip() for s in config.get('approved_statistics', [])]
    for pattern in [r'\d+%', r'\d+ out of \d+', r'\d+ in \d+', r'\d+ percent']:
        for stat in re.findall(pattern, text.lower()):
            if not any(stat in a or a in stat for a in approved_stats): return False, f"Unapproved statistic: '{stat}'"
    return True, "passed"

def write_pitch(lead, config):
    client = anthropic.Anthropic()
    system_prompt = f"""You are NeverX004, the Logic Brain. You analyze facts and write with structural precision.
    HONESTY LAW: Sign as {config['sender_name']}, Business: {config['business_name']}, Phone: {config['phone']}, Email: {config['email']}.
    ONLY use stats from this approved list: {config.get('approved_statistics', ['none'])}. No invented numbers. No fluff. Strict logic."""
    
    user_msg = f"""Write a pitch to: {lead['name']} ({lead['business']}). Details: {lead['details']}."""
    
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}]
    )
    log_fuel(response.usage, "claude-3-5-haiku-20241022")
    return response.content[0].text.strip()

def main():
    print("="*60)
    print("NEVERX004 v1 - THE LOGIC BRAIN")
    print("="*60)
    config = load_config()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM leads WHERE id = 1") # Test on Marcus
    lead = dict(c.fetchone())
    
    print(f"Targeting Lead: {lead['name']} - {lead['business']}")
    print("-"*60)
    
    pitch = write_pitch(lead, config)
    passed, reason = monster_check(pitch, config)
    
    if not passed:
        print(f"[MONSTER] REJECTED: {reason}\n")
        print(pitch)
        return
        
    c.execute("INSERT INTO pitches (lead_id, pitch_text, status) VALUES (?, ?, 'DRAFT')", (lead['id'], pitch))
    conn.commit()
    
    print(f"STATUS: DRAFT (Monster passed - Logic applied)\n")
    print(pitch)
    print("\n" + "="*60)
    conn.close()

if __name__ == "__main__":
    main()
