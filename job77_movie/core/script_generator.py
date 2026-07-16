#!/usr/bin/env python3
"""Generate a movie script from extracted document text, using Grok."""
import json
import requests
from neverx007.config import XAI_API_KEY, XAI_MODEL, XAI_URL

def generate_script(extracted_text: str, max_scenes: int = 6) -> dict:
    if not XAI_API_KEY:
        return {"success": False, "error": "XAI_API_KEY not set"}

    prompt = f"""You are a scriptwriter turning a document into a short narrated video.

Read the document text below and produce a JSON object with:
- "title": a short movie title (5-8 words)
- "scenes": a list of up to {max_scenes} scenes, each with:
    - "narration": 1-3 sentences of spoken narration for this scene
    - "caption": short on-screen text (under 8 words) summarizing the scene

Document text:
{extracted_text[:6000]}

Return ONLY valid JSON, no markdown, no explanation."""

    try:
        r = requests.post(
            XAI_URL,
            headers={"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": XAI_MODEL, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7, "max_tokens": 2048},
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

        script = json.loads(raw_text)
        script["success"] = True
        return script

    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Could not parse Grok's response as JSON: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
