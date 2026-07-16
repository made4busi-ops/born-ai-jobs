#!/usr/bin/env python3
"""
face_locker.py — lock a real actor's face using PixVerse, so scenes can
later generate video/images that keep their identity consistent.

Takes an actor's uploaded photo, uploads it to PixVerse to get a
media_id (the face reference), and stores both that ID and a text
description back into actor_profiles. The description is required —
PixVerse v6 needs an explicit text anchor (e.g. "a bald man with
glasses and a mustache") alongside the reference image to actually
hold identity across a generation; the image alone isn't enough.

This does NOT run automatically on intake — deliberate second step,
same as voice_cloner.py, and re-checks consent as a hard gate.
"""
import sqlite3
import uuid
from pathlib import Path

import requests

from neverx007.config import PIXVERSE_API_KEY

PIXVERSE_BASE = "https://app-api.pixverse.ai"


def lock_face_for_actor(actor_profile_id: int, face_description: str, db_path: Path) -> dict:
    """Upload the actor's photo to PixVerse and store the reference.
    face_description must be a real, specific description (used later
    to anchor every generation for this actor) — not optional."""
    if not PIXVERSE_API_KEY:
        return {"success": False, "error": "PIXVERSE_API_KEY not set"}

    if not face_description or not face_description.strip():
        return {"success": False, "error": "face_description is required — PixVerse needs a text anchor, not just the image"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM actor_profiles WHERE id = ?", (actor_profile_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return {"success": False, "error": f"No actor_profiles row with id={actor_profile_id}"}

    if not row["consent_given"]:
        conn.close()
        return {"success": False, "error": "Consent not recorded for this actor — refusing to lock face."}

    photo_path = row["face_data"]
    if not photo_path or not Path(photo_path).exists():
        conn.close()
        return {"success": False, "error": f"Photo file missing: {photo_path}"}

    trace_id = str(uuid.uuid4())

    try:
        with open(photo_path, "rb") as f:
            files = {"file": f}
            headers = {"Ai-Trace-Id": trace_id, "API-KEY": PIXVERSE_API_KEY}
            r = requests.post(
                f"{PIXVERSE_BASE}/openapi/v2/media/upload",
                headers=headers,
                files=files,
                timeout=60,
            )
    except Exception as e:
        conn.close()
        return {"success": False, "error": f"Request to PixVerse failed: {e}"}

    data = r.json()
    if data.get("ErrCode") != 0:
        conn.close()
        return {"success": False, "error": f"PixVerse rejected the upload: {data}"}

    media_id = data.get("Resp", {}).get("media_id")
    if not media_id:
        conn.close()
        return {"success": False, "error": f"No media_id returned: {data}"}

    conn.execute(
        "UPDATE actor_profiles SET face_reference_id = ?, face_description = ? WHERE id = ?",
        (str(media_id), face_description.strip(), actor_profile_id),
    )
    conn.commit()
    conn.close()

    return {"success": True, "actor_profile_id": actor_profile_id, "face_reference_id": media_id, "face_description": face_description.strip()}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python face_locker.py <actor_profile_id> \"<face description>\"")
        sys.exit(1)
    db = Path("data/watcher.db")
    result = lock_face_for_actor(int(sys.argv[1]), sys.argv[2], db)
    print(result)
