import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_MODEL = "grok-4.3"
XAI_URL = "https://api.x.ai/v1/chat/completions"
JSON2VIDEO_API_KEY = os.getenv("JSON2VIDEO_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
PIXVERSE_API_KEY = os.getenv("PIXVERSE_API_KEY", "")
