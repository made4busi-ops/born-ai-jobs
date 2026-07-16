#!/usr/bin/env python3
"""
voice_cloner.py — clone a real person's voice from their uploaded sample
using ElevenLabs Instant Voice Clone, and store the resulting voice_id
back into actor_profiles.voice_clone_id.

This does NOT run automatically on intake — it's a deliberate second
step, called only after consent has already been confirmed (checked
again here as a hard gate, not just trusted from the intake step).
"""
import sqlite3
from pathlib import Path

import requests

from neverx007.config import ELEVENLABS_API_KEY

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


def clone_voice_for_actor(actor_profile_id: int, db_path: Path) -> dict:
    """Clone the voice for one actor_profiles row, by id. Returns a dict
    with success/error, matching the style of the rest of the pipeline."""
    if not ELEVENLABS_API_KEY:
        return {"success": False, "error": "ELEVENLABS_API_KEY not set"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM actor_profiles WHERE id = ?", (actor_profile_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return {"success": False, "error": f"No actor_profiles row with id={actor_profile_id}"}

    # Hard consent gate — re-checked here, not just trusted from intake.
    if not row["consent_given"]:
        conn.close()
        return {"success": False, "error": "Consent not recorded for this actor — refusing to clone."}

    voice_sample_path = row["voice_sample_path"]
    if not voice_sample_path or not Path(voice_sample_path).exists():
        conn.close()
        return {"success": False, "error": f"Voice sample file missing: {voice_sample_path}"}

    name = row["name"] or f"actor_{actor_profile_id}"

    try:
        with open(voice_sample_path, "rb") as f:
            files = {"files": (Path(voice_sample_path).name, f, "audio/wav")}
            data = {"name": name}
            headers = {"xi-api-key": ELEVENLABS_API_KEY}
            r = requests.post(
                f"{ELEVENLABS_BASE}/voices/add",
                headers=headers,
                data=data,
                files=files,
                timeout=60,
            )
    except Exception as e:
        conn.close()
        return {"success": False, "error": f"Request to ElevenLabs failed: {e}"}

    if r.status_code != 200:
        conn.close()
        return {"success": False, "error": f"ElevenLabs rejected the clone request: {r.status_code} {r.text[:300]}"}

    result = r.json()
    voice_id = result.get("voice_id")
    if not voice_id:
        conn.close()
        return {"success": False, "error": f"No voice_id returned: {result}"}

    conn.execute(
        "UPDATE actor_profiles SET voice_clone_id = ? WHERE id = ?",
        (voice_id, actor_profile_id),
    )
    conn.commit()
    conn.close()

    return {"success": True, "actor_profile_id": actor_profile_id, "voice_id": voice_id}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python voice_cloner.py <actor_profile_id>")
        sys.exit(1)
    db = Path("data/watcher.db")
    result = clone_voice_for_actor(int(sys.argv[1]), db)
    print(result)
