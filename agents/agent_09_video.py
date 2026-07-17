#!/usr/bin/env python3
"""NeverX009 v1 - The Movie Studio. 

Kling is just a camera. X009 is the Director.
Reads approved pitches from the Ledger, writes the video prompt, 
slices it into 3 aspect ratios (Zillow, IG, FB), and saves DRAFT video 
records for the Governor to approve.

Law: No fiction. We animate the real property, we don't invent it.
"""
import os
import sys
import json
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
# FUEL GAUGE (Same meter as X008)
# ============================================================
def load_fuel():
    if os.path.exists(FUEL_LOG):
        with open(FUEL_LOG) as f: return json.load(f)
    return {"total_calls": 0, "total_tokens_in": 0, "total_tokens_out": 0, "estimated_cost_usd": 0.0, "history": []}

def save_fuel(fuel):
    with open(FUEL_LOG, "w") as f: json.dump(fuel, f, indent=2)

def log_fuel(usage, model):
    fuel = load_fuel()
    # FIX 1: Updated pricing math to match new model
    cost = (usage.input_tokens / 1_000_000) * 1.00 + (usage.output_tokens / 1_000_000) * 5.00
    fuel["total_calls"] += 1
    fuel["total_tokens_in"] += usage.input_tokens
    fuel["total_tokens_out"] += usage.output_tokens
    fuel["estimated_cost_usd"] = round(fuel["estimated_cost_usd"] + cost, 6)
    fuel["history"].append({
        "timestamp": datetime.now().isoformat(), "agent": "X009",
        "tokens_in": usage.input_tokens, "tokens_out": usage.output_tokens,
        "cost_usd": round(cost, 6)
    })
    fuel["history"] = fuel["history"][-100:]
    save_fuel(fuel)

# ============================================================
# THE DIRECTOR'S BRAIN
# ============================================================
def write_video_prompt(lead, pitch_text):
    """Tells Claude to write the exact prompt needed for Kling AI."""
    client = anthropic.Anthropic()
    
    system_prompt = """You are a Master Video Director. You write text-to-video prompts for Kling AI.
    RULE 1: NO FICTION. Only animate the property described. Do not invent furniture or views that aren't listed.
    RULE 2: Keep it under 60 seconds. Cinematic, bright, and professional.
    Output ONLY the prompt text to be fed directly into the video generator."""
    
    user_msg = f"""Write a Kling AI prompt for this property:
    Lead Name: {lead['name']}
    Business: {lead['business']}
    Property Details: {lead['details']}
    
    The marketing pitch we are supporting: {pitch_text}
    
    Write the exact prompt to generate a 60-second video tour of this specific property."""

    # FIX 1: Updated model string to current running version
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}]
    )
    
    log_fuel(response.usage, "claude-3-5-haiku-20241022")
    return response.content[0].text.strip()

# ============================================================
# THE RENDER PIPELINE (Mock V1)
# ============================================================
# FIX 2: Added pitch_id parameter
def render_cuts(lead_id, pitch_id, prompt_text):
    """Simulates sending the prompt to Kling and getting 3 files back."""
    cuts = [
        ("16:9", "Zillow_Wide"),
        ("9:16", "Instagram_Vertical"),
        ("1:1", "Facebook_Square")
    ]
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    for ratio, platform_name in cuts:
        # Simulated file path (In production, this is where Kling's returned URL goes)
        fake_file_path = f"/videos/lead_{lead_id}_{platform_name}.mp4"
        
        # FIX 2: Inserting pitch_id into the database
        c.execute("""INSERT INTO videos (lead_id, pitch_id, prompt_text, file_path, aspect_ratio, status) 
                     VALUES (?, ?, ?, ?, ?, 'DRAFT')""",
                  (lead_id, pitch_id, prompt_text, fake_file_path, ratio))
    
    conn.commit()
    conn.close()

# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    print("=" * 60)
    print("NEVERX009 v1 - THE MOVIE STUDIO (Directing Kling)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # FIX 3: Added NOT EXISTS guard to prevent duplicate video generation
    c.execute("""
        SELECT l.id as lead_id, l.name, l.business, l.details, p.pitch_text, p.id as pitch_id 
        FROM leads l 
        JOIN pitches p ON l.id = p.lead_id 
        WHERE p.status = 'PITCHED' 
          AND NOT EXISTS (SELECT 1 FROM videos v WHERE v.lead_id = l.id)
        ORDER BY l.id LIMIT 1
    """)
    
    row = c.fetchone()
    if not row:
        print("No pitched leads found in the Ledger to turn into videos (or all already drafted).")
        conn.close()
        return
        
    lead = dict(row)
    print(f"Found Lead: {lead['name']} - {lead['business']}")
    print("-" * 60)
    
    # 1. Write the Prompt
    print("Director X009 is writing the Kling prompt...")
    prompt = write_video_prompt(lead, lead['pitch_text'])
    print(f"\nPROMPT WRITTEN:\n{prompt}\n")
    
    # 2. Render the 3 Cuts
    print("-" * 60)
    print("Sending to Kling (Simulation)... Rendering 3 aspect ratios...")
    
    # FIX 2: Passing pitch_id to render_cuts
    render_cuts(lead['lead_id'], lead['pitch_id'], prompt)
    
    # FIX 3: Mark pitch as VIDEO_DRAFTED so it doesn't get picked up again
    c.execute("UPDATE pitches SET status = 'VIDEO_DRAFTED' WHERE id = ?", (lead['pitch_id'],))
    conn.commit()

    # 4. Verify in DB
    c.execute("SELECT aspect_ratio, file_path, status FROM videos WHERE lead_id = ?", (lead['lead_id'],))
    videos = c.fetchall()
    
    print("\n[LEDGER] 3 Video Cuts saved to Drafts:")
    for v in videos:
        print(f"  -> {v['aspect_ratio']:5} | {v['file_path']} | Status: {v['status']}")
        
    print("\n" + "=" * 60)
    print("X009 DONE. Awaiting Governor approval to ship.")
    print("=" * 60)
    
    fuel = load_fuel()
    print(f"FUEL: {fuel['total_calls']} call(s) | ${fuel['estimated_cost_usd']} spent total")
    conn.close()

if __name__ == "__main__":
    main()
