import base64
from pathlib import Path

from openai import OpenAI

from pipeline.config import OPENAI_API_KEY, IMAGE_MODEL, IMAGE_SIZE

client = OpenAI(api_key=OPENAI_API_KEY)

STYLE_SUFFIX = (
    ", cinematic historical documentary illustration, painterly digital art, "
    "dramatic volumetric lighting, rich color grading, highly detailed, 16:9 widescreen "
    "composition, no text, no watermark, no modern elements"
)


def generate_scene_image(prompt: str, out_path: Path) -> Path:
    full_prompt = f"{prompt}{STYLE_SUFFIX}"
    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=full_prompt,
        size=IMAGE_SIZE,
        n=1,
    )
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
