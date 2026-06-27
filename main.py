import argparse

from pipeline.orchestrator import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Korean history YouTube documentary pipeline")
    parser.add_argument(
        "mode", choices=["sample", "daily"],
        help="'sample' generates a video without uploading; 'daily' generates and uploads to YouTube",
    )
    parser.add_argument("--topic", default=None, help="Override topic instead of auto-picking one")
    parser.add_argument(
        "--privacy", default="public", choices=["public", "unlisted", "private"],
        help="YouTube privacy status for uploaded video (daily mode only)",
    )
    args = parser.parse_args()

    upload = args.mode == "daily"
    result = run_pipeline(topic=args.topic, upload=upload, privacy_status=args.privacy)
    print(result)


if __name__ == "__main__":
    main()
