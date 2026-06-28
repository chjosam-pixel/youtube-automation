"""Real-time trending topic discovery.

Replaces the old static topic-rotation list. Topics are pulled live from
Google Trends (daily trending searches RSS) and, if that yields nothing
usable, from Reddit's public "top of the day" listing. There is
intentionally no static/sample topic list here: if both live sources fail,
`get_trending_topic` raises instead of inventing a fallback topic.
"""

import xml.etree.ElementTree as ET

import requests

from pipeline.config import TOPICS_STATE_FILE
import json

GOOGLE_TRENDS_GEOS = ["SA", "EG", "US"]
REDDIT_URL = "https://www.reddit.com/r/all/top.json?limit=25&t=day"
USER_AGENT = "Mozilla/5.0 (compatible; trend-pulse-bot/1.0)"


def _load_used():
    if TOPICS_STATE_FILE.exists():
        return set(json.loads(TOPICS_STATE_FILE.read_text()))
    return set()


def _save_used(used):
    TOPICS_STATE_FILE.write_text(json.dumps(sorted(used), ensure_ascii=False, indent=2))


def _fetch_google_trends():
    topics = []
    for geo in GOOGLE_TRENDS_GEOS:
        url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.findtext("title")
                if title:
                    topics.append(title.strip())
        except (requests.RequestException, ET.ParseError):
            continue
    return topics


def _fetch_reddit_trends():
    topics = []
    try:
        resp = requests.get(REDDIT_URL, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for child in data.get("data", {}).get("children", []):
            title = child.get("data", {}).get("title")
            if title:
                topics.append(title.strip())
    except (requests.RequestException, ValueError):
        pass
    return topics


def get_trending_topic() -> str:
    """Return a fresh real-time trending topic from Google Trends or Reddit.

    Raises RuntimeError if no live trend source returns a usable, unused topic.
    """
    used = _load_used()

    candidates = _fetch_google_trends() + _fetch_reddit_trends()
    available = [t for t in candidates if t and t not in used]

    if not available:
        raise RuntimeError(
            "No live trending topics available from Google Trends or Reddit "
            "(all sources empty/failed, or all current trends already used)."
        )

    topic = available[0]
    used.add(topic)
    _save_used(used)
    return topic
