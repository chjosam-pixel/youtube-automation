import base64
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from openai import OpenAI

from pipeline.config import OPENAI_API_KEY, IMAGE_MODEL
from pipeline.image_gen import _generate_with_retry

client = OpenAI(api_key=OPENAI_API_KEY)

THUMB_SIZE = (1280, 720)
ARABIC_FONT_NAME = "Amiri Bold"


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


def _render_arabic_text_pango(title: str, target_size: tuple[int, int]) -> Image.Image:
    """Render Arabic title text using ImageMagick Pango for properly connected RTL script.

    Splits into 1-2 words per line, finds the largest font size where all lines
    fit within the safe horizontal margin, then composites on a dark gradient.
    """
    w_img, h_img = target_size
    margin_x = int(w_img * 0.06)
    max_text_w = w_img - margin_x * 2

    words = title.split()

    def make_chunks(wds: list[str], per_line: int) -> list[str]:
        return [" ".join(wds[i:i + per_line]) for i in range(0, len(wds), per_line)]

    def pango_text_width(lines: list[str], font_size: int) -> int:
        """Measure rendered pixel width using ImageMagick Pango in a temp file."""
        markup = "\n".join(
            f'<span font="{ARABIC_FONT_NAME} {font_size}" color="white">{ln}</span>'
            for ln in lines
        )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        try:
            subprocess.run(
                ["convert", "-size", f"{w_img}x{h_img}", "-background", "transparent",
                 f"pango:{markup}", tmp],
                capture_output=True, check=True,
            )
            img = Image.open(tmp)
            return img.size[0]
        finally:
            Path(tmp).unlink(missing_ok=True)

    # Find largest font size where lines fit, trying 1 word/line then 2
    chosen_chunks: list[str] = []
    chosen_font_size = 60
    for per_line in [1, 2]:
        for font_size in range(220, 55, -8):
            cands = make_chunks(words, per_line)
            # Estimate width: use ImageMagick to measure the longest line
            longest = max(cands, key=len)
            markup = f'<span font="{ARABIC_FONT_NAME} {font_size}" foreground="white">{longest}</span>'
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                tmp = f.name
            try:
                result = subprocess.run(
                    ["convert", "-background", "transparent", f"pango:{markup}", tmp],
                    capture_output=True,
                )
                if result.returncode != 0:
                    continue
                w = Image.open(tmp).size[0]
            finally:
                Path(tmp).unlink(missing_ok=True)

            if w <= max_text_w:
                chosen_chunks = cands
                chosen_font_size = font_size
                break
        if chosen_chunks:
            break

    if not chosen_chunks:
        chosen_chunks = make_chunks(words, 2)
        chosen_font_size = 60

    # Build full Pango markup (one span per line, newline-separated)
    markup_lines = "\n".join(
        f'<span font="{ARABIC_FONT_NAME} {chosen_font_size}" foreground="gold">{ln}</span>'
        for ln in chosen_chunks
    )

    # Render text at natural size (no -size constraint to avoid canvas overflow errors)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        text_tmp = f.name
    try:
        subprocess.run(
            ["convert", "-background", "transparent", f"pango:{markup_lines}", text_tmp],
            capture_output=True, check=True,
        )
        text_img = Image.open(text_tmp).convert("RGBA")
    finally:
        Path(text_tmp).unlink(missing_ok=True)

    # Composite text onto a full-canvas transparent layer, gravity=South with margin
    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    tw, th = text_img.size
    # Clamp to canvas width just in case
    if tw > w_img:
        scale = w_img / tw
        text_img = text_img.resize((w_img, int(th * scale)), Image.LANCZOS)
        tw, th = text_img.size
    bottom_margin = int(h_img * 0.05)
    paste_x = (w_img - tw) // 2
    paste_y = h_img - th - bottom_margin
    canvas.paste(text_img, (paste_x, max(0, paste_y)))
    return canvas


def _draw_title_text(image: Image.Image, title: str, size: tuple[int, int] | None = None) -> Image.Image:
    """Overlay bold Arabic title text on image using ImageMagick Pango for correct RTL rendering."""
    target_size = size or THUMB_SIZE
    image = image.convert("RGBA").resize(target_size)
    w_img, h_img = target_size

    # Dark gradient at the bottom behind text
    gradient_layer = Image.new("RGBA", target_size, (0, 0, 0, 0))
    grad_height = int(h_img * 0.55)
    grad_start = h_img - grad_height
    pixels = gradient_layer.load()
    for yy in range(grad_start, h_img):
        alpha = int(200 * min(1.0, (yy - grad_start) / max(1, grad_height)))
        for xx in range(w_img):
            pixels[xx, yy] = (0, 0, 0, alpha)

    base = Image.alpha_composite(image, gradient_layer)

    # Render Arabic text via ImageMagick Pango
    text_layer = _render_arabic_text_pango(title, target_size)

    result = Image.alpha_composite(base, text_layer)
    return result.convert("RGB")



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
