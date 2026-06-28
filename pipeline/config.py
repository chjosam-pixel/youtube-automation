import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
CREDENTIALS_DIR = ROOT_DIR / "credentials"
TOPICS_STATE_FILE = ROOT_DIR / "pipeline" / "used_topics.json"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
# Default voice id is a placeholder; set ELEVENLABS_VOICE_ID to the Arabic
# narrator voice "Mustafa" from the ElevenLabs Voice Library for Arabic narration.
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

YOUTUBE_CLIENT_SECRET_FILE = ROOT_DIR / os.environ.get(
    "YOUTUBE_CLIENT_SECRET_FILE", "credentials/client_secret.json"
)
YOUTUBE_TOKEN_FILE = ROOT_DIR / os.environ.get(
    "YOUTUBE_TOKEN_FILE", "credentials/token.json"
)

# Script / content settings
SCRIPT_MODEL = os.environ.get("SCRIPT_MODEL", "gpt-4o")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = "1536x1024"  # landscape, closest gpt-image-1 support to 16:9
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_MIN_SECONDS = 30.0
SHORTS_MAX_SECONDS = 58.0

TARGET_MIN_MINUTES = 5
TARGET_MAX_MINUTES = 10

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is not set")
if not ELEVENLABS_API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY environment variable is not set")

OUTPUT_DIR.mkdir(exist_ok=True)
CREDENTIALS_DIR.mkdir(exist_ok=True)
