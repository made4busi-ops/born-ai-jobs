#!/usr/bin/env python3
"""Full Northfraim Job 77 Project Audit & Bug Hunter"""
import os
from pathlib import Path
import subprocess

BASE = Path.home() / "northfraim-job77"

print("=" * 60)
print("NORTHFRAME JOB 77 - FULL SHAKEDOWN AUDIT")
print("=" * 60)

# 1. Check for leftover junk files
print("\n[1] Checking for leftover junk files...")
junk_patterns = ["setup_*.py", "fix_*.py", "generate_*.py", "start-*.sh", "install-*.sh", 
                 ".gitigno*", "project_state.json", "server.log", "*.sh~"]
found_junk = False
for pattern in junk_patterns:
    matches = list(BASE.glob(pattern))
    if matches:
        print(f"  ❌ FOUND JUNK: {matches}")
        found_junk = True
if not found_junk:
    print("  ✅ No leftover junk files found")

# 2. Check .env cleanliness
print("\n[2] Checking .env cleanliness...")
env_path = BASE / ".env"
if env_path.exists():
    content = env_path.read_text().strip()
    lines = content.splitlines()
    print(f"  Lines in .env: {len(lines)}")
    if len(lines) > 3 or any("import" in line or "def " in line or "class " in line for line in lines):
        print("  ❌ .env IS CORRUPTED with Python code!")
    else:
        print("  ✅ .env looks clean")
        print(f"  Content:\n{content}")
else:
    print("  ❌ .env missing!")

# 3. Check key loading
print("\n[3] Checking API key loading...")
try:
    from neverx007.config import GEMINI_API_KEY, OPENROUTER_API_KEY
    print(f"  GEMINI_API_KEY loaded: {'Yes' if GEMINI_API_KEY else 'NO'}")
    print(f"  OPENROUTER_API_KEY loaded: {'Yes' if OPENROUTER_API_KEY else 'NO'}")
except Exception as e:
    print(f"  ❌ Key loading failed: {e}")

# 4. Check Governor
print("\n[4] Testing Governor routing...")
try:
    from neverx007.governor import route_and_execute, self_healing_check
    print(f"  Health: {self_healing_check()}")
    result = route_and_execute("Test creative task", "creative")
    print(f"  Creative test result: {result[:150]}...")
except Exception as e:
    print(f"  ❌ Governor test failed: {e}")

# 5. Check Supervisor processes
print("\n[5] Checking Supervisor processes...")
try:
    result = subprocess.run(["sudo", "supervisorctl", "status"], capture_output=True, text=True)
    print(result.stdout)
except Exception as e:
    print(f"  ❌ Supervisor check failed: {e}")

# 6. Check server health
print("\n[6] Checking northfraim server...")
try:
    import requests
    r = requests.get("http://localhost:8001/health", timeout=5)
    print(f"  Server response: {r.json()}")
except Exception as e:
    print(f"  ❌ Server check failed: {e}")

print("\n" + "=" * 60)
print("AUDIT COMPLETE")
print("=" * 60)
