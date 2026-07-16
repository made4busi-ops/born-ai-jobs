#!/usr/bin/env python3
"""
Guard 2: Lip-Sync Applied
Last check before a hero scene ships -- deliberately stricter than
Guard 1. Fails closed if the lip-sync mechanism isn't present or used,
by design, not by accident.
"""

GUARD_NAME = "lipsync_check"


def check(pixverse_response: dict) -> dict:
    used_lipsync = pixverse_response.get("lipsync_applied", False)
    if not used_lipsync:
        return {"guard": GUARD_NAME, "passed": False, "score": 0,
                "reason": "Lip-sync was not applied to this generation"}
    return {"guard": GUARD_NAME, "passed": True, "score": 1, "reason": "OK"}
