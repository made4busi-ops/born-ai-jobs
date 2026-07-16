#!/usr/bin/env python3
"""Initializes the NeverX007 Leads Ledger (SQLite)."""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "leads.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, business TEXT, 
        platform TEXT, details TEXT, source_url TEXT, status TEXT DEFAULT 'NEW', 
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS pitches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER, pitch_text TEXT, 
        status TEXT DEFAULT 'DRAFT', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
        FOREIGN KEY (lead_id) REFERENCES leads (id))''')
    
    conn.commit()
    conn.close()
    print(f"LEDGER INITIALIZED: {DB_PATH}")
    print("Tables ready: leads, pitches")

if __name__ == "__main__":
    init_db()
