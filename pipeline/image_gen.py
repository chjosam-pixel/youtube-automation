import base64
import time
from pathlib import Path

from openai import OpenAI, RateLimitError

from pipeline.config import OPENAI_API_KEY, IMAGE_MODEL, IMAGE_SIZE

client = OpenAI(api_key=OPENAI_API_KEY)

STYLE_SUFFIX = (
    ", modern bright digital illustration, vivid saturated colors, clean crisp high-key lighting, "
    "trendy contemporary news-graphic style, sharp and highly detailed, 16:9 widescreen "
    "composition, no text, no watermark, no dark or muddy tones"
)

MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 20


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
    result = _generate_with_retry(full_prompt)
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
