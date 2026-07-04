"""Global HR monitoring: scans location-scoped news feeds for labor,
workplace-safety, and disaster/emergency news, and sends one combined
Telegram digest per run for any newly matched items.

Each run fetches the configured RSS feeds (one Google News search per
monitored location), classifies items against the keyword categories in
keywords.py, and bundles any item not already alerted (tracked in
alerted_items.json so re-runs don't spam duplicate alerts) into a single
digest message.
"""

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from hr_monitor.config import MAX_ITEM_AGE_HOURS, STATE_FILE
from hr_monitor.keywords import CATEGORY_KR, classify
from hr_monitor.sources import FEEDS
from hr_monitor.telegram_notify import send_telegram_message
from hr_monitor.translate import translate_to_korean

USER_AGENT = "Mozilla/5.0 (compatible; hr-monitor-bot/1.0)"
MAX_TRACKED_IDS = 2000
TELEGRAM_MAX_LEN = 4000
MAX_ITEMS_PER_LOCATION = 8


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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _two_line_summary(title: str, description: str) -> str:
    """Return a short ~2-line summary: the title plus up to one extra sentence."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(description) if s.strip()]
    extra = sentences[0] if sentences else ""
    if extra and extra.lower() not in title.lower():
        extra = extra[:160]
        return f"{title}\n{extra}"
    return title


def _build_digest(matches: list[dict]) -> str:
    lines = [f"\U0001F6A8 <b>HR 모니터링 알림 ({len(matches)}건)</b>", ""]
    by_region: dict[str, list[dict]] = {}
    for match in matches:
        by_region.setdefault(match["region"], []).append(match)

    for region, region_matches in by_region.items():
        lines.append(f"\U0001F4CD <b>{region}</b>")
        for match in region_matches:
            item = match["item"]
            cat_line = ", ".join(CATEGORY_KR.get(c, c) for c in match["categories"])
            summary = _two_line_summary(item["title"], item["description"])
            summary_kr = translate_to_korean(summary)
            lines.append(f"[{cat_line}] {summary_kr}")
            if item["link"]:
                lines.append(item["link"])
            lines.append("")
        lines.append("")

    return "\n".join(lines).strip()


def _chunk_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for block in text.split("\n\n"):
        block_len = len(block) + 2
        if current_len + block_len > max_len and current:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(block)
        current_len += block_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def run_once(dry_run: bool = False) -> list[dict]:
    """Scan all configured location feeds once and digest new HR-relevant items
    into a single Telegram message.

    Returns the list of matched items (or that would be matched, if dry_run).
    """
    seen = _load_state()
    new_seen = set(seen)
    matches = []

    for region, url, source in FEEDS:
        try:
            items = _fetch_feed(url)
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"[hr_monitor] fetch failed for {source} ({region}): {exc}")
            continue

        for item in items[:MAX_ITEMS_PER_LOCATION]:
            if not _is_recent(item["pub_date"]):
                continue
            item_id = _item_id(item, region)
            if item_id in seen:
                continue

            categories = classify(f"{item['title']} {item['description']}") or ["일반 뉴스"]

            matches.append(
                {"region": region, "source": source, "categories": categories, "item": item}
            )
            new_seen.add(item_id)

    if matches:
        digest = _build_digest(matches)
        if not dry_run:
            for chunk in _chunk_message(digest):
                send_telegram_message(chunk)
    else:
        if not dry_run:
            now_kst = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            send_telegram_message(f"✅ HR 모니터링 정상 실행 ({now_kst})\n새로운 특이사항 없음")

    if not dry_run:
        _save_state(new_seen)

    return matches
