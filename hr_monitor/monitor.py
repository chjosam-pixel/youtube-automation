"""Global HR monitoring: scans regional news feeds for labor, workplace-safety,
and disaster/emergency news, and alerts via Telegram on new matches.

Each run fetches the configured RSS feeds, classifies items against the
keyword categories in keywords.py, and sends a Telegram message for any
item not already alerted (tracked in alerted_items.json so re-runs don't
spam duplicate alerts).
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from hr_monitor.config import MAX_ITEM_AGE_HOURS, STATE_FILE
from hr_monitor.keywords import classify
from hr_monitor.sources import FEEDS
from hr_monitor.telegram_notify import send_telegram_message

USER_AGENT = "Mozilla/5.0 (compatible; hr-monitor-bot/1.0)"
MAX_TRACKED_IDS = 2000


def _load_state() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def _save_state(seen: set[str]) -> None:
    trimmed = sorted(seen)[-MAX_TRACKED_IDS:]
    STATE_FILE.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2))


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _is_recent(pub_date: str | None) -> bool:
    if not pub_date:
        return True  # can't tell age, don't drop the item
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
        return age_hours <= MAX_ITEM_AGE_HOURS
    except (TypeError, ValueError):
        return True


def _fetch_feed(url: str):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title")
        if not title:
            continue
        description = _strip_html(item.findtext("description") or "")
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate")
        items.append(
            {
                "title": title.strip(),
                "description": description,
                "link": link.strip(),
                "pub_date": pub_date,
            }
        )
    return items


def _item_id(item: dict, region: str) -> str:
    return item["link"] or f"{region}:{item['title']}"


def _format_alert(region: str, source: str, categories: list[str], item: dict) -> str:
    cat_line = ", ".join(categories)
    lines = [
        f"\U0001F6A8 <b>HR 모니터링 알림</b>",
        f"지역: {region} | 출처: {source}",
        f"분류: {cat_line}",
        "",
        f"<b>{item['title']}</b>",
    ]
    if item["description"]:
        lines.append(item["description"][:400])
    if item["link"]:
        lines.append(item["link"])
    return "\n".join(lines)


def run_once(dry_run: bool = False) -> list[dict]:
    """Scan all configured feeds once and alert on new HR-relevant items.

    Returns the list of alerts sent (or that would be sent, if dry_run).
    """
    seen = _load_state()
    new_seen = set(seen)
    alerts = []

    for region, url, source in FEEDS:
        try:
            items = _fetch_feed(url)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"[hr_monitor] fetch failed for {source} ({region}): {exc}")
            continue

        for item in items:
            if not _is_recent(item["pub_date"]):
                continue
            item_id = _item_id(item, region)
            if item_id in seen:
                continue

            categories = classify(f"{item['title']} {item['description']}")
            if not categories:
                new_seen.add(item_id)
                continue

            message = _format_alert(region, source, categories, item)
            if not dry_run:
                send_telegram_message(message)
            alerts.append(
                {"region": region, "source": source, "categories": categories, "item": item}
            )
            new_seen.add(item_id)

    if not dry_run:
        _save_state(new_seen)

    return alerts
