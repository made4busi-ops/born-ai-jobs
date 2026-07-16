#!/usr/bin/env python3
"""
lipsync_generator.py — takes a real ElevenLabs voice clone and a
PixVerse-generated hero scene video, and produces a lip-synced final
version where the mouth actually matches the spoken audio.

Real pipeline, three steps:
1. Generate real downloadable audio directly from ElevenLabs (not
   through JSON2Video, which doesn't expose the raw audio file)
2. Upload that audio to PixVerse
3. Call PixVerse's Speech(LipSync) endpoint with the hero-scene
   video_id + the uploaded audio, producing a new lip-synced video

This is a genuinely separate audio generation from the one JSON2Video
does for the final assembled voice track -- known duplication, not a
bug. Combining them into one audio generation is a future optimization,
not required for this to work correctly.
"""
import uuid
import requests

from neverx007.config import ELEVENLABS_API_KEY, PIXVERSE_API_KEY

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
PIXVERSE_BASE = "https://app-api.pixverse.ai"


def generate_elevenlabs_audio(voice_id: str, text: str, out_path: str) -> tuple:
    """Call ElevenLabs directly to get a real downloadable audio file
    using the cloned voice. Returns (success: bool, diagnostic: str)
    -- on failure the diagnostic explains exactly what went wrong and
    is also logged to the errors table automatically."""
    from neverx007.diagnostics import diagnose_http_response, diagnose_exception

    if not ELEVENLABS_API_KEY:
        return False, "ELEVENLABS_API_KEY not set"

    try:
        r = requests.post(
            f"{ELEVENLABS_BASE}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
            },
            timeout=60,
        )
        if r.status_code != 200:
            diagnostic = diagnose_http_response("ElevenLabs TTS", r, f"voice_id={voice_id}")
            return False, diagnostic
        with open(out_path, "wb") as f:
            f.write(r.content)
        return True, "OK"
    except Exception as e:
        diagnostic = diagnose_exception("ElevenLabs TTS", e, f"voice_id={voice_id}")
        return False, diagnostic


def upload_audio_to_pixverse(audio_path: str) -> int:
    """Upload the ElevenLabs audio file to PixVerse. Returns the
    media_id on success, or None on failure."""
    if not PIXVERSE_API_KEY:
        return None

    trace_id = str(uuid.uuid4())
    try:
        with open(audio_path, "rb") as f:
            files = {"file": f}
            headers = {"Ai-Trace-Id": trace_id, "API-KEY": PIXVERSE_API_KEY}
            r = requests.post(
                f"{PIXVERSE_BASE}/openapi/v2/media/upload",
                headers=headers,
                files=files,
                timeout=60,
            )
        data = r.json()
        if data.get("ErrCode") != 0:
            return None
        return data.get("Resp", {}).get("media_id")
    except Exception:
        return None


def apply_lipsync(source_video_id: str, audio_media_id: int) -> dict:
    """Call PixVerse's Speech(LipSync) endpoint to sync the hero-scene
    video's mouth movement to the real audio. Returns a dict with
    success/error and the resulting video_id on success -- caller
    still needs to poll for the actual result URL."""
    if not PIXVERSE_API_KEY:
        return {"success": False, "error": "PIXVERSE_API_KEY not set"}

    trace_id = str(uuid.uuid4())
    try:
        r = requests.post(
            f"{PIXVERSE_BASE}/openapi/v2/video/lip_sync/generate",
            headers={"API-KEY": PIXVERSE_API_KEY, "Ai-Trace-Id": trace_id, "Content-Type": "application/json"},
            json={
                "source_video_id": int(source_video_id),
                "audio_media_id": int(audio_media_id),
            },
            timeout=30,
        )
        data = r.json()
        if data.get("ErrCode") != 0:
            return {"success": False, "error": f"PixVerse rejected lip-sync request: {data}"}
        video_id = data.get("Resp", {}).get("video_id")
        if not video_id:
            return {"success": False, "error": f"No video_id returned: {data}"}
        return {"success": True, "video_id": video_id}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {e}"}


def poll_pixverse_result(video_id: str, max_wait_seconds: int = 100) -> str:
    """Poll for a PixVerse generation result (works for both regular
    generation and lip-sync). Returns the final video URL on success,
    or None on failure/timeout."""
    import time

    if not PIXVERSE_API_KEY:
        return None

    waited = 0
    while waited < max_wait_seconds:
        time.sleep(5)
        waited += 5
        try:
            trace_id = str(uuid.uuid4())
            r = requests.get(
                f"{PIXVERSE_BASE}/openapi/v2/video/result/{video_id}",
                headers={"API-KEY": PIXVERSE_API_KEY, "Ai-Trace-Id": trace_id},
                timeout=30,
            )
            data = r.json()
            resp = data.get("Resp", {})
            if resp.get("status") == 1:
                return resp.get("url")
            if resp.get("status") in (7, 8):
                return None
        except Exception:
            continue
    return None


def generate_lipsynced_hero_scene(source_video_id: str, elevenlabs_voice_id: str,
                                   narration_text: str, temp_audio_path: str) -> dict:
    """Full pipeline: real ElevenLabs audio -> upload to PixVerse ->
    apply lip-sync to the hero-scene video -> poll for the final
    lip-synced result. Returns a dict with success/error/url."""
    audio_ok, audio_diagnostic = generate_elevenlabs_audio(elevenlabs_voice_id, narration_text, temp_audio_path)
    if not audio_ok:
        return {"success": False, "error": f"ElevenLabs audio generation failed: {audio_diagnostic}"}

    audio_media_id = upload_audio_to_pixverse(temp_audio_path)
    if not audio_media_id:
        return {"success": False, "error": "Failed to upload audio to PixVerse"}

    lipsync_result = apply_lipsync(source_video_id, audio_media_id)
    if not lipsync_result.get("success"):
        return lipsync_result

    final_url = poll_pixverse_result(lipsync_result["video_id"])
    if not final_url:
        return {"success": False, "error": "Lip-sync generation timed out or failed"}

    return {"success": True, "url": final_url, "lipsync_applied": True}
