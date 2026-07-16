"""
web_api.py — NorthFraim website backend glue.

This is a FastAPI router meant to be INCLUDED in your existing app
(the one that already runs under supervisorctl on port 8001), not a
standalone service. It adds the routes the website's JS calls:

    POST /api/upload                  -> save PDF, return upload_id
    POST /api/create-checkout-session -> Stripe Checkout session for that upload
    POST /api/verify-and-start        -> confirm payment, kick off the real pipeline
    GET  /api/status/{job_id}         -> poll render progress
    GET  /api/download/{job_id}       -> serve the finished mp4
    GET  /                            -> serves website/index.html
"""

import json
import os
import subprocess
import threading
import time
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import stripe

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
MOVIE_DIR = DATA_DIR / "movies"
JOBS_FILE = DATA_DIR / "jobs.json"

for d in (UPLOAD_DIR, MOVIE_DIR):
    d.mkdir(parents=True, exist_ok=True)
if not JOBS_FILE.exists():
    JOBS_FILE.write_text("{}")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
PUBLIC_DOMAIN = os.environ.get("PUBLIC_DOMAIN", "http://localhost:8001")

TIERS = {
    "short":        {"label": "Short (TikTok-length)",         "price_cents": 900},
    "medium":       {"label": "Medium (standard short film)",   "price_cents": 1900},
    "novel":        {"label": "Novel (full-length manuscript)", "price_cents": 3900},
    "feature":      {"label": "Feature (45 min)",                "price_cents": 9900},
    "full_feature": {"label": "Full Feature (90 min)",           "price_cents": 29900},
}

_jobs_lock = threading.Lock()


def _read_jobs() -> dict:
    with _jobs_lock:
        return json.loads(JOBS_FILE.read_text())


def _write_job(job_id: str, data: dict):
    with _jobs_lock:
        jobs = json.loads(JOBS_FILE.read_text())
        jobs[job_id] = data
        JOBS_FILE.write_text(json.dumps(jobs, indent=2))


# Promo rate limit: Short-tier jobs are capped at 1 per calendar day,
# weekdays only (Mon-Fri), per customer email. Only applies to "short"
# tier since that's the free-trial/promo tier -- paid tiers are unlimited.
def _check_daily_limit(customer_email: str, tier: str):
    if tier != "short":
        return True, None

    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False, "Short-tier videos are only available Monday-Friday. Come back on Monday!"

    if not customer_email:
        return True, None  # no email on file, can't check history -- allow through

    today_str = now.date().isoformat()
    jobs = _read_jobs()
    for job in jobs.values():
        if (job.get("customer_email") == customer_email
                and job.get("tier") == "short"
                and job.get("created_date") == today_str):
            return False, "You've already used today's free Short video. One per day, Monday-Friday -- see you tomorrow!"

    return True, None


@router.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(400, "Only PDF files are accepted.")

    upload_id = uuid.uuid4().hex[:12]
    dest = UPLOAD_DIR / f"{upload_id}.pdf"
    contents = await file.read()

    max_bytes = 25 * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(400, "File too large (25MB limit).")

    dest.write_bytes(contents)
    return {"upload_id": upload_id}


class CheckoutRequest(BaseModel):
    upload_id: str
    tier: str


@router.post("/api/create-checkout-session")
async def create_checkout_session(payload: CheckoutRequest):
    pdf_path = UPLOAD_DIR / f"{payload.upload_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "Upload not found — please re-upload your PDF.")

    if payload.tier not in TIERS:
        raise HTTPException(400, f"Unknown tier '{payload.tier}'.")

    if not stripe.api_key:
        raise HTTPException(500, "Stripe is not configured on the server (STRIPE_SECRET_KEY missing).")

    tier_info = TIERS[payload.tier]
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": f"NorthFraim — {tier_info['label']}"},
                "unit_amount": tier_info["price_cents"],
            },
            "quantity": 1,
        }],
        metadata={"upload_id": payload.upload_id, "tier": payload.tier},
        success_url=f"{PUBLIC_DOMAIN}/?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{PUBLIC_DOMAIN}/",
    )
    return {"checkout_url": session.url}


class VerifyRequest(BaseModel):
    session_id: str


def expected_output_path(pdf_path: Path, started_at: float):
    """Finds the real output file, using the pattern CONFIRMED today by an
    actual render: movie_<random_id>.mp4 in data/movies/ — not the earlier
    guessed <input>.pdf.mp4 pattern, which was wrong. Since the random id
    isn't predictable in advance, this looks for the newest .mp4 created
    after the render started."""
    candidates = [
        p for p in MOVIE_DIR.glob("movie_*.mp4")
        if p.stat().st_mtime >= started_at
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run_pipeline_job(job_id: str, pdf_path: Path, tier: str):
    _write_job(job_id, {"status": "processing", "progress": 20, "message": f"Grok is writing your {tier} script — this one takes real time to get right, not built for speed."})
    started_at = time.time()
    TIER_TIMEOUTS = {
        "short": 900,
        "medium": 1800,
        "novel": 3600,
        "feature": 10800,
        "full_feature": 21600,
    }
    try:
        result = subprocess.run(
            ["python3", "job77_movie/core/movie_pipeline.py", str(pdf_path), "--tier", tier],
            capture_output=True,
            text=True,
            timeout=TIER_TIMEOUTS.get(tier, 900),
            cwd=str(BASE_DIR.parent) if (BASE_DIR.parent / "job77_movie").exists() else None,
        )
        if result.returncode != 0:
            _write_job(job_id, {
                "status": "error",
                "progress": 0,
                "message": f"Pipeline failed: {result.stderr[-400:]}",
            })
            return

        out_path = expected_output_path(pdf_path, started_at)
        if not out_path:
            _write_job(job_id, {
                "status": "error",
                "progress": 90,
                "message": "Pipeline finished but no new movie_*.mp4 file was found in data/movies/.",
            })
            return

        _write_job(job_id, {
            "status": "done",
            "progress": 100,
            "message": "Your film is ready.",
            "output_path": str(out_path),
        })
    except subprocess.TimeoutExpired:
        _write_job(job_id, {"status": "error", "progress": 0, "message": "Render timed out."})
    except Exception as e:
        _write_job(job_id, {"status": "error", "progress": 0, "message": str(e)})


@router.post("/api/verify-and-start")
async def verify_and_start(payload: VerifyRequest):
    if not stripe.api_key:
        raise HTTPException(500, "Stripe is not configured on the server.")

    try:
        session = stripe.checkout.Session.retrieve(payload.session_id)
    except Exception:
        raise HTTPException(400, "Could not verify that checkout session.")

    if session.payment_status != "paid":
        raise HTTPException(402, "Payment not completed.")

    upload_id = session.metadata.get("upload_id")
    tier = session.metadata.get("tier", "short")
    customer_email = ""
    if session.customer_details and session.customer_details.email:
        customer_email = session.customer_details.email

    pdf_path = UPLOAD_DIR / f"{upload_id}.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "Original upload is missing — cannot start render.")

    allowed, reason = _check_daily_limit(customer_email, tier)
    if not allowed:
        raise HTTPException(429, reason)

    job_id = uuid.uuid4().hex[:12]
    _write_job(job_id, {
        "status": "queued",
        "progress": 5,
        "message": f"Payment confirmed ({tier} tier), queued…",
        "tier": tier,
        "customer_email": customer_email,
        "created_date": datetime.now(timezone.utc).date().isoformat(),
    })

    thread = threading.Thread(target=run_pipeline_job, args=(job_id, pdf_path, tier), daemon=True)
    thread.start()

    return {"job_id": job_id}


@router.get("/api/status/{job_id}")
async def get_status(job_id: str):
    jobs = _read_jobs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job_id.")
    return job


@router.get("/api/download/{job_id}")
async def download(job_id: str):
    jobs = _read_jobs()
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "Film not ready yet.")
    return FileResponse(job["output_path"], media_type="video/mp4", filename="northfraim_film.mp4")


# --- Bring Your Own Cast: actor intake ---------------------------------

ACTOR_DIR = BASE_DIR.parent / "data" / "actor_profiles"
DB_PATH = BASE_DIR.parent / "data" / "watcher.db"


def _actor_db():
    return sqlite3.connect(DB_PATH)


@router.post("/api/actor/intake")
async def actor_intake(
    name: str = Form(...),
    email: str = Form(...),
    consent: bool = Form(...),
    photo: UploadFile = File(...),
    voice_sample: UploadFile = File(...),
):
    if not consent:
        raise HTTPException(
            400,
            "Consent is required before a face or voice can be used. "
            "Please confirm you have the right to license this person's likeness."
        )

    if photo.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(400, "Photo must be a JPEG or PNG.")
    if not (voice_sample.content_type or "").startswith("audio/"):
        raise HTTPException(400, "Voice sample must be an audio file.")

    actor_id = uuid.uuid4().hex[:12]
    actor_folder = ACTOR_DIR / actor_id
    actor_folder.mkdir(parents=True, exist_ok=True)

    photo_ext = ".jpg" if photo.content_type == "image/jpeg" else ".png"
    photo_path = actor_folder / f"photo{photo_ext}"
    photo_path.write_bytes(await photo.read())

    voice_path = actor_folder / f"voice_sample{Path(voice_sample.filename or '').suffix or '.wav'}"
    voice_path.write_bytes(await voice_sample.read())

    now = datetime.now(timezone.utc).isoformat()

    conn = _actor_db()
    try:
        cur = conn.execute(
            """INSERT INTO actor_profiles
               (name, email, face_data, body_data, licensing_price,
                total_uses, total_earnings, created_at,
                consent_given, consent_timestamp, voice_sample_path, voice_clone_id)
               VALUES (?, ?, ?, ?, ?, 0, 0.0, ?, ?, ?, ?, ?)""",
            (
                name, email, str(photo_path), None, None,
                now, 1, now, str(voice_path), None,
            ),
        )
        conn.commit()
        profile_id = cur.lastrowid
    finally:
        conn.close()

    return {"actor_id": actor_id, "profile_id": profile_id, "status": "intake_complete"}


# NOTE: static file mounting has to happen on the `app` object itself,
# not on this router. In your main app file, alongside
# app.include_router(web_router), add:
#
#     from fastapi.staticfiles import StaticFiles
#     app.mount("/", StaticFiles(directory="web", html=True), name="web")
#
# Mount this AFTER include_router(), and copy website/index.html into a
# `web/` folder relative to wherever your app runs from.
