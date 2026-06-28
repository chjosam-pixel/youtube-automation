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


def _generate_background(topic: str, scene_briefs: list[str], out_path: Path) -> Path:
    """Build the thumbnail prompt around the actual scene content, not the bare
    (often ambiguous) trending keyword, so the thumbnail visibly matches what the
    video is really about (e.g. the specific match/event/people involved)."""
    content_brief = " ".join(scene_briefs[:2]) if scene_briefs else topic
    prompt = (
        f"A hard-hitting, highly provocative breaking-news YouTube thumbnail photo. "
        f"It must clearly and unmistakably depict this exact specific subject, instantly recognizable at a glance: "
        f"{content_brief} "
        f"General topic for reference only: {topic}. "
        "Photorealistic, shot on a professional DSLR camera, real photojournalism quality, realistic lighting "
        "and textures, not an illustration, not a painting, not cartoon, not 3D render. "
        "Viral high-stakes news-channel thumbnail style: extreme dramatic close-up framing, intense facial "
        "expressions or high-tension action, bold vibrant high-saturation colors, punchy high contrast, "
        "bright clean high-key lighting, sharp focus, highly detailed, professional broadcast-network polish, "
        "credible and authoritative news-studio production value, no text, no watermark, no dark or muddy "
        "tones, 16:9 widescreen composition."
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

    font_size = 130
    font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)

    wrapped = textwrap.wrap(title, width=14)
    while len(wrapped) > 3 and font_size > 80:
        font_size -= 4
        font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)
        wrapped = textwrap.wrap(title, width=14)

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

    outline_width = 8
    outline_offsets = [
        (dx, dy)
        for dx in range(-outline_width, outline_width + 1, 2)
        for dy in range(-outline_width, outline_width + 1, 2)
        if dx != 0 or dy != 0
    ]
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (image.size[0] - w) / 2
        for dx, dy in outline_offsets:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), line, font=font, fill=(255, 215, 0, 255))
        y += line_height

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def generate_thumbnail(topic: str, title: str, out_dir: Path, scene_briefs: list[str] | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bg_path = out_dir / "thumbnail_bg.png"
    _generate_background(topic, scene_briefs or [], bg_path)

    image = Image.open(bg_path)
    final = _draw_title_text(image, title)
    out_path = out_dir / "thumbnail.jpg"
    final.save(out_path, quality=92)
    return out_path
