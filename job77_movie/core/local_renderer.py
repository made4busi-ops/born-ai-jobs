#!/usr/bin/env python3
"""Local movie renderer -- FFmpeg replaces JSON2Video for scene assembly.

Same contract as video_renderer.render_movie(script, output_dir):
takes the same script dict, returns the same result dict, produces an
mp4 in output_dir. The rest of the pipeline never knows the difference.

What it does per scene:
  1. Generate the voice audio locally:
       - azure-style voices  -> edge-tts (same Microsoft neural voices,
                                same names, zero cost, no API key)
       - elevenlabs voices   -> ElevenLabs API called directly with our
                                own key (no middleman credits)
  2. Build the visual:
       - normal scene -> solid color background (same 5-color rotation)
                         + white caption text
       - hero scene   -> PixVerse-generated, guard-checked video
                         (reuses _generate_hero_scene_image from
                         video_renderer -- Guards 1 & 2 untouched)
  3. Scene length = audio length (matches JSON2Video's duration=-1
     behavior where the voice drives the scene).
Then all scenes are concatenated into one Full HD mp4.

Zero rendering credits. Ever.
"""
import os
import json
import shutil
import asyncio
import textwrap
import subprocess
import uuid as _uuid
from pathlib import Path

from neverx007.config import ELEVENLABS_API_KEY

# Reuse the exact same scene look and the exact same guard-checked
# hero-scene generator. Nothing about guards changes.
from job77_movie.core.video_renderer import (
    SCENE_COLORS,
    FALLBACK_VOICE,
    _generate_hero_scene_image,
)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
RESOLUTION = (1920, 1080)
FPS = 30
SILENT_SCENE_SECONDS = 4.0  # scene length when there is no narration

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


# ---------------------------------------------------------------------------
# Voice generation
# ---------------------------------------------------------------------------

# Some Azure voice names don't exist on the free edge-tts endpoint.
# Translate them to the closest available voice. voice_cast maps stay
# untouched -- translation happens here at the renderer's door.
EDGE_VOICE_MAP = {
    "en-US-DavisNeural": "en-US-ChristopherNeural",
    "en-US-TonyNeural": "en-US-GuyNeural",
    "en-US-JasonNeural": "en-US-BrianNeural",
    "en-US-SaraNeural": "en-US-AriaNeural",
    "en-US-NancyNeural": "en-US-MichelleNeural",
    "en-US-AmberNeural": "en-US-JennyNeural",
    "en-US-AshleyNeural": "en-US-AvaNeural",
    "en-US-BrandonNeural": "en-US-EricNeural",
    "en-US-JacobNeural": "en-US-RogerNeural",
    "en-US-MonicaNeural": "en-US-EmmaNeural",
    "en-US-AnaNeural": "en-US-AnaNeural",
}
# Last-resort voice if a requested one produces no audio.
EDGE_FALLBACK_VOICE = "en-US-ChristopherNeural"


def _tts_edge(text: str, voice: str, out_path: str) -> bool:
    """Generate speech with edge-tts (free Microsoft neural voices).
    Translates Azure voice names the free endpoint doesn't carry, and
    retries once with a known-good fallback voice so a bad name can
    never kill a whole render."""
    def _attempt(voice_name: str) -> bool:
        try:
            import edge_tts

            async def _run():
                communicate = edge_tts.Communicate(text, voice_name)
                await communicate.save(out_path)

            asyncio.run(_run())
            return os.path.exists(out_path) and os.path.getsize(out_path) > 0
        except Exception:
            return False

    translated = EDGE_VOICE_MAP.get(voice, voice)
    if _attempt(translated):
        return True
    if translated != EDGE_FALLBACK_VOICE:
        return _attempt(EDGE_FALLBACK_VOICE)
    return False


def _tts_elevenlabs(text: str, voice_id: str, out_path: str) -> bool:
    """Generate speech by calling ElevenLabs directly with our own key."""
    import requests

    if not ELEVENLABS_API_KEY:
        return False
    try:
        r = requests.post(
            ELEVENLABS_TTS_URL.format(voice_id=voice_id),
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
            },
            timeout=120,
        )
        if r.status_code != 200:
            return False
        with open(out_path, "wb") as f:
            f.write(r.content)
        return os.path.getsize(out_path) > 0
    except Exception:
        return False


def _audio_duration(path: str) -> float:
    """Measure audio length with ffprobe. Returns 0.0 on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Scene building
# ---------------------------------------------------------------------------

def _write_caption_file(caption: str, path: str):
    """Write the caption to a text file for drawtext's textfile option.
    Sidesteps every shell/filter escaping bug. Wrapped to fit 1920px
    at 72px font."""
    wrapped = "\n".join(textwrap.wrap(caption, width=40)) if caption else ""
    with open(path, "w", encoding="utf-8") as f:
        f.write(wrapped)


def _run_ffmpeg(args: list, timeout: int = 600) -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0
    except Exception:
        return False


def _render_color_scene(color: str, caption_file: str, audio_path: str,
                        duration: float, out_path: str) -> bool:
    """Solid color background + caption text + voice audio."""
    w, h = RESOLUTION
    vf = (
        f"drawtext=fontfile={FONT_PATH}:textfile={caption_file}:"
        f"fontsize=72:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"line_spacing=16"
    )
    args = [
        "-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:r={FPS}:d={duration:.3f}",
    ]
    if audio_path:
        args += ["-i", audio_path]
    else:
        args += ["-f", "lavfi", "-i",
                 f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration:.3f}"]
    args += [
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-t", f"{duration:.3f}",
        "-shortest",
        out_path,
    ]
    return _run_ffmpeg(args)


def _render_hero_scene(hero_video_path: str, caption_file: str, audio_path: str,
                       duration: float, out_path: str) -> bool:
    """Hero video background (looped to fill the audio), scaled and
    padded to Full HD, caption overlaid, voice audio on top."""
    w, h = RESOLUTION
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={FPS},"
        f"drawtext=fontfile={FONT_PATH}:textfile={caption_file}:"
        f"fontsize=72:fontcolor=white:x=(w-text_w)/2:y=h-text_h-80:"
        f"line_spacing=16"
    )
    args = ["-stream_loop", "-1", "-i", hero_video_path]
    if audio_path:
        args += ["-i", audio_path]
    else:
        args += ["-f", "lavfi", "-i",
                 f"anullsrc=channel_layout=stereo:sample_rate=44100:d={duration:.3f}"]
    args += [
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        "-t", f"{duration:.3f}",
        out_path,
    ]
    return _run_ffmpeg(args)


def _download_file(url: str, out_path: str) -> bool:
    import requests
    try:
        r = requests.get(url, timeout=120)
        if r.status_code != 200:
            return False
        with open(out_path, "wb") as f:
            f.write(r.content)
        return os.path.getsize(out_path) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main entry -- same contract as video_renderer.render_movie
# ---------------------------------------------------------------------------

def render_movie(script: dict, output_dir: str, poll_interval: int = 5,
                 timeout: int = 600) -> dict:
    """Render the script locally with FFmpeg. Same inputs, same output
    dict shape as the JSON2Video version. poll_interval/timeout are
    accepted for drop-in compatibility (no polling happens locally)."""
    job_id = script.get("title", "untitled")[:50]
    work_dir = Path(f"/tmp/local_render_{_uuid.uuid4().hex}")
    work_dir.mkdir(parents=True, exist_ok=True)

    voice_cast = script.get("voice_cast", {})
    voice_cast_meta = voice_cast.get("_meta", {})
    face_cast_data = script.get("face_cast", {})
    face_cast = face_cast_data.get("cast", {})
    hero_indices = set(face_cast_data.get("hero_scene_indices", []))

    scene_files = []
    try:
        for i, scene in enumerate(script.get("scenes", [])):
            color = SCENE_COLORS[i % len(SCENE_COLORS)]
            speaker = scene.get("speaker", "narrator")
            voice = voice_cast.get(speaker, voice_cast.get("narrator", FALLBACK_VOICE))
            narration = scene.get("narration", "") or ""
            caption = scene.get("caption", "") or ""

            # --- 1. voice audio -------------------------------------------
            audio_path = None
            duration = SILENT_SCENE_SECONDS
            if narration.strip():
                audio_path = str(work_dir / f"audio_{i}.mp3")
                if voice_cast_meta.get(speaker) == "elevenlabs":
                    ok = _tts_elevenlabs(narration, voice, audio_path)
                else:
                    ok = _tts_edge(narration, voice, audio_path)
                if not ok:
                    return {"success": False,
                            "error": f"Voice generation failed for scene {i} "
                                     f"(speaker={speaker}, voice={voice})"}
                duration = _audio_duration(audio_path)
                if duration <= 0:
                    return {"success": False,
                            "error": f"Could not measure audio duration for scene {i}"}
                duration += 0.5  # small breathing room, matches rendered feel

            # --- 2. caption file ------------------------------------------
            caption_file = str(work_dir / f"caption_{i}.txt")
            _write_caption_file(caption, caption_file)

            # --- 3. visual ------------------------------------------------
            scene_out = str(work_dir / f"scene_{i}.mp4")
            rendered = False

            if i in hero_indices and speaker in face_cast:
                cast_info = face_cast[speaker]
                hero_url = _generate_hero_scene_image(
                    cast_info["face_reference_id"],
                    cast_info["face_description"],
                    caption,
                    reference_photo_path=cast_info.get("reference_photo_path"),
                    job_id=job_id,
                )
                if hero_url:
                    hero_path = str(work_dir / f"hero_{i}.mp4")
                    if _download_file(hero_url, hero_path):
                        rendered = _render_hero_scene(
                            hero_path, caption_file, audio_path, duration, scene_out)

            if not rendered:
                # Normal scene, or hero fell back to solid color --
                # same fallback rule as the JSON2Video version.
                rendered = _render_color_scene(
                    color, caption_file, audio_path, duration, scene_out)

            if not rendered:
                return {"success": False,
                        "error": f"FFmpeg failed rendering scene {i}"}
            scene_files.append(scene_out)

        if not scene_files:
            return {"success": False, "error": "Script contained no scenes"}

        # --- 4. concatenate all scenes ------------------------------------
        concat_list = work_dir / "concat.txt"
        with open(concat_list, "w") as f:
            for p in scene_files:
                f.write(f"file '{p}'\n")

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        project_id = _uuid.uuid4().hex[:12]
        final_path = str(Path(output_dir) / f"movie_{project_id}.mp4")

        ok = _run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", final_path,
        ], timeout=timeout)
        if not ok or not os.path.exists(final_path):
            return {"success": False, "error": "FFmpeg concat step failed"}

        return {"success": True,
                "video_path": final_path,
                "video_url": None,  # local render -- no remote URL
                "project_id": project_id,
                "backend": "local_ffmpeg"}

    finally:
        # Never leave temp files behind -- the /tmp accumulation bug
        # stays dead.
        shutil.rmtree(work_dir, ignore_errors=True)
