#!/usr/bin/env python3
"""
sorting_hub.py
The Job 73 -> Office spine: reads NEW leads from the Job 73 Ledger,
classifies each as LABOR (physical work) or OFFICE (video-commercial /
admin work), and hands LABOR leads to Turnover Titans' own leads table.
OFFICE leads stay in Job 73's queue for the existing pitch engine.

Real paths, no assumptions:
  JOB73_DB = /root/born-ai-jobs/data/leads.db
  TT_DB    = /root/northfraim-turnovertitan/data/leads.db
"""

import sqlite3
import sys

JOB73_DB = "/root/born-ai-jobs/data/leads.db"
TT_DB = "/root/northfraim-turnovertitan/data/leads.db"

# Labor = physical, on-site work. If any of these show up, it's a
# Turnover Titans job, full stop — video-commercial language never
# overrides a labor keyword.
LABOR_KEYWORDS = [
    "cleaning", "clean", "turnover", "maintenance", "repair",
    "inspection", "landscaping", "lawn", "snow removal", "plumbing",
    "electrical", "hvac", "painting", "moving", "hauling", "pest",
]


def classify(business: str, details: str) -> str:
    text = f"{business or ''} {details or ''}".lower()
    for kw in LABOR_KEYWORDS:
        if kw in text:
            return "LABOR"
    return "OFFICE"


def route_labor_lead(job73_conn, tt_conn, lead_id, name, business, details):
    tt_conn.execute(
        "INSERT INTO leads (name, business, message) VALUES (?, ?, ?)",
        (name, business or "Routed from Job 73", details),
    )
    tt_conn.commit()
    job73_conn.execute(
        "UPDATE leads SET status = 'ROUTED_LABOR' WHERE id = ?", (lead_id,)
    )
    job73_conn.commit()


def mark_office(job73_conn, lead_id):
    job73_conn.execute(
        "UPDATE leads SET status = 'OFFICE_QUEUE' WHERE id = ?", (lead_id,)
    )
    job73_conn.commit()


def run(job73_db_path=JOB73_DB, tt_db_path=TT_DB):
    job73_conn = sqlite3.connect(job73_db_path)
    tt_conn = sqlite3.connect(tt_db_path)

    rows = job73_conn.execute(
        "SELECT id, name, business, details FROM leads WHERE status = 'NEW'"
    ).fetchall()

    labor_count = 0
    office_count = 0

    for lead_id, name, business, details in rows:
        verdict = classify(business, details)
        if verdict == "LABOR":
            route_labor_lead(job73_conn, tt_conn, lead_id, name, business, details)
            labor_count += 1
        else:
            mark_office(job73_conn, lead_id)
            office_count += 1

    job73_conn.close()
    tt_conn.close()
    return labor_count, office_count


if __name__ == "__main__":
    labor, office = run()
    print(f"Sorted: {labor} LABOR -> Turnover Titans, {office} OFFICE -> Job 73 queue")
