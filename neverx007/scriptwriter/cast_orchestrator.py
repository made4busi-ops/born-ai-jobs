#!/usr/bin/env python3
"""
Cast Orchestrator — before any script gets written, check who's
actually locked in (real voice + real face already set up) and hand
their real names to the scriptwriter as required characters, instead
of hoping generic character names happen to match afterward.

This flips the casting order: real people first, story built around
them -- not story first, hoping for a lucky name match.
"""
import sqlite3
from pathlib import Path


def get_available_cast(allowed_names: list = None, db_path: Path = None) -> list:
    """Return real actors who have BOTH a real voice clone and a real
    locked face -- i.e. fully cast, ready to star in a script.

    IMPORTANT: allowed_names must be provided and non-empty, or this
    returns []. Without a scope, every locked actor in the whole
    database would get pulled into every script generated -- including
    unrelated customers' actors. allowed_names should be the specific
    cast list for THIS movie/job only (e.g. the cast_names already
    passed into generate_script_chunk)."""
    if not allowed_names:
        return []

    if db_path is None:
        db_path = Path("data/watcher.db")
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" for _ in allowed_names)
    lowered = [n.lower() for n in allowed_names]
    rows = conn.execute(
        f"SELECT name, face_description FROM actor_profiles "
        f"WHERE consent_given = 1 "
        f"AND voice_clone_id IS NOT NULL "
        f"AND face_reference_id IS NOT NULL "
        f"AND lower(name) IN ({placeholders})",
        lowered
    ).fetchall()
    conn.close()

    return [{"name": name, "description": desc} for name, desc in rows]


def build_cast_instruction(cast: list) -> str:
    """Turn the available cast into an explicit instruction block for
    the scriptwriting prompt, telling Grok exactly who must star."""
    if not cast:
        return ""

    lines = ["IMPORTANT: The following real people are cast in this film and MUST appear as named characters, using these exact names:"]
    for actor in cast:
        lines.append(f"- {actor['name']}" + (f" ({actor['description']})" if actor['description'] else ""))
    lines.append("Do not invent different names for these people. Build the story around them as the featured cast.")
    return "\n".join(lines)
