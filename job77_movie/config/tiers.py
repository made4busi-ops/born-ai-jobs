#!/usr/bin/env python3
"""
Tier configuration — the ONE place tier numbers live.

Every number below is a planning estimate, not a guarantee. Real scene
duration depends on how much narration text Grok writes per scene, which
JSON2Video auto-times (see video_renderer.py's "duration": -1). Treat
target_minutes as "roughly," not "exactly" — until you've run enough real
renders to know your actual words-per-scene average.
"""

TIERS = {
    "short": {
        "name": "Short",
        "price": 9,
        "target_minutes": 3,
        "max_scenes": 24,
        "chunks": 1,
        "max_tokens_per_chunk": 3072,
        "description": "Social media, teasers, TikTok-length",
    },
    "medium": {
        "name": "Medium",
        "price": 19,
        "target_minutes": 8,
        "max_scenes": 63,
        "chunks": 2,
        "max_tokens_per_chunk": 4096,
        "description": "YouTube-length, standard short film",
    },
    "novel": {
        "name": "Novel",
        "price": 39,
        "target_minutes": 15,
        "max_scenes": 118,
        "chunks": 3,
        "max_tokens_per_chunk": 4096,
        "description": "Short film / documentary length",
    },
    "feature": {
        "name": "Feature",
        "price": 99,
        "target_minutes": 45,
        "max_scenes": 355,
        "chunks": 8,
        "max_tokens_per_chunk": 4096,
        "description": "Feature-length, masterclass-length",
    },
    "full_feature": {
        "name": "Full Feature",
        "price": 299,
        "target_minutes": 90,
        "max_scenes": 710,
        "chunks": 15,
        "max_tokens_per_chunk": 8192,
        "description": "Full-length film, cinematic experience",
    },
}


def get_tier(tier_name: str) -> dict:
    """Get tier config by name, defaulting safely to 'short' if unknown."""
    return TIERS.get(tier_name, TIERS["short"])


def scenes_per_chunk(tier_name: str) -> int:
    """How many scenes each individual Grok call should aim for."""
    tier = get_tier(tier_name)
    import math
    return max(1, math.ceil(tier["max_scenes"] / tier["chunks"]))
