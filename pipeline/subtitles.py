from pathlib import Path

MAX_LINE_CHARS = 42
BREAK_CHARS = set("。！？，；：、.!?,;:؟،؛")
SHORTS_MAX_LINE_CHARS = 22
SENTENCE_END_CHARS = set("。！？.!?؟")


def format_srt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _chunk_characters(characters: list[str], starts: list[float], ends: list[float], max_line_chars: int = MAX_LINE_CHARS):
    """Yields (text, start, end) chunks split on punctuation / max length."""
    chunk_chars = []
    chunk_start = None
    for ch, st, en in zip(characters, starts, ends):
        if chunk_start is None:
            chunk_start = st
        chunk_chars.append(ch)
        is_break = ch in BREAK_CHARS
        too_long = len("".join(chunk_chars).strip()) >= max_line_chars
        if is_break or too_long:
            text = "".join(chunk_chars).strip()
            if text:
                yield text, chunk_start, en
            chunk_chars = []
            chunk_start = None
    if chunk_chars:
        text = "".join(chunk_chars).strip()
        if text:
            yield text, chunk_start, ends[-1]


def build_srt_for_scenes(
    scenes_with_alignment: list[dict],
    scene_offsets: list[float],
    out_path: Path,
    max_line_chars: int = MAX_LINE_CHARS,
) -> Path:
    """scenes_with_alignment: list of dicts with 'alignment' (characters/start/end seconds, scene-relative).
    scene_offsets: cumulative start time (seconds) of each scene within the final concatenated video.
    """
    entries = []
    for scene, offset in zip(scenes_with_alignment, scene_offsets):
        alignment = scene["alignment"]
        characters = alignment["characters"]
        starts = alignment["character_start_times_seconds"]
        ends = alignment["character_end_times_seconds"]
        for text, st, en in _chunk_characters(characters, starts, ends, max_line_chars):
            entries.append((text, st + offset, en + offset))

    lines = []
    for idx, (text, st, en) in enumerate(entries, start=1):
        if en <= st:
            en = st + 0.8
        lines.append(str(idx))
        lines.append(f"{format_srt_time(st)} --> {format_srt_time(en)}")
        lines.append(text)
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def _scene_sentences(alignment: dict):
    """Yields (text, start, end) split only at full sentence-ending punctuation.

    Unlike _chunk_characters, this never cuts mid-word: a sentence is always
    handed to the subtitle renderer whole, so words never lose their Arabic
    joining context and render as broken/disconnected glyph fragments.
    """
    characters = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    chunk_chars = []
    chunk_start = None
    for ch, st, en in zip(characters, starts, ends):
        if chunk_start is None:
            chunk_start = st
        chunk_chars.append(ch)
        if ch in SENTENCE_END_CHARS:
            text = "".join(chunk_chars).strip()
            if text:
                yield text, chunk_start, en
            chunk_chars = []
            chunk_start = None
    if chunk_chars:
        text = "".join(chunk_chars).strip()
        if text:
            yield text, chunk_start, ends[-1]


def _wrap_for_display(text: str, max_line_chars: int) -> str:
    """Insert forced ASS line breaks (\\N) so no rendered line exceeds
    max_line_chars, instead of relying on libass to auto-wrap a whole
    sentence at a width it may not fit, which can push text past the
    frame edges on a narrow vertical (Shorts) frame."""
    words = text.split(" ")
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_line_chars:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\\N".join(lines)


def build_srt_from_entries(
    entries: list[tuple[str, float, float]], out_path: Path, max_line_chars: int | None = None
) -> Path:
    """entries: list of (text, absolute_start_seconds, absolute_end_seconds), already final."""
    lines = []
    for idx, (text, st, en) in enumerate(entries, start=1):
        if en <= st:
            en = st + 0.8
        display_text = _wrap_for_display(text, max_line_chars) if max_line_chars else text
        lines.append(str(idx))
        lines.append(f"{format_srt_time(st)} --> {format_srt_time(en)}")
        lines.append(display_text)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
