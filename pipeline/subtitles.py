from pathlib import Path

MAX_LINE_CHARS = 42
BREAK_CHARS = set("。！？，；：、.!?,;:؟،؛")
SHORTS_MAX_LINE_CHARS = 22


def _format_srt_time(t: float) -> str:
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
        lines.append(f"{_format_srt_time(st)} --> {_format_srt_time(en)}")
        lines.append(text)
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
