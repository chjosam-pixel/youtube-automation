import argparse

from hr_monitor.monitor import run_once


def main():
    parser = argparse.ArgumentParser(
        description="Global HR monitoring: scan world news for labor, workplace-safety, "
        "and disaster/emergency issues and alert via Telegram."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and print matches without sending Telegram alerts or updating state",
    )
    args = parser.parse_args()

    alerts = run_once(dry_run=args.dry_run)
    if not alerts:
        print("No new HR-relevant items found.")
    for alert in alerts:
        print(f"[{alert['region']}] {alert['source']}: {alert['item']['title']} -> {alert['categories']}")


if __name__ == "__main__":
    main()
