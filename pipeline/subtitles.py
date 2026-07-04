from pathlib import Path

MAX_LINE_CHARS = 42
BREAK_CHARS = set("。！？，；：、.!?,;:؟،؛")
SHORTS_MAX_LINE_CHARS = 26
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


def _words_from_alignment(alignment: dict):
    """Group an alignment's per-character timestamps into per-word
    (word, start, end) tuples, splitting on spaces."""
    characters = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words = []
    chars = []
    word_start = None
    word_end = None
    for ch, st, en in zip(characters, starts, ends):
        if ch == " ":
            if chars:
                words.append(("".join(chars), word_start, word_end))
                chars = []
                word_start = None
            continue
        if word_start is None:
            word_start = st
        chars.append(ch)
        word_end = en
    if chars:
        words.append(("".join(chars), word_start, word_end))
    return words


def _scene_sentence_word_groups(alignment: dict):
    """Yields one list of (word, start, end) tuples per sentence (split at
    SENTENCE_END_CHARS), so callers can build word-level (typewriter-style)
    captions while still knowing the sentence's overall start/end for
    audio/image clip timing."""
    words = _words_from_alignment(alignment)
    group = []
    for word, st, en in words:
        group.append((word, st, en))
        if word and word[-1] in SENTENCE_END_CHARS:
            yield group
            group = []
    if group:
        yield group


def build_typewriter_srt(
    sentence_word_groups: list[list[tuple[str, float, float]]],
    out_path: Path,
    max_words_visible: int = 4,
    max_line_chars: int = SHORTS_MAX_LINE_CHARS,
) -> Path:
    """Build an SRT where caption text grows/slides one word at a time as
    it's spoken (a sliding window of the last `max_words_visible` words),
    instead of showing a whole sentence at once. The window keeps each
    entry short so it always fits the wrapped/margined caption box."""
    lines = []
    idx = 1
    for group in sentence_word_groups:
        n = len(group)
        for i, (_, st, en) in enumerate(group):
            window = group[max(0, i - max_words_visible + 1): i + 1]
            text = " ".join(w for w, _, _ in window)
            entry_end = group[i + 1][1] if i + 1 < n else en
            if entry_end <= st:
                entry_end = st + 0.15
            display_text = _wrap_for_display(text, max_line_chars)
            lines.append(str(idx))
            lines.append(f"{format_srt_time(st)} --> {format_srt_time(entry_end)}")
            lines.append(display_text)
            lines.append("")
            idx += 1
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
