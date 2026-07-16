#!/usr/bin/env python3
"""Catches leads from the landing page and drops them in the Ledger."""
from flask import Flask, request, redirect
import sqlite3, os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "leads.db")

@app.route('/submit', methods=['POST'])
def submit():
    # Grab whatever fields the form sent
    form_data = request.form.to_dict()
    
    name = form_data.get('name', form_data.get('Name', 'Unknown'))
    business = form_data.get('business', form_data.get('Business', 'Website Lead'))
    details = " | ".join([f"{k}: {v}" for k, v in form_data.items() if k.lower() not in ['name', 'business']])
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO leads (name, business, platform, details) VALUES (?, ?, ?, ?)",
              (name, business, "Website Form", details))
    conn.commit()
    conn.close()
    
    print(f"[LEDGER] New lead captured from website: {name} - {business}")
    # Redirect them back to the page (or a thank you page later)
    return redirect('http://166.198.102.51/?status=success', code=302)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
