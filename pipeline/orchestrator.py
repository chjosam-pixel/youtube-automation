import json
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR
from pipeline.script_gen import generate_script
from pipeline.image_gen import generate_images_for_scenes
from pipeline.tts import synthesize_scenes
from pipeline.video import build_shorts_video, build_scene_clips, concat_clips, burn_subtitles
from pipeline.trends import get_trending_topic
from pipeline.subtitles import build_srt_for_scenes
from pipeline.thumbnail import generate_thumbnail, generate_shorts_thumbnail


def run_pipeline(topic: str | None = None, upload: bool = False, privacy_status: str = "public") -> dict:
    """Generates and (optionally) uploads a single ~1-minute vertical Shorts
    clip for the run. Long-form main-video generation has been retired:
    only the Shorts pipeline runs now."""
    context: list[str] = []
    category: str | None = None
    if topic is None:
        trend = get_trending_topic()
        topic = trend["topic"]
        context = trend["context"]
        category = trend.get("category")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[1/5] Topic: {topic}")
    if context:
        print(f"[1/5] Context: {context}")

    print("[2/5] Generating script...")
    script = generate_script(topic, context, category=category)
    (run_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))
    scenes = script["scenes"]

    print(f"[3/5] Generating {len(scenes)} scene images...")
    images = generate_images_for_scenes(scenes, run_dir / "images")

    print("[4/5] Synthesizing narration audio with timestamps...")
    scenes_with_audio = synthesize_scenes(scenes, run_dir / "audio")

    print("[5/6] Assembling vertical Shorts clip (picture changes every sentence)...")
    shorts_video, shorts_seconds = build_shorts_video(scenes_with_audio, images, run_dir / "shorts")

    print("[6/6] Assembling horizontal main video...")
    main_dir = run_dir / "main"
    main_dir.mkdir(parents=True, exist_ok=True)
    clip_paths, scene_durations = build_scene_clips(scenes_with_audio, images, main_dir / "clips")
    raw_main = concat_clips(clip_paths, main_dir / "main_raw.mp4")
    scene_offsets = []
    offset = 0.0
    for d in scene_durations:
        scene_offsets.append(offset)
        offset += d
    srt_path = build_srt_for_scenes(scenes_with_audio, scene_offsets, main_dir / "main_subtitles.srt")
    main_video = burn_subtitles(raw_main, srt_path, main_dir / "main_final.mp4")

    result = {
        "topic": topic,
        "run_dir": str(run_dir),
        "shorts_video_path": str(shorts_video),
        "main_video_path": str(main_video),
        "title": script["title"],
        "description": script["description"],
        "tags": script["tags"],
        "shorts_duration_seconds": shorts_seconds,
        "main_duration_seconds": offset,
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print("Generating thumbnails...")
    scene_briefs = [s.get("image_prompt", "") for s in scenes[:2]]
    thumbnail_path = generate_thumbnail(topic, script["title"], run_dir / "thumbnail", scene_briefs)
    shorts_thumbnail_path = generate_shorts_thumbnail(topic, script["title"], run_dir / "thumbnail", scene_briefs)

    print(f"Done. Shorts: {shorts_video} ({shorts_seconds:.1f}s) | Main: {main_video} ({offset:.1f}s)")

    if upload:
        from pipeline.youtube_upload import upload_video

        # Upload main video first so its URL can be embedded in the Shorts description
        print("Uploading main video to YouTube...")
        main_video_id = upload_video(
            video_path=main_video,
            title=script["title"][:100],
            description=script["description"],
            tags=list(script["tags"]),
            thumbnail_path=thumbnail_path,
            privacy_status=privacy_status,
        )
        result["youtube_main_video_id"] = main_video_id
        result["youtube_main_url"] = f"https://www.youtube.com/watch?v={main_video_id}"
        print(f"Uploaded Main: {result['youtube_main_url']}")

        print("Uploading Shorts clip to YouTube...")
        shorts_title = f"{script['title'][:50]} #Shorts"
        main_url = result["youtube_main_url"]
        shorts_description = (
            f"{script['description']}\n\n"
            f"▶ 전체 영상 보기: {main_url}\n\n"
            f"#Shorts"
        )
        shorts_tags = list(script["tags"])
        if "Shorts" not in shorts_tags:
            shorts_tags.append("Shorts")
        shorts_video_id = upload_video(
            video_path=shorts_video,
            title=shorts_title,
            description=shorts_description,
            tags=shorts_tags,
            thumbnail_path=shorts_thumbnail_path,
            privacy_status=privacy_status,
        )
        result["youtube_shorts_video_id"] = shorts_video_id
        result["youtube_shorts_url"] = f"https://www.youtube.com/shorts/{shorts_video_id}"
        print(f"Uploaded Shorts: {result['youtube_shorts_url']}")

        (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))

    return result
