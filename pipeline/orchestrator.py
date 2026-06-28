import json
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR
from pipeline.script_gen import generate_script
from pipeline.image_gen import generate_images_for_scenes
from pipeline.tts import synthesize_scenes
from pipeline.subtitles import build_srt_for_scenes
from pipeline.video import (
    build_scene_clips,
    concat_clips,
    burn_subtitles,
    select_shorts_scenes,
    build_shorts_clips,
)
from pipeline.thumbnail import generate_thumbnail
from pipeline.trends import get_trending_topic


def run_pipeline(topic: str | None = None, upload: bool = False, privacy_status: str = "public") -> dict:
    context: list[str] = []
    if topic is None:
        trend = get_trending_topic()
        topic = trend["topic"]
        context = trend["context"]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[1/7] Topic: {topic}")
    if context:
        print(f"[1/7] Context: {context}")

    print("[2/7] Generating script...")
    script = generate_script(topic, context)
    (run_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))
    scenes = script["scenes"]

    print(f"[3/7] Generating {len(scenes)} scene images...")
    images = generate_images_for_scenes(scenes, run_dir / "images")

    print("[4/7] Synthesizing narration audio with timestamps...")
    scenes_with_audio = synthesize_scenes(scenes, run_dir / "audio")

    print("[5/7] Assembling Ken Burns video clips...")
    clip_paths, durations = build_scene_clips(scenes_with_audio, images, run_dir / "clips")

    scene_offsets = []
    cumulative = 0.0
    for d in durations:
        scene_offsets.append(cumulative)
        cumulative += d

    print("[6/7] Building subtitles and concatenating video...")
    srt_path = build_srt_for_scenes(scenes_with_audio, scene_offsets, run_dir / "subtitles.srt")
    raw_video = concat_clips(clip_paths, run_dir / "raw.mp4")
    final_video = burn_subtitles(raw_video, srt_path, run_dir / "final.mp4")

    print("[7/8] Generating thumbnail...")
    thumbnail_path = generate_thumbnail(topic, script["title"], run_dir)

    print("[8/8] Assembling vertical Shorts clip...")
    shorts_count = select_shorts_scenes(scenes_with_audio, durations)
    shorts_clip_paths, shorts_durations = build_shorts_clips(
        scenes_with_audio[:shorts_count], images[:shorts_count], run_dir / "shorts_clips"
    )
    shorts_offsets = []
    shorts_cumulative = 0.0
    for d in shorts_durations:
        shorts_offsets.append(shorts_cumulative)
        shorts_cumulative += d
    shorts_srt_path = build_srt_for_scenes(
        scenes_with_audio[:shorts_count], shorts_offsets, run_dir / "shorts_subtitles.srt"
    )
    shorts_raw = concat_clips(shorts_clip_paths, run_dir / "shorts_raw.mp4")
    shorts_video = burn_subtitles(shorts_raw, shorts_srt_path, run_dir / "shorts_final.mp4")

    result = {
        "topic": topic,
        "run_dir": str(run_dir),
        "video_path": str(final_video),
        "shorts_video_path": str(shorts_video),
        "thumbnail_path": str(thumbnail_path),
        "title": script["title"],
        "description": script["description"],
        "tags": script["tags"],
        "total_duration_seconds": cumulative,
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Done. Video: {final_video} ({cumulative/60:.1f} min)")

    if upload:
        from pipeline.youtube_upload import upload_video

        print("Uploading main video to YouTube...")
        video_id = upload_video(
            video_path=final_video,
            title=script["title"],
            description=script["description"],
            tags=script["tags"],
            thumbnail_path=thumbnail_path,
            privacy_status=privacy_status,
        )
        result["youtube_video_id"] = video_id
        result["youtube_url"] = f"https://www.youtube.com/watch?v={video_id}"
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Uploaded: {result['youtube_url']}")

        print("Uploading Shorts clip to YouTube...")
        shorts_title = f"{script['title'][:90]} #Shorts"
        shorts_description = f"{script['description']}\n\n#Shorts"
        shorts_tags = list(script["tags"])
        if "Shorts" not in shorts_tags:
            shorts_tags.append("Shorts")
        shorts_video_id = upload_video(
            video_path=shorts_video,
            title=shorts_title,
            description=shorts_description,
            tags=shorts_tags,
            thumbnail_path=None,
            privacy_status=privacy_status,
        )
        result["youtube_shorts_video_id"] = shorts_video_id
        result["youtube_shorts_url"] = f"https://www.youtube.com/shorts/{shorts_video_id}"
        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"Uploaded Shorts: {result['youtube_shorts_url']}")

    return result
