import base64
import time
from pathlib import Path

from openai import BadRequestError, OpenAI, RateLimitError

from pipeline.config import OPENAI_API_KEY, IMAGE_MODEL, IMAGE_SIZE

client = OpenAI(api_key=OPENAI_API_KEY)

STYLE_SUFFIX = (
    ", photorealistic, shot on a professional camera, realistic lighting and textures, "
    "bright clean high-key lighting, vivid natural colors, sharp focus, highly detailed, "
    "16:9 widescreen composition, no text, no watermark, no dark or muddy tones, "
    "not an illustration, not a painting, not cartoon, not 3D render"
)

# Real news topics (conflict, disasters, etc.) routinely trip OpenAI's image
# safety system on the first try. Rather than let one blocked scene crash the
# whole run, soften the prompt to a tasteful, non-graphic angle on the same
# subject before giving up.
SAFE_RETRY_SUFFIX = (
    ", tasteful and non-graphic news photograph, no visible violence, no weapons, "
    "no blood, no injured people, no graphic combat imagery, respectful documentary "
    "style focusing on people, places, government buildings, maps, or symbolic imagery "
    "related to the topic"
)

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 20


def _is_moderation_blocked(error: BadRequestError) -> bool:
    body = getattr(error, "body", None) or {}
    return isinstance(body, dict) and body.get("code") == "moderation_blocked"


def _generate_with_retry(full_prompt: str):
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return client.images.generate(
                model=IMAGE_MODEL,
                prompt=full_prompt,
                size=IMAGE_SIZE,
                n=1,
            )
        except RateLimitError as e:
            last_error = e
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            print(f"Rate limited generating image, retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)
    raise last_error


def generate_scene_image(prompt: str, out_path: Path) -> Path:
    full_prompt = f"{prompt}{STYLE_SUFFIX}"
    try:
        result = _generate_with_retry(full_prompt)
    except BadRequestError as e:
        if not _is_moderation_blocked(e):
            raise
        print(f"Image prompt blocked by safety system, retrying with a softened prompt: {e}")
        result = _generate_with_retry(f"{prompt}{SAFE_RETRY_SUFFIX}")
    item = result.data[0]
    if getattr(item, "b64_json", None):
        image_bytes = base64.b64decode(item.b64_json)
    else:
        import requests

        image_bytes = requests.get(item.url, timeout=60).content
    out_path.write_bytes(image_bytes)
    return out_path


def generate_images_for_scenes(scenes: list[dict], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(scenes):
        out_path = out_dir / f"scene_{i:02d}.png"
        generate_scene_image(scene["image_prompt"], out_path)
        paths.append(out_path)
    return paths
