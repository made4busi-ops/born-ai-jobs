#!/usr/bin/env python3
"""
api_health_check.py — proactively checks that ElevenLabs, JSON2Video,
and PixVerse are all actually reachable and authenticating correctly,
on a timer, independent of any render job running.

This exists because API keys can go stale silently (permission
changes, leak-detection auto-disable, rotation on the provider's
side) with nothing telling you until a real customer job fails mid-render.
This catches it first and logs it to the same errors table diagnostics.py
already uses, so a health check surfaces it immediately instead of
someone discovering it live.
"""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from neverx007.diagnostics import log_error


def _load_env_file():
    """Supervisor starts this process with a bare environment -- it
    doesn't source .env the way a manual terminal session does. Load
    it directly so the key checks below actually have something to
    check."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

CHECK_INTERVAL_SECONDS = 300  # every 5 minutes


def check_elevenlabs():
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        return False, "ELEVENLABS_API_KEY not set in environment"
    try:
        r = requests.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
            timeout=15,
        )
        if r.status_code == 200:
            return True, None
        return False, f"ElevenLabs returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"ElevenLabs check failed: {e}"


def check_json2video():
    key = os.getenv("JSON2VIDEO_API_KEY")
    if not key:
        return False, "JSON2VIDEO_API_KEY not set in environment"
    try:
        r = requests.get(
            "https://api.json2video.com/v2/movies",
            headers={"x-api-key": key},
            timeout=15,
        )
        if r.status_code == 200:
            return True, None
        return False, f"JSON2Video returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"JSON2Video check failed: {e}"


def check_pixverse():
    key = os.getenv("PIXVERSE_API_KEY")
    if not key:
        return False, "PIXVERSE_API_KEY not set in environment"
    try:
        r = requests.get(
            "https://app-api.pixverse.ai/openapi/v2/account/balance",
            headers={"API-KEY": key},
            timeout=15,
        )
        if r.status_code == 200:
            return True, None
        return False, f"PixVerse returned HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, f"PixVerse check failed: {e}"


def run_checks():
    checks = {
        "elevenlabs": check_elevenlabs,
        "json2video": check_json2video,
        "pixverse": check_pixverse,
    }
    for service_name, check_fn in checks.items():
        ok, detail = check_fn()
        if not ok:
            log_error(
                error_summary=f"API health check failed: {service_name}",
                context=detail,
            )
            print(f"[api_health_check] {service_name}: FAILED — {detail}")
        else:
            print(f"[api_health_check] {service_name}: ok")


def main():
    while True:
        run_checks()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
