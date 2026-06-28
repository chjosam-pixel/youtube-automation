import json
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR
from pipeline.script_gen import generate_script
from pipeline.image_gen import generate_images_for_scenes
from pipeline.tts import synthesize_scenes
from pipeline.subtitles import build_srt_for_scenes
from pipeline.video import build_scene_clips, concat_clips, burn_subtitles
from pipeline.thumbnail import generate_thumbnail
from pipeline.trends import get_trending_topic


def run_pipeline(topic: str | None = None, upload: bool = False, privacy_status: str = "public") -> dict:
    if topic is None:
        topic = get_trending_topic()

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[1/7] Topic: {topic}")

    print("[2/7] Generating script...")
    script = generate_script(topic)
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

    print("[7/7] Generating thumbnail...")
    thumbnail_path = generate_thumbnail(topic, script["title"], run_dir)

    result = {
        "topic": topic,
        "run_dir": str(run_dir),
        "video_path": str(final_video),
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

        print("Uploading to YouTube...")
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

    return result
