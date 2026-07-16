#!/usr/bin/env python3
"""Fuel Gauge -- NorthFraim one-command dashboard.
Shows API credit balances (ElevenLabs, JSON2Video, PixVerse) and service health.
xAI has no public balance endpoint -- shown as manual check.
Usage: python3 fuel_gauge.py
"""
import os, subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed in this Python. Run with the venv python.")
    raise SystemExit(1)

BASE = Path(__file__).resolve().parent.parent.parent

def load_env():
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

def bar(label, value):
    print(f"  {label:<14} {value}")

def check_elevenlabs():
    key = os.getenv("ELEVENLABS_API_KEY", "")
    if not key:
        return "NO KEY IN .env"
    try:
        r = requests.get("https://api.elevenlabs.io/v1/user/subscription",
                         headers={"xi-api-key": key}, timeout=15)
        if r.status_code != 200:
            return f"HTTP {r.status_code} -- check key/permissions"
        d = r.json()
        used = d.get("character_count", "?")
        limit = d.get("character_limit", "?")
        tier = d.get("tier", "")
        left = ""
        if isinstance(used, int) and isinstance(limit, int):
            left = f" -> {limit - used:,} credits LEFT"
        return f"{used:,} used of {limit:,}{left}  ({tier})" if isinstance(used, int) else f"used={used} limit={limit}"
    except Exception as e:
        return f"ERROR: {e}"

def check_json2video():
    key = os.getenv("JSON2VIDEO_API_KEY", "")
    if not key:
        return "NO KEY IN .env"
    try:
        r = requests.get("https://api.json2video.com/v2/movies",
                         headers={"x-api-key": key}, timeout=15)
        if r.status_code != 200:
            return f"HTTP {r.status_code} -- check key"
        d = r.json()
        quota = d.get("remaining_quota", {})
        credits = quota.get("time", "?")
        return f"{credits:,} credits LEFT" if isinstance(credits, int) else f"remaining_quota: {quota}"
    except Exception as e:
        return f"ERROR: {e}"

def check_pixverse():
    key = os.getenv("PIXVERSE_API_KEY", "")
    if not key:
        return "NO KEY IN .env"
    try:
        r = requests.get("https://app-api.pixverse.ai/openapi/v2/account/balance",
                         headers={"API-KEY": key}, timeout=15)
        if r.status_code != 200:
            return f"HTTP {r.status_code} -- check key"
        d = r.json()
        resp = d.get("Resp") or d.get("resp") or d
        if isinstance(resp, dict):
            parts = [f"{k}: {v}" for k, v in resp.items() if "credit" in k.lower() or "balance" in k.lower()]
            if parts:
                return ", ".join(parts)
            return str(resp)[:120]
        return str(d)[:120]
    except Exception as e:
        return f"ERROR: {e}"

def check_services():
    try:
        r = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True, timeout=10)
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        out = []
        for l in lines:
            name = l.split()[0]
            state = "RUNNING" if "RUNNING" in l else ("FATAL" if "FATAL" in l else l.split()[1] if len(l.split()) > 1 else "?")
            mark = "OK " if state == "RUNNING" else "!! "
            out.append(f"  {mark}{name:<22} {state}")
        return "\n".join(out) if out else "  (no services found)"
    except Exception as e:
        return f"  supervisorctl error: {e}"

def main():
    load_env()
    print("=" * 52)
    print("  NORTHFRAIM FUEL GAUGE")
    print("=" * 52)
    print("FUEL (API credits):")
    bar("ElevenLabs:", check_elevenlabs())
    bar("JSON2Video:", check_json2video())
    bar("PixVerse:", check_pixverse())
    bar("xAI (Grok):", "no balance API -- check console.x.ai")
    print("-" * 52)
    print("ENGINE (services):")
    print(check_services())
    print("=" * 52)

if __name__ == "__main__":
    main()
