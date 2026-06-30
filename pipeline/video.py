import subprocess
from pathlib import Path

from pipeline.config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    SHORTS_WIDTH,
    SHORTS_HEIGHT,
    SHORTS_MIN_SECONDS,
    SHORTS_MAX_SECONDS,
)
from pipeline.subtitles import _scene_sentence_word_groups, build_srt_from_entries, SHORTS_MAX_LINE_CHARS


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _ken_burns_filter(motion: int, total_frames: int) -> str:
    zoom_rate = 0.0009
    max_zoom = 1.18
    if motion == 0:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == 1:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = f"(iw-iw/zoom)*(on/{total_frames})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == 2:
        z = f"if(eq(on,0),{max_zoom},max(zoom-{zoom_rate},1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y = "ih/2-(ih/zoom/2)"
    return (
        f"scale=3840:2160,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS},"
        f"eq=brightness=0.06:saturation=1.35:contrast=1.12,"
        f"format=yuv420p"
    )


def _shorts_ken_burns_filter(motion: int, total_frames: int) -> str:
    """Same Ken Burns motion as the main video, but cropped to a 9:16 vertical frame."""
    zoom_rate = 0.0009
    max_zoom = 1.18
    if motion == 0:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == 1:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = f"(iw-iw/zoom)*(on/{total_frames})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == 2:
        z = f"if(eq(on,0),{max_zoom},max(zoom-{zoom_rate},1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = f"min(zoom+{zoom_rate},{max_zoom})"
        x = f"(iw-iw/zoom)*(1-on/{total_frames})"
        y = "ih/2-(ih/zoom/2)"
    crop_width = round(2160 * SHORTS_WIDTH / SHORTS_HEIGHT)
    return (
        f"scale=-2:2160,crop={crop_width}:2160,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={SHORTS_WIDTH}x{SHORTS_HEIGHT}:fps={VIDEO_FPS},"
        f"eq=brightness=0.06:saturation=1.35:contrast=1.12,"
        f"format=yuv420p"
    )


def build_shorts_clip(image_path: Path, audio_path: Path, duration: float, motion: int, out_path: Path) -> Path:
    total_frames = max(int(round(duration * VIDEO_FPS)), 1)
    vf = _shorts_ken_burns_filter(motion, total_frames)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def _extract_audio_segment(in_audio: Path, start: float, end: float, out_path: Path) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(in_audio),
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-c:a", "aac", "-b:a", "192k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def build_shorts_video(
    scenes_with_audio: list[dict],
    images: list[Path],
    out_dir: Path,
    min_seconds: float = SHORTS_MIN_SECONDS,
    max_seconds: float = SHORTS_MAX_SECONDS,
) -> tuple[Path, float]:
    """Assemble a vertical Shorts video that changes picture at every sentence
    boundary (cycling through the scene images) instead of holding on one
    image for an entire multi-sentence scene, and stops once the runtime
    lands within [min_seconds, max_seconds]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []
    sentence_word_groups: list[list[tuple[str, float, float]]] = []
    cumulative = 0.0
    sentence_count = 0

    for scene in scenes_with_audio:
        for group in _scene_sentence_word_groups(scene["alignment"]):
            start = group[0][1]
            end = group[-1][2]
            duration = end - start
            if duration <= 0.05:
                continue
            if sentence_count > 0 and cumulative >= min_seconds and cumulative + duration > max_seconds:
                break

            seg_audio = out_dir / f"seg_{sentence_count:03d}.m4a"
            _extract_audio_segment(scene["audio_path"], start, end, seg_audio)

            image_path = images[sentence_count % len(images)]
            clip_path = out_dir / f"short_{sentence_count:03d}.mp4"
            build_shorts_clip(image_path, seg_audio, duration, motion=sentence_count % 4, out_path=clip_path)

            clip_paths.append(clip_path)
            # Shift this sentence's word timestamps from scene-relative time
            # to the cumulative time of the concatenated Shorts video.
            abs_group = [(w, cumulative + (wst - start), cumulative + (wen - start)) for w, wst, wen in group]
            sentence_word_groups.append(abs_group)
            cumulative += duration
            sentence_count += 1

            if cumulative >= max_seconds:
                break
        if cumulative >= max_seconds:
            break

    raw_video = concat_clips(clip_paths, out_dir / "shorts_raw.mp4")
    # Whole sentence per caption (changes only when the narrator pauses at a
    # sentence boundary), not per-word: word-by-word reveal was too fast/
    # frantic to read comfortably.
    sentence_entries = [
        (" ".join(w for w, _, _ in group), group[0][1], group[-1][2]) for group in sentence_word_groups
    ]
    srt_path = build_srt_from_entries(
        sentence_entries, out_dir / "shorts_subtitles.srt", max_line_chars=SHORTS_MAX_LINE_CHARS
    )
    final_video = burn_subtitles(
        raw_video, srt_path, out_dir / "shorts_final.mp4", width=SHORTS_WIDTH, height=SHORTS_HEIGHT
    )
    return final_video, cumulative


def build_scene_clip(image_path: Path, audio_path: Path, duration: float, motion: int, out_path: Path) -> Path:
    total_frames = max(int(round(duration * VIDEO_FPS)), 1)
    vf = _ken_burns_filter(motion, total_frames)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def build_scene_clips(scenes_with_audio: list[dict], images: list[Path], out_dir: Path) -> tuple[list[Path], list[float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    durations = []
    for i, (scene, image_path) in enumerate(zip(scenes_with_audio, images)):
        duration = ffprobe_duration(scene["audio_path"])
        out_path = out_dir / f"clip_{i:02d}.mp4"
        build_scene_clip(image_path, scene["audio_path"], duration, motion=i % 4, out_path=out_path)
        clip_paths.append(out_path)
        durations.append(duration)
    return clip_paths, durations


def concat_clips(clip_paths: list[Path], out_path: Path) -> Path:
    list_file = out_path.parent / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_path


def burn_subtitles(
    in_video: Path,
    srt_path: Path,
    out_video: Path,
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
) -> Path:
    """Burn subtitles sized so the text block stays within roughly the bottom
    1/5 of the frame, instead of a fixed huge font that can swallow most of a
    narrow vertical (Shorts) frame."""
    # Base font size on the narrower of the two dimensions: for a portrait
    # Shorts frame (1080x1920), the 1080px width is what actually bounds line
    # length, so sizing off the much taller height (as before) produced text
    # too wide to fit and overflowing past the frame edges.
    font_size = max(30, round(min(width, height) * 0.034))
    outline = max(3, round(font_size * 0.06))
    shadow = max(1, round(font_size * 0.02))
    margin_v = round(height * 0.06)
    margin_lr = round(width * 0.08)
    style = (
        f"FontName=Amiri,FontSize={font_size},Bold=1,PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline={outline},Shadow={shadow},"
        f"MarginV={margin_v},MarginL={margin_lr},MarginR={margin_lr},Alignment=2"
    )
    vf = f"subtitles={srt_path}:force_style='{style}'"
    cmd = [
        "ffmpeg", "-y", "-i", str(in_video),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "copy",
        str(out_video),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return out_video
