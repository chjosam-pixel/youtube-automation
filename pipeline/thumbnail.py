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


def _draw_title_text(image: Image.Image, title: str, size: tuple[int, int] | None = None) -> Image.Image:
    """Overlay bold Arabic title text on image.

    Strategy: chunk the title into 1-2 words per line, then find the largest
    font size where every line still fits within the safe horizontal margin.
    This guarantees no clipping regardless of word length.
    """
    target_size = size or THUMB_SIZE
    image = image.convert("RGB").resize(target_size)
    w_img, h_img = target_size
    margin_x = int(w_img * 0.07)
    max_text_width = w_img - margin_x * 2

    # Reshape the full title for PIL rendering (PIL doesn't do Arabic shaping)
    reshaped_title = _to_display_text(title)

    # Split into 1-2 word chunks for large legible lines
    words = reshaped_title.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + 2]))
        i += 2

    # Find the largest font size where every chunk fits within max_text_width
    dummy = Image.new("RGB", (1, 1))
    draw_dummy = ImageDraw.Draw(dummy)
    font_size = 160  # start large
    font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)
    while font_size > 50:
        font = ImageFont.truetype(ARABIC_FONT_PATH, font_size)
        widths = [draw_dummy.textbbox((0, 0), c, font=font)[2] for c in chunks]
        if max(widths) <= max_text_width:
            break
        font_size -= 6

    line_height = font_size + int(font_size * 0.18)
    total_text_h = line_height * len(chunks)
    safe_bottom_margin = int(h_img * 0.05)

    # Dark gradient covering the bottom portion behind text
    overlay = Image.new("RGBA", target_size, (0, 0, 0, 0))
    gradient = Image.new("L", (1, h_img), color=0)
    grad_start = h_img - total_text_h - safe_bottom_margin - int(h_img * 0.08)
    for yy in range(h_img):
        if yy >= grad_start:
            alpha = int(210 * min(1.0, (yy - grad_start) / max(1, h_img - grad_start)))
            gradient.putpixel((0, yy), alpha)
    gradient = gradient.resize(target_size)
    shadow_layer = Image.new("RGBA", target_size, (0, 0, 0, 255))
    shadow_layer.putalpha(gradient)
    overlay = Image.alpha_composite(overlay, shadow_layer)

    draw = ImageDraw.Draw(overlay)
    y = h_img - total_text_h - safe_bottom_margin

    outline_w = max(4, font_size // 18)
    offsets = [
        (dx, dy)
        for dx in range(-outline_w, outline_w + 1, 2)
        for dy in range(-outline_w, outline_w + 1, 2)
        if dx != 0 or dy != 0
    ]
    for chunk in chunks:
        bbox = draw.textbbox((0, 0), chunk, font=font)
        lw = bbox[2] - bbox[0]
        x = (w_img - lw) / 2
        for dx, dy in offsets:
            draw.text((x + dx, y + dy), chunk, font=font, fill=(0, 0, 0, 255))
        draw.text((x, y), chunk, font=font, fill=(255, 215, 0, 255))
        y += line_height

    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _wrap_to_fit(text: str, font: ImageFont.FreeTypeFont, max_width: int, font_size: int) -> list[str]:
    """Word-wrap pre-reshaped Arabic text so each line fits within max_width pixels."""
    dummy_img = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy_img)

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def generate_thumbnail(topic: str, title: str, out_dir: Path, scene_briefs: list[str] | None = None) -> Path:
    """Main video thumbnail — clean photorealistic image, no text."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bg_path = out_dir / "thumbnail_bg.png"
    _generate_background(topic, scene_briefs or [], bg_path)
    image = Image.open(bg_path).convert("RGB").resize(THUMB_SIZE)
    out_path = out_dir / "thumbnail.jpg"
    image.save(out_path, quality=92)
    return out_path


def generate_shorts_thumbnail(topic: str, title: str, out_dir: Path, scene_briefs: list[str] | None = None) -> Path:
    """Shorts thumbnail — same background with large bold Arabic title text overlay."""
    out_dir.mkdir(parents=True, exist_ok=True)
    bg_path = out_dir / "shorts_thumbnail_bg.png"
    _generate_background(topic, scene_briefs or [], bg_path)
    image = Image.open(bg_path)
    image_with_text = _draw_title_text(image, title)
    out_path = out_dir / "shorts_thumbnail.jpg"
    image_with_text.save(out_path, quality=92)
    return out_path
