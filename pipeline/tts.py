import base64
import json
from pathlib import Path

import requests

from pipeline.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL_ID

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

VOICE_SETTINGS = {
    "stability": 0.65,
    "similarity_boost": 0.75,
    "style": 0.15,
    "use_speaker_boost": True,
}


def synthesize_with_timestamps(text: str, out_audio_path: Path) -> dict:
    """Calls ElevenLabs TTS with character-level timestamps.

    Returns the alignment dict: {"characters": [...], "character_start_times_seconds": [...],
    "character_end_times_seconds": [...]}
    """
    url = API_URL.format(voice_id=ELEVENLABS_VOICE_ID)
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    audio_bytes = base64.b64decode(data["audio_base64"])
    out_audio_path.write_bytes(audio_bytes)

    alignment = data["alignment"]
    align_path = out_audio_path.with_suffix(".json")
    align_path.write_text(json.dumps(alignment, ensure_ascii=False))
    return alignment


def synthesize_scenes(scenes: list[dict], out_dir: Path) -> list[dict]:
    """Synthesizes audio for each scene narration text.

    Returns list of dicts merged into scenes with keys: audio_path, alignment
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for i, scene in enumerate(scenes):
        audio_path = out_dir / f"scene_{i:02d}.mp3"
        alignment = synthesize_with_timestamps(scene["narration"], audio_path)
        results.append({**scene, "audio_path": audio_path, "alignment": alignment})
    return results
