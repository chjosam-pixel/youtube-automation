import base64
import textwrap
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI

from pipeline.config import OPENAI_API_KEY, IMAGE_MODEL
from pipeline.image_gen import _generate_with_retry

client = OpenAI(api_key=OPENAI_API_KEY)

THUMB_SIZE = (1280, 720)
ARABIC_FONT_PATH = "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Bold.ttf"


def _to_display_text(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def _generate_background(topic: str, out_path: Path) -> Path:
    prompt = (
        f"A dramatic cinematic key art poster representing the historical theme: {topic}. "
        "Epic historical documentary thumbnail style, painterly, dramatic lighting, "
        "high contrast, no text, no watermark, 16:9 widescreen."
    )
    result = _generate_with_retry(prompt)
    item = result.data[0]
    if getattr(item, "b64_json", None):
        image_bytes = base64.b64decode(item.b64_json)
    else:
        import requests

        image_bytes = requests.get(item.url, timeout=60).content
    out_path.write_bytes(image_bytes)
    return out_path


def _draw_title_text(image: Image.Image, title: str) -> Image.Image:
    image = image.convert("RGB").resize(THUMB_SIZE)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = 72
    font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)

    wrapped = textwrap.wrap(title, width=22)
    while len(wrapped) > 3 and font_size > 36:
        font_size -= 4
        font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)
        wrapped = textwrap.wrap(title, width=22)

    wrapped = [_to_display_text(line) for line in wrapped]

    line_height = font_size + 14
    total_height = line_height * len(wrapped)
    y = image.size[1] - total_height - 60

    gradient = Image.new("L", (1, image.size[1]), color=0)
    for yy in range(image.size[1]):
        if yy > image.size[1] * 0.5:
            gradient.putpixel((0, yy), int(180 * (yy - image.size[1] * 0.5) / (image.size[1] * 0.5)))
    gradient = gradient.resize(image.size)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 255))
    shadow.putalpha(gradient)
    overlay = Image.alpha_composite(overlay, shadow)
    draw = ImageDraw.Draw(overlay)

    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (image.size[0] - w) / 2
        for dx, dy in [(-3, -3), (3, -3), (-3, 3), (3, 3), (0, 0)]:
            color = (0, 0, 0, 255) if (dx, dy) != (0, 0) else (255, 215, 0, 255)
            draw.text((x + dx, y + dy), line, font=font, fill=color)
        y += line_height

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def generate_thumbnail(topic: str, title: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bg_path = out_dir / "thumbnail_bg.png"
    _generate_background(topic, bg_path)

    image = Image.open(bg_path)
    final = _draw_title_text(image, title)
    out_path = out_dir / "thumbnail.jpg"
    final.save(out_path, quality=92)
    return out_path
