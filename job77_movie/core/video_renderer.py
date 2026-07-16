import os
#!/usr/bin/env python3
"""Render a structured script into a real video using JSON2Video.

Now voice-aware: each scene's "speaker" field is looked up against the
script's voice_cast map, so narration and each character get their own
consistent voice instead of one flat narrator for everything.
"""
import time
import requests
from pathlib import Path
from neverx007.config import JSON2VIDEO_API_KEY

JSON2VIDEO_BASE = "https://api.json2video.com/v2/movies"
SCENE_COLORS = ["#1B2A41", "#3A506B", "#5BC0BE", "#0B132B", "#6B2D5C"]

FALLBACK_VOICE = "en-US-DavisNeural"  # used only if a script has no voice_cast at all


ELEVENLABS_CONNECTION_ID = "northfraim-elevenlabs"


def _log_handoff(job_id: str, guard_1_result: dict, guard_2_result: dict, sealed: bool):
    """Write one guard-check attempt to handoff_log -- the persistent
    record of what passed, what failed, and why. This is the machine's
    memory: every attempt is kept, not just the final outcome."""
    import sqlite3
    from datetime import datetime, timezone
    from pathlib import Path

    db_path = Path("data/watcher.db")
    if not db_path.exists():
        return
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO handoff_log (envelope_id, job_id, from_room, to_room, "
        "guard_1_passed, guard_1_score, guard_2_passed, guard_2_score, seal, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            __import__("uuid").uuid4().hex,
            job_id,
            "pixverse_generation",
            "movie_renderer",
            int(guard_1_result.get("passed", False)),
            guard_1_result.get("score"),
            int(guard_2_result.get("passed", False)) if guard_2_result else None,
            guard_2_result.get("score") if guard_2_result else None,
            "sealed" if sealed else "rejected",
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def _download_video_frame(video_url: str, out_path: str) -> bool:
    """Download the generated hero-scene video and extract its first
    frame as a still image, for Guard 1 to compare against the
    reference photo. Returns True on success."""
    import requests
    try:
        r = requests.get(video_url, timeout=60)
        temp_video = out_path + ".mp4"
        with open(temp_video, "wb") as f:
            f.write(r.content)

        import cv2
        cap = cv2.VideoCapture(temp_video)
        success, frame = cap.read()
        cap.release()
        if not success:
            return False
        cv2.imwrite(out_path, frame)
        return True
    except Exception:
        return False


def _generate_hero_scene_image(face_reference_id: str, face_description: str, scene_caption: str,
                                reference_photo_path: str = None, job_id: str = "unknown",
                                elevenlabs_voice_id: str = None, narration_text: str = None) -> str:
    """Call PixVerse to generate a real background image for a hero
    scene, anchored to the locked face. Runs Guard 1 (face match)
    against the result; retries once with a reinforced prompt if the
    guard fails. Every attempt is logged to handoff_log. Returns an
    image URL on success, or None on any failure -- caller falls back
    to solid color rather than failing the whole render over one bad scene."""
    import uuid as _uuid
    import requests
    from neverx007.config import PIXVERSE_API_KEY
    from neverx007.guards import face_match as guard_face_match

    if not PIXVERSE_API_KEY:
        return None

    def _attempt(prompt_text: str):
        trace_id = str(_uuid.uuid4())
        try:
            r = requests.post(
                "https://app-api.pixverse.ai/openapi/v2/video/img/generate",
                headers={"API-KEY": PIXVERSE_API_KEY, "Ai-Trace-Id": trace_id, "Content-Type": "application/json"},
                json={
                    "img_id": int(face_reference_id),
                    "prompt": prompt_text,
                    "model": "v6",
                    "duration": 5,
                    "quality": "540p",
                    "water_mark": False,
                },
                timeout=30,
            )
            data = r.json()
            if data.get("ErrCode") != 0:
                return None
            video_id = data.get("Resp", {}).get("video_id")
            if not video_id:
                return None
        except Exception:
            return None

        for _ in range(20):
            time.sleep(5)
            try:
                poll_trace = str(_uuid.uuid4())
                status_r = requests.get(
                    f"https://app-api.pixverse.ai/openapi/v2/video/result/{video_id}",
                    headers={"API-KEY": PIXVERSE_API_KEY, "Ai-Trace-Id": poll_trace},
                    timeout=30,
                )
                status_data = status_r.json()
                resp = status_data.get("Resp", {})
                if resp.get("status") == 1:
                    return resp.get("url"), video_id
                if resp.get("status") in (7, 8):
                    return None, None
            except Exception:
                continue
        return None, None

    base_prompt = f"{face_description}, {scene_caption}, natural lighting, no camera cuts, standing still"

    for attempt_num, prompt_text in enumerate([
        base_prompt,
        f"{face_description}, {face_description}, {scene_caption}, natural lighting, no camera cuts, standing still, consistent facial features throughout",
    ], start=1):
        video_url, attempt_video_id = _attempt(prompt_text)

        if not video_url:
            _log_handoff(job_id, {"passed": False, "score": None}, None, sealed=False)
            continue

        if not reference_photo_path:
            # No reference photo available to check against -- can't run
            # Guard 1, so we accept the generation as-is (best effort).
            return video_url

        frame_path = f"/tmp/hero_frame_{_uuid.uuid4().hex}.jpg"
        if not _download_video_frame(video_url, frame_path):
            _log_handoff(job_id, {"passed": False, "score": None}, None, sealed=False)
            continue

        guard_1_result = guard_face_match.check(reference_photo_path, frame_path)

        # Clean up immediately -- pass or fail, we're done with these.
        # Leaving temp files behind forever was the known /tmp accumulation
        # bug found during factory sweeps.
        for _cleanup_path in (frame_path, frame_path + ".mp4"):
            try:
                if os.path.exists(_cleanup_path):
                    os.remove(_cleanup_path)
            except Exception:
                pass

        if guard_1_result.get("passed"):
            # Guard 1 passed -- if we have voice info, also try
            # lip-sync and check Guard 2. Lip-sync failure does NOT
            # discard the video -- it falls back to the non-synced
            # hero scene rather than losing the whole shot.
            if elevenlabs_voice_id and narration_text:
                from neverx007.guards.lipsync_generator import generate_lipsynced_hero_scene
                from neverx007.guards import lipsync_check as guard_lipsync

                import uuid as _u2
                temp_audio = f"/tmp/lipsync_{_u2.uuid4().hex}.mp3"
                lipsync_result = generate_lipsynced_hero_scene(
                    source_video_id=str(attempt_video_id) if attempt_video_id else None,
                    elevenlabs_voice_id=elevenlabs_voice_id,
                    narration_text=narration_text,
                    temp_audio_path=temp_audio,
                )
                guard_2_result = guard_lipsync.check(lipsync_result)
                _log_handoff(job_id, guard_1_result, guard_2_result, sealed=guard_2_result.get("passed", False))

                if guard_2_result.get("passed"):
                    return lipsync_result.get("url")
                # Guard 2 failed -- fall back to the non-synced but
                # face-matched video rather than losing the scene.
                return video_url

            _log_handoff(job_id, guard_1_result, None, sealed=True)
            return video_url

        _log_handoff(job_id, guard_1_result, None, sealed=False)
        # Loop continues to next (reinforced) prompt attempt

    return None


def build_movie_json(script: dict) -> dict:
    voice_cast = script.get("voice_cast", {})
    voice_cast_meta = voice_cast.get("_meta", {})
    face_cast_data = script.get("face_cast", {})
    face_cast = face_cast_data.get("cast", {})
    hero_indices = set(face_cast_data.get("hero_scene_indices", []))

    scenes = []
    for i, scene in enumerate(script.get("scenes", [])):
        color = SCENE_COLORS[i % len(SCENE_COLORS)]
        speaker = scene.get("speaker", "narrator")
        voice = voice_cast.get(speaker, voice_cast.get("narrator", FALLBACK_VOICE))

        voice_element = {"type": "voice", "text": scene.get("narration", ""), "voice": voice}

        if voice_cast_meta.get(speaker) == "elevenlabs":
            voice_element["model"] = "elevenlabs"
            voice_element["connection"] = ELEVENLABS_CONNECTION_ID
        else:
            voice_element["model"] = "azure"

        elements = [
            {"type": "text", "text": scene.get("caption", ""),
             "settings": {"font-family": "Arial", "font-size": "72px", "color": "#FFFFFF"},
             "duration": -1},
            voice_element
        ]

        scene_json = {"elements": elements, "background-color": color}

        # Hero scene: try real face-generated visual. Falls back to
        # solid color on any failure -- one bad generation should
        # never take down the whole render.
        if i in hero_indices and speaker in face_cast:
            cast_info = face_cast[speaker]
            hero_url = _generate_hero_scene_image(
                cast_info["face_reference_id"],
                cast_info["face_description"],
                scene.get("caption", ""),
                reference_photo_path=cast_info.get("reference_photo_path"),
                job_id=script.get("title", "untitled")[:50],
            )
            if hero_url:
                elements.insert(0, {"type": "video", "src": hero_url, "duration": -1})

        scenes.append(scene_json)
    return {"resolution": "full-hd", "quality": "high", "scenes": scenes}


def render_movie(script: dict, output_dir: str, poll_interval: int = 5, timeout: int = 600) -> dict:
    if not JSON2VIDEO_API_KEY:
        return {"success": False, "error": "JSON2VIDEO_API_KEY not set"}

    movie_json = build_movie_json(script)
    headers = {"x-api-key": JSON2VIDEO_API_KEY, "Content-Type": "application/json"}

    try:
        r = requests.post(JSON2VIDEO_BASE, headers=headers, json=movie_json, timeout=30)
        data = r.json()
    except Exception as e:
        return {"success": False, "error": f"Submit failed: {e}"}

    if not data.get("success"):
        return {"success": False, "error": f"JSON2Video rejected the job: {data}"}

    project_id = data.get("project")
    if not project_id:
        return {"success": False, "error": f"No project ID returned: {data}"}

    waited = 0
    while waited < timeout:
        time.sleep(poll_interval)
        waited += poll_interval
        try:
            status_r = requests.get(JSON2VIDEO_BASE, headers=headers, params={"project": project_id}, timeout=30)
            status_data = status_r.json()
        except Exception:
            continue

        movie = status_data.get("movie", {})
        status = movie.get("status")

        if status == "done":
            video_url = movie.get("url")
            if not video_url:
                return {"success": False, "error": "Render done but no URL returned", "raw": movie}
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            local_path = Path(output_dir) / f"movie_{project_id}.mp4"
            video_data = requests.get(video_url, timeout=120)
            local_path.write_bytes(video_data.content)
            return {"success": True, "video_path": str(local_path), "video_url": video_url, "project_id": project_id}

        if status == "error":
            return {"success": False, "error": movie.get("message", "Unknown render error"), "raw": movie}

    return {"success": False, "error": f"Timed out after {timeout}s waiting for render"}
