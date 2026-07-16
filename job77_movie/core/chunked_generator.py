#!/usr/bin/env python3
"""
Chunked script generator — handles ALL tiers through one code path,
with a real cast: a casting pass runs once before any scenes are
written, assigning each named character a fixed voice for the whole
film. Every chunk after that is told the fixed cast so it never
invents a second name for the same person.
"""
import json
import math
import time
import requests
from neverx007.config import XAI_API_KEY, XAI_MODEL, XAI_URL
from job77_movie.config.tiers import get_tier, scenes_per_chunk

MAX_CHUNK_INPUT_CHARS = 20000
WORDS_PER_SECOND_SPOKEN = 2.5

NARRATOR_VOICE = "en-US-DavisNeural"
CHARACTER_VOICE_POOL = [
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "en-US-AriaNeural",
    "en-US-JasonNeural",
    "en-US-AvaNeural",
    "en-GB-RyanNeural",
    "en-US-NancyNeural",
]


def _split_into_chunks(text: str, num_chunks: int) -> list:
    words = text.split()
    if not words:
        return [""]
    chunk_size = max(1, math.ceil(len(words) / num_chunks))
    pieces = []
    for i in range(0, len(words), chunk_size):
        piece = " ".join(words[i:i + chunk_size])
        if piece.strip():
            pieces.append(piece[:MAX_CHUNK_INPUT_CHARS])
    return pieces or [""]


def generate_cast(full_text: str) -> dict:
    """One casting call before any scenes are written. Reads the opening
    of the document and returns up to 6 named recurring characters —
    decided once, up front, like a real production casts before shooting."""
    if not XAI_API_KEY:
        return {"success": False, "error": "XAI_API_KEY not set"}

    sample = full_text[:8000]
    prompt = f"""You are a casting director reading the opening of a document that will become a narrated film.

Read the text below and identify up to 6 named characters who are central to the story. Do not include minor one-off mentions.

Document sample:
{sample}

Return ONLY a JSON object, no markdown, no explanation:
{{"characters": ["Name One", "Name Two"]}}

If there are no clearly named recurring characters (e.g. this is a technical or business document), return {{"characters": []}}."""

    try:
        r = requests.post(
            XAI_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": XAI_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.3, "max_tokens": 512},
            timeout=60,
        )
        data = r.json()
        if "choices" not in data:
            return {"success": False, "error": f"Grok error: {data}"}
        raw_text = data["choices"][0]["message"]["content"].strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()
        result = json.loads(raw_text)
        result["success"] = True
        return result
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Could not parse casting response as JSON: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _lookup_cloned_voice(character_name: str):
    """Check actor_profiles for a real cloned voice matching this
    character name. Returns (voice_id, is_clone=True) if found and
    consented, else (None, False). Case-insensitive exact match on name."""
    import sqlite3
    from pathlib import Path
    db_path = Path("data/watcher.db")
    if not db_path.exists():
        return None, False
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT voice_clone_id FROM actor_profiles "
        "WHERE lower(name) = lower(?) AND consent_given = 1 AND voice_clone_id IS NOT NULL",
        (character_name,)
    ).fetchone()
    conn.close()
    if row and row[0]:
        return row[0], True
    return None, False


def build_voice_cast(characters: list) -> dict:
    """Assign each character a voice, plus the narrator. Real actor
    clones (matched by name in actor_profiles) take priority over the
    generic pool. Same character always gets the same voice for the
    whole film."""
    voice_cast = {"narrator": NARRATOR_VOICE}
    voice_cast_meta = {}  # tracks which entries are real clones vs pool voices
    pool_index = 0
    for name in characters:
        cloned_voice_id, is_clone = _lookup_cloned_voice(name)
        if is_clone:
            voice_cast[name] = cloned_voice_id
            voice_cast_meta[name] = "elevenlabs"
        else:
            voice_cast[name] = CHARACTER_VOICE_POOL[pool_index % len(CHARACTER_VOICE_POOL)]
            voice_cast_meta[name] = "azure"
            pool_index += 1
    voice_cast["_meta"] = voice_cast_meta
    return voice_cast


def _lookup_locked_face(character_name: str):
    """Check actor_profiles for a real locked face matching this
    character name. Returns (face_reference_id, face_description,
    is_locked=True) if found and consented, else (None, None, False)."""
    import sqlite3
    from pathlib import Path
    db_path = Path("data/watcher.db")
    if not db_path.exists():
        return None, None, False
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT face_reference_id, face_description, face_data FROM actor_profiles "
        "WHERE lower(name) = lower(?) AND consent_given = 1 AND face_reference_id IS NOT NULL",
        (character_name,)
    ).fetchone()
    conn.close()
    if row and row[0]:
        return row[0], row[1], row[2], True
    return None, None, None, False


# Max number of real face-generated "hero scenes" per movie, regardless
# of tier or scene count. Real generation costs real credits (35-45 per
# PixVerse call) and takes 30-90s each -- this caps runaway cost on a
# script that happens to tag a cast member in many scenes. Excess hero
# scenes past this cap fall back to the existing solid-color treatment
# rather than failing the whole render.
MAX_FACE_GENERATIONS_PER_MOVIE = 10


def build_face_cast(scenes: list, characters: list) -> dict:
    """Determine which scenes should get real face-generated visuals.
    Only scenes where a locked-face character is the speaker qualify --
    this keeps cost bounded and matches what the customer actually paid
    for (their cast member appearing), not every background in the film.

    Returns a dict: {"cast": {name: {face_reference_id, face_description}},
    "hero_scene_indices": [list of scene indices that qualify, capped]}
    """
    locked_cast = {}
    for name in characters:
        face_id, face_desc, face_photo_path, is_locked = _lookup_locked_face(name)
        if is_locked:
            locked_cast[name] = {
                "face_reference_id": face_id,
                "face_description": face_desc,
                "reference_photo_path": face_photo_path,
            }

    hero_scene_indices = []
    if locked_cast:
        for i, scene in enumerate(scenes):
            speaker = scene.get("speaker", "narrator")
            if speaker in locked_cast:
                hero_scene_indices.append(i)
                if len(hero_scene_indices) >= MAX_FACE_GENERATIONS_PER_MOVIE:
                    break

    return {"cast": locked_cast, "hero_scene_indices": hero_scene_indices}


def generate_script_chunk(text_chunk: str, handoff: dict, cast_names: list,
                           target_scenes: int, chunk_num: int, total_chunks: int,
                           max_tokens: int) -> dict:
    """Generate one chunk of the script, aware of the fixed cast and what
    came before."""
    if not XAI_API_KEY:
        return {"success": False, "error": "XAI_API_KEY not set"}

    cast_note = ""
    if cast_names:
        cast_note = f"\nFixed cast for this film (use these exact names, do not invent new main characters): {', '.join(cast_names)}\n"

    from neverx007.scriptwriter.cast_orchestrator import get_available_cast, build_cast_instruction
    real_cast = get_available_cast(allowed_names=cast_names)
    if real_cast:
        cast_note += "\n" + build_cast_instruction(real_cast) + "\n"

    continuation_note = ""
    if chunk_num > 1:
        continuation_note = f"""
THIS IS A CONTINUATION — chunk {chunk_num} of {total_chunks}. Do not
restart the story.

Story so far: {handoff.get('plot_state', 'beginning of the story')}
Established tone: {handoff.get('tone', 'to be determined by you')}
"""

    prompt = f"""You are a scriptwriter turning a document into a narrated video.
{cast_note}{continuation_note}
Read the document text below and produce a JSON object with:
- "title": a short movie title (5-8 words) — only meaningful on chunk 1, otherwise repeat the established title
- "scenes": a list of up to {target_scenes} scenes, each with:
    - "narration": 1-3 sentences of spoken narration for this scene
    - "caption": short on-screen text (under 8 words) summarizing the scene
    - "speaker": "narrator" for descriptive narration, OR the exact character name from the fixed cast list if this scene is written as that character speaking or thinking directly

DIALOGUE RULE: if two or more characters are talking to each other, do NOT
combine their exchange into one scene. Break it into separate consecutive
scenes, one per line of dialogue, each with "speaker" set to whichever
single character is talking in that scene. Example -- a back-and-forth
between Jonathan and Dracula becomes multiple scenes in sequence, alternating
speaker between "Jonathan" and "Dracula", each scene holding only that one
character's line. This matches how the line will actually be filmed --
one character's face and voice per shot, cut together afterward.
- "characters": list of named characters that appear in this chunk (should match the fixed cast list)
- "plot_summary": 2-3 sentences summarizing where the story stands after this chunk
- "tone": one or two words describing the tone (e.g. "tense", "whimsical", "reflective")

Document text for this chunk:
{text_chunk}

Return ONLY valid JSON, no markdown, no explanation."""

    try:
        r = requests.post(
            XAI_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": XAI_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7, "max_tokens": max_tokens},
            timeout=90,
        )
        data = r.json()
        if "choices" not in data:
            return {"success": False, "error": f"Grok error: {data}"}

        raw_text = data["choices"][0]["message"]["content"].strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            if raw_text.startswith("json"):
                raw_text = raw_text[4:].strip()

        result = json.loads(raw_text)
        result["success"] = True
        return result

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": (
                f"Could not parse Grok's response as JSON: {e}. "
                f"If this happens on Feature/Full Feature tiers, max_tokens "
                f"may still be too low for the requested scene count."
            ),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_for_tier(full_text: str, tier: str) -> dict:
    """Generate a complete cast + script for the given tier, chunked as needed."""
    tier_config = get_tier(tier)
    num_chunks = tier_config["chunks"]
    target_total_scenes = tier_config["max_scenes"]
    per_chunk_scenes = scenes_per_chunk(tier)
    max_tokens = tier_config["max_tokens_per_chunk"]

    cast_result = generate_cast(full_text)
    if not cast_result.get("success"):
        return cast_result
    cast_names = cast_result.get("characters", [])
    voice_cast = build_voice_cast(cast_names)

    text_pieces = _split_into_chunks(full_text, num_chunks)
    actual_chunks = len(text_pieces)

    handoff = {"plot_state": "", "tone": ""}
    all_scenes = []
    title = None

    for i, piece in enumerate(text_pieces):
        result = generate_script_chunk(
            piece, handoff, cast_names, per_chunk_scenes,
            chunk_num=i + 1, total_chunks=actual_chunks, max_tokens=max_tokens,
        )
        if not result.get("success"):
            result["failed_at_chunk"] = i + 1
            result["total_chunks"] = actual_chunks
            return result

        if title is None:
            title = result.get("title", "Untitled")

        handoff["plot_state"] = result.get("plot_summary", handoff["plot_state"])
        handoff["tone"] = result.get("tone", handoff["tone"])

        all_scenes.extend(result.get("scenes", []))

        if len(all_scenes) >= target_total_scenes:
            break
        if i < actual_chunks - 1:
            time.sleep(1)

    all_scenes = all_scenes[:target_total_scenes]

    total_words = sum(len(s.get("narration", "").split()) for s in all_scenes)
    estimated_seconds = round(total_words / WORDS_PER_SECOND_SPOKEN) if total_words else 0

    face_cast = build_face_cast(all_scenes, cast_names)

    return {
        "success": True,
        "title": title or "Untitled",
        "scenes": all_scenes,
        "cast": cast_names,
        "voice_cast": voice_cast,
        "face_cast": face_cast,
        "tier": tier,
        "chunks_used": actual_chunks,
        "estimated_duration_seconds": estimated_seconds,
        "estimated_duration_label": f"~{estimated_seconds // 60}m {estimated_seconds % 60}s (estimate, not guaranteed)",
    }
