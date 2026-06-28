import subprocess
from pathlib import Path

from pipeline.config import (
    VIDEO_WIDTH,
    VIDEO_HEIGHT,
    VIDEO_FPS,
    SHORTS_WIDTH,
    SHORTS_HEIGHT,
    SHORTS_MAX_SECONDS,
)


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


def select_shorts_scenes(scenes_with_audio: list[dict], durations: list[float]) -> int:
    """Return how many leading scenes fit within SHORTS_MAX_SECONDS (at least 1)."""
    cumulative = 0.0
    count = 0
    for d in durations:
        if count > 0 and cumulative + d > SHORTS_MAX_SECONDS:
            break
        cumulative += d
        count += 1
    return max(count, 1)


def build_shorts_clips(scenes_with_audio: list[dict], images: list[Path], out_dir: Path) -> tuple[list[Path], list[float]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_paths = []
    durations = []
    for i, (scene, image_path) in enumerate(zip(scenes_with_audio, images)):
        duration = ffprobe_duration(scene["audio_path"])
        out_path = out_dir / f"short_{i:02d}.mp4"
        build_shorts_clip(image_path, scene["audio_path"], duration, motion=i % 4, out_path=out_path)
        clip_paths.append(out_path)
        durations.append(duration)
    return clip_paths, durations


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


def burn_subtitles(in_video: Path, srt_path: Path, out_video: Path) -> Path:
    style = (
        "FontName=Amiri,FontSize=96,Bold=1,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=5,Shadow=2,"
        "MarginV=40,MarginL=40,MarginR=40,Alignment=2"
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
