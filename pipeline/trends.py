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
REDDIT_USER_AGENT = "trend-pulse-bot/1.0 (by /u/trendpulse999)"


def _load_used():
    if TOPICS_STATE_FILE.exists():
        return set(json.loads(TOPICS_STATE_FILE.read_text()))
    return set()


def _save_used(used):
    TOPICS_STATE_FILE.write_text(json.dumps(sorted(used), ensure_ascii=False, indent=2))


NS = {"ht": "https://trends.google.com/trending/rss"}


def _fetch_google_trends():
    """Return a list of (topic, context_lines) tuples.

    context_lines holds the real news headlines Google Trends associates with
    the topic, so script generation can ground narration in actual facts
    instead of guessing what the bare keyword refers to.
    """
    candidates = []
    for geo in GOOGLE_TRENDS_GEOS:
        url = f"https://trends.google.com/trending/rss?geo={geo}"
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.findtext("title")
                if not title:
                    continue
                context_lines = []
                for news_item in item.findall("ht:news_item", NS):
                    news_title = news_item.findtext("ht:news_item_title", namespaces=NS)
                    news_source = news_item.findtext("ht:news_item_source", namespaces=NS)
                    if news_title:
                        line = news_title.strip()
                        if news_source:
                            line = f"{line} ({news_source.strip()})"
                        context_lines.append(line)
                candidates.append((title.strip(), context_lines))
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"[trends] Google Trends fetch failed for geo={geo}: {exc}")
            continue
    return candidates


def _fetch_reddit_trends():
    """Return a list of (topic, context_lines) tuples from Reddit post titles."""
    candidates = []
    try:
        resp = requests.get(REDDIT_URL, headers={"User-Agent": REDDIT_USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for child in data.get("data", {}).get("children", []):
            title = child.get("data", {}).get("title")
            if title:
                candidates.append((title.strip(), []))
    except (requests.RequestException, ValueError) as exc:
        print(f"[trends] Reddit fetch failed: {exc}")
    return candidates


def get_trending_topic() -> dict:
    """Return a fresh real-time trending topic from Google Trends or Reddit.

    The result is {"topic": str, "context": list[str]}, where "context" holds
    real news headlines associated with the topic (when available) so script
    generation has actual facts to ground narration in, instead of inventing
    a plausible-sounding but fabricated story for an ambiguous keyword.

    Raises RuntimeError if no live trend source returns a usable, unused topic.
    """
    used = _load_used()

    candidates = _fetch_google_trends() + _fetch_reddit_trends()
    available = [(t, ctx) for t, ctx in candidates if t and t not in used]

    if not available:
        raise RuntimeError(
            "No live trending topics available from Google Trends or Reddit "
            "(all sources empty/failed, or all current trends already used)."
        )

    topic, context = available[0]
    used.add(topic)
    _save_used(used)
    return {"topic": topic, "context": context}
