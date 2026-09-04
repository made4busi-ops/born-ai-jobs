"""ai_receptionist.py

Answers visitor questions live on the landing page and captures their
contact info into the Ledger — the "instant chat" upgrade for
d11.pythonanywhere.com. Uses the existing Haiku API key already
configured for X008.

Flask blueprint — wire into the existing form_catcher.py app.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

# Was a bare relative "data/leads.db" -- silently pointed at whatever the
# process's current working directory happened to be rather than this
# project's real data dir. Made absolute, matching form_catcher.py's own
# BASE_DIR-relative convention, so this always lands in the same
# database regardless of how/where the process is started.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "leads.db")

BUSINESS_INFO = """You are the AI receptionist for Born AI Jobs / Job 73.
We create custom video commercials for rental listings (landlords and
Airbnb hosts). Answer visitor questions warmly and briefly. If they seem
interested, ask for their name, business/property, and email or phone
so a human can follow up. Never invent pricing, stats, or promises not
given to you. If unsure, say a team member will follow up with details."""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_api_key():
    """Load the Haiku API key from environment. Never crashes."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("WARNING: ANTHROPIC_API_KEY not set; receptionist cannot respond.")
        return None
    return key


def _init_db():
    """Ensure the chat_leads table exists. Never crashes."""
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                contact TEXT,
                message TEXT,
                captured_at TEXT
            )
        """)
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as exc:
        print(f"WARNING: could not initialize chat_leads table: {exc}")
        return False


def save_chat_lead(name, contact, message):
    """Save a captured lead from the chat. Returns True on success. Never crashes."""
    if not name and not contact:
        return False
    _init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO chat_leads (name, contact, message, captured_at) VALUES (?, ?, ?, ?)",
            (name or "", contact or "", message or "", _now_iso()),
        )
        conn.commit()
        conn.close()
        print(f"[RECEPTIONIST] Captured lead: name={name!r} contact={contact!r}")
        return True
    except sqlite3.Error as exc:
        print(f"WARNING: could not save chat lead: {exc}")
        return False


def get_response(visitor_message, conversation_history=None):
    """Call the Haiku API to generate a receptionist reply. Never crashes.

    Returns a reply string, or a safe fallback message on any failure.
    """
    api_key = _get_api_key()
    if api_key is None:
        return "Thanks for reaching out — a team member will follow up with you shortly."

    try:
        import anthropic
    except ImportError:
        print("WARNING: anthropic package not installed; using fallback reply.")
        return "Thanks for reaching out — a team member will follow up with you shortly."

    messages = conversation_history or []
    messages = messages + [{"role": "user", "content": visitor_message}]

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=BUSINESS_INFO,
            messages=messages,
        )
        reply_text = response.content[0].text if response.content else ""
        if not reply_text:
            return "Thanks for reaching out — a team member will follow up with you shortly."
        return reply_text
    except Exception as exc:
        print(f"WARNING: receptionist API call failed: {exc}")
        return "Thanks for reaching out — a team member will follow up with you shortly."


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ai_receptionist.py '<visitor message>'")
        sys.exit(1)
    reply = get_response(sys.argv[1])
    print(f"RECEPTIONIST REPLY: {reply}")
