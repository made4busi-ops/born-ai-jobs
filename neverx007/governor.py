#!/usr/bin/env python3
import time
import requests
from neverx007.config import XAI_API_KEY, XAI_MODEL, XAI_URL

def call_grok(prompt):
    if not XAI_API_KEY:
        return "ERROR: XAI_API_KEY not set"
    try:
        r = requests.post(
            XAI_URL,
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": XAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            timeout=60,
        )
        d = r.json()
        if "choices" in d:
            return d["choices"][0]["message"]["content"]
        return f"GROK_ERROR: {d}"
    except Exception as e:
        return f"GROK_ERROR: {e}"

def route_and_execute(task, task_type="general"):
    print(f"[GOVERNOR] {task_type} -> GROK ({XAI_MODEL})")
    return call_grok(task)

def self_healing_check():
    if not XAI_API_KEY:
        return "ISSUE: XAI_API_KEY missing"
    try:
        r = requests.post(
            XAI_URL,
            headers={
                "Authorization": f"Bearer {XAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": XAI_MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            timeout=10,
        )
        return "HEALTHY" if r.status_code == 200 else f"ISSUE: HTTP {r.status_code} - {r.text[:200]}"
    except Exception as e:
        return f"ISSUE: {e}"

def run_governor_loop():
    print("Governor (Grok-only) started.")
    print(f"Health: {self_healing_check()}")
    while True:
        print("heartbeat...")
        time.sleep(30)

if __name__ == "__main__":
    run_governor_loop()
