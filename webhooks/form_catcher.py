#!/usr/bin/env python3
"""Catches leads from the landing page and drops them in the Ledger."""
from flask import Flask, request, redirect, send_from_directory, jsonify
import sqlite3, os, sys

app = Flask(__name__)
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_DIR, "data", "leads.db")
ASSETS_DIR = os.path.join(REPO_DIR, "assets")

sys.path.insert(0, REPO_DIR)
import ai_receptionist


@app.route('/')
def landing():
    return send_from_directory(REPO_DIR, 'job73_landing.html')


@app.route('/assets/<path:filename>')
def assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


@app.route('/api/chat', methods=['POST'])
def chat():
    """Real route for ai_receptionist.py -- previously a standalone script,
    never actually reachable from the live page (2026-09-04)."""
    data = request.get_json(force=True, silent=True) or {}
    message = data.get('message', '')
    history = data.get('history', [])
    name = data.get('name', '')
    contact = data.get('contact', '')

    reply = ai_receptionist.get_response(message, history)
    if name or contact:
        ai_receptionist.save_chat_lead(name, contact, message)
    return jsonify({"reply": reply})


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
    # Was http://166.198.102.51/?status=success -- an IP that isn't this
    # VPS (162.222.206.72) and isn't reachable at all; a stale reference
    # from wherever this was drafted. Now redirects back to this
    # business's own real, live route (2026-09-04).
    return redirect('/jobs73/?status=success', code=302)

if __name__ == '__main__':
    # Was port 8080 -- now taken by turnover-titans.service on this same
    # machine (wired earlier tonight). Moved to 8040, the next free
    # internal port after Commercial Genie's 8030.
    app.run(host='127.0.0.1', port=8040)
