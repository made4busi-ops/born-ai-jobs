#!/usr/bin/env python3
"""NorthFraim Job 77 - Full Health Check"""
import subprocess
import sys
from pathlib import Path

print("=" * 60)
print("NORTHFRAIM JOB 77 - FULL HEALTH CHECK")
print("=" * 60)

# 1. Check required packages
print("\n[1] REQUIRED PACKAGES:")
packages = ["dotenv", "requests", "pdfplumber", "uvicorn", "fastapi"]
for pkg in packages:
    try:
        __import__(pkg)
        print(f"  OK    {pkg}")
    except ImportError as e:
        print(f"  MISSING  {pkg} -- {e}")

# 2. Check required files exist
print("\n[2] REQUIRED FILES:")
files = [
    "neverx007/config.py",
    "neverx007/governor.py",
    "job77_movie/core/extractor.py",
    "job77_movie/core/script_generator.py",
    "job77_movie/core/video_renderer.py",
    "job77_movie/core/movie_pipeline.py",
    "job77_movie/core/movie_workflow.py",
    "mcp/northfraim_complete.py",
    ".env",
]
for f in files:
    p = Path(f)
    if p.exists():
        print(f"  OK    {f} ({p.stat().st_size} bytes)")
    else:
        print(f"  MISSING  {f}")

# 3. Check .env keys are actually loaded (without printing values)
print("\n[3] ENVIRONMENT KEYS LOADED:")
try:
    from dotenv import load_dotenv
    import os
    load_dotenv(".env")
    keys = ["XAI_API_KEY", "JSON2VIDEO_API_KEY", "OPENROUTER_API_KEY"]
    for k in keys:
        v = os.getenv(k)
        if v:
            print(f"  OK    {k} (length {len(v)})")
        else:
            print(f"  MISSING  {k}")
except Exception as e:
    print(f"  ERROR checking env: {e}")

# 4. Check mcp/northfraim_complete.py imports cleanly
print("\n[4] CAN mcp/northfraim_complete.py IMPORT CLEANLY?")
result = subprocess.run(
    [sys.executable, "-c", "import ast; ast.parse(open('mcp/northfraim_complete.py').read())"],
    capture_output=True, text=True
)
if result.returncode == 0:
    print("  OK    File has valid Python syntax")
else:
    print(f"  ERROR  Syntax problem:\n{result.stderr}")

# 5. Try actually running northfraim_complete.py briefly to catch the real error
print("\n[5] ACTUAL IMPORT TEST for mcp/northfraim_complete.py:")
result = subprocess.run(
    [sys.executable, "-c", "import sys; sys.path.insert(0, '.'); exec(open('mcp/northfraim_complete.py').read().split('if __name__')[0])"],
    capture_output=True, text=True, timeout=15
)
if result.returncode == 0:
    print("  OK    Imports and top-level code ran without error")
else:
    print(f"  ERROR  {result.stderr[-1500:]}")

print("\n" + "=" * 60)
print("HEALTH CHECK COMPLETE")
print("=" * 60)
