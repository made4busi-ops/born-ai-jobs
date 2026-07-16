from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import uvicorn
import subprocess
import sqlite3
from pathlib import Path as P
from datetime import datetime
import sys

sys.path.insert(0, str(P(__file__).parent.parent))

try:
    from job77_movie.core.extractor import extract_text_from_pdf
    EXTRACTOR_AVAILABLE = True
except ImportError:
    EXTRACTOR_AVAILABLE = False

app = FastAPI(title="Northframe PDF2Movie Job 77")

from web_api import router as web_router
app.include_router(web_router)

DATA = P("data")
for d in ["input", "movies", "logs", "members", "actor_profiles"]:
    (DATA / d).mkdir(exist_ok=True)

DB = DATA / "watcher.db"

def db_conn():
    return sqlite3.connect(DB)

with db_conn() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS processed_files (filename TEXT UNIQUE, processed_at TEXT, output_file TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS memberships (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, plan TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_email TEXT, customer_name TEXT, product_type TEXT, estimated_pages INTEGER, estimated_minutes INTEGER, model_choice TEXT, face_body_scan INTEGER, price REAL, status TEXT DEFAULT 'pending', created_at TEXT, updated_at TEXT, final_movie_path TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS actor_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, face_data TEXT, body_data TEXT, licensing_price REAL, total_uses INTEGER DEFAULT 0, total_earnings REAL DEFAULT 0.0, created_at TEXT, consent_given INTEGER DEFAULT 0, consent_timestamp TEXT, voice_sample_path TEXT, voice_clone_id TEXT, face_reference_id TEXT, face_description TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS handoff_log (id INTEGER PRIMARY KEY AUTOINCREMENT, envelope_id TEXT UNIQUE, job_id TEXT, from_room TEXT, to_room TEXT, guard_1_passed INTEGER, guard_1_score INTEGER, guard_2_passed INTEGER, guard_2_score INTEGER, seal TEXT, timestamp TEXT)")
    conn.commit()

@app.get("/health")
def health():
    movies = len(list((DATA / "movies").glob("*.mp4")))
    return {"status": "Job 77 Running", "movies": movies, "extractor": EXTRACTOR_AVAILABLE}

@app.post("/process")
async def process(file: UploadFile = File(...)):
    try:
        content = await file.read()
        inp = DATA / "input" / file.filename
        with open(inp, "wb") as f:
            f.write(content)

        out = DATA / "movies" / f"{file.filename}.mp4"

        # Get text safely from extractor
        if EXTRACTOR_AVAILABLE:
            result = extract_text_from_pdf(str(inp))
            if isinstance(result, dict):
                text = result.get("text", "") or ""
            else:
                text = str(result)
        else:
            text = "Sample text for testing"

        # Simple safe ffmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=1280x720:d=8",
            "-vf", f"drawtext=text='Northframe Test':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2",
            str(out)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return {"status": "error", "msg": result.stderr[:400]}

        with db_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO processed_files VALUES (?, ?, ?)",
                         (file.filename, datetime.now().isoformat(), str(out)))
            conn.commit()

        return {
            "status": "success",
            "movie": str(out),
            "filename": file.filename,
            "message": "Video generated"
        }
    except Exception as e:
        return {"status": "error", "msg": str(e)}

from fastapi.staticfiles import StaticFiles
import os as _os
_web_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "web")
app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)


