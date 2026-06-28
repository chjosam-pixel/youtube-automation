import argparse

from pipeline.orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Daily trending-topic YouTube documentary pipeline (Arabic narration)")
    parser.add_argument("--topic", default=None, help="Override topic instead of auto-picking one")
    parser.add_argument(
        "--privacy", default="public", choices=["public", "unlisted", "private"],
        help="YouTube privacy status for the uploaded video",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Generate the video only, without uploading to YouTube",
    )
    args = parser.parse_args()

    result = run_pipeline(topic=args.topic, upload=not args.no_upload, privacy_status=args.privacy)
    print(result)


if __name__ == "__main__":
    main()
