#!/usr/bin/env python3
"""
diagnostics.py — when something fails, don't just say "it failed."
Capture the real reason (HTTP status, response body, exception detail)
and write it to the errors table, so failures are investigated and
remembered automatically, not just reported and forgotten.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def log_error(error_summary: str, context: str, db_path: Path = None):
    """Write a diagnosed error to the errors table. error_summary
    should be short (what failed); context should have the real
    detail (status code, response body, etc.)."""
    if db_path is None:
        db_path = Path("data/watcher.db")
    if not db_path.exists():
        return

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO errors (timestamp, error, context) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), error_summary, context),
    )
    conn.commit()
    conn.close()


def diagnose_http_response(service_name: str, response, extra_context: str = "") -> str:
    """Given a requests.Response object, build a real diagnostic
    message (status code + body) and log it. Returns the diagnostic
    string so the caller can also use it in their own error message."""
    try:
        status = response.status_code
        body = response.text[:500]
    except Exception:
        status = "unknown"
        body = "could not read response"

    summary = f"{service_name} returned HTTP {status}"
    context = f"Status: {status}\nBody: {body}\n{extra_context}"
    log_error(summary, context)
    return f"{summary} — {body}"


def diagnose_exception(service_name: str, exception: Exception, extra_context: str = "") -> str:
    """Given a caught exception, build a real diagnostic message and
    log it. Returns the diagnostic string so the caller can also use
    it in their own error message."""
    summary = f"{service_name} raised {type(exception).__name__}"
    context = f"Exception: {exception}\n{extra_context}"
    log_error(summary, context)
    return f"{summary}: {exception}"


def recent_errors(limit: int = 10, db_path: Path = None) -> list:
    """Pull the most recent logged errors, for review or for the
    machine to learn from patterns over time."""
    if db_path is None:
        db_path = Path("data/watcher.db")
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id, timestamp, error, context FROM errors ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows
