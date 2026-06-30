import json
from datetime import datetime
from pathlib import Path

from pipeline.config import OUTPUT_DIR
from pipeline.script_gen import generate_script
from pipeline.image_gen import generate_images_for_scenes
from pipeline.tts import synthesize_scenes
from pipeline.video import build_shorts_video
from pipeline.trends import get_trending_topic


def run_pipeline(topic: str | None = None, upload: bool = False, privacy_status: str = "public") -> dict:
    """Generates and (optionally) uploads a single ~1-minute vertical Shorts
    clip for the run. Long-form main-video generation has been retired:
    only the Shorts pipeline runs now."""
    context: list[str] = []
    if topic is None:
        trend = get_trending_topic()
        topic = trend["topic"]
        context = trend["context"]

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[1/5] Topic: {topic}")
    if context:
        print(f"[1/5] Context: {context}")

    print("[2/5] Generating script...")
    script = generate_script(topic, context)
    (run_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2))
    scenes = script["scenes"]

    print(f"[3/5] Generating {len(scenes)} scene images...")
    images = generate_images_for_scenes(scenes, run_dir / "images")

    print("[4/5] Synthesizing narration audio with timestamps...")
    scenes_with_audio = synthesize_scenes(scenes, run_dir / "audio")

    print("[5/5] Assembling vertical Shorts clip (picture changes every sentence)...")
    shorts_video, shorts_seconds = build_shorts_video(scenes_with_audio, images, run_dir / "shorts")

    result = {
        "topic": topic,
        "run_dir": str(run_dir),
        "shorts_video_path": str(shorts_video),
        "title": script["title"],
        "description": script["description"],
        "tags": script["tags"],
        "shorts_duration_seconds": shorts_seconds,
    }
    (run_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Done. Shorts: {shorts_video} ({shorts_seconds:.1f}s)")

    if upload:
        from pipeline.youtube_upload import upload_video

        print("Uploading Shorts clip to YouTube...")
        shorts_title = f"{script['title'][:50]} #Shorts"
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
