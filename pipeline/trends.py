"""Real-time trending topic discovery.

Replaces the old static topic-rotation list. Topics are pulled live from
Google Trends (daily trending searches RSS) and Reddit's public "top of the
day" listing, then cross-referenced against real news headlines from Al
Jazeera and CNN's RSS feeds so script generation has actual reported facts
to ground narration in. There is intentionally no static/sample topic list
here: if all live sources fail, `get_trending_topic` raises instead of
inventing a fallback topic.
"""

import re
import xml.etree.ElementTree as ET

import requests

from pipeline.config import TOPICS_STATE_FILE
import json

GOOGLE_TRENDS_GEOS = ["SA", "EG", "US"]
REDDIT_URL = "https://www.reddit.com/r/all/top.json?limit=25&t=day"
ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
CNN_RSS_URL = "http://rss.cnn.com/rss/cnn_topstories.rss"
USER_AGENT = "Mozilla/5.0 (compatible; trend-pulse-bot/1.0)"
REDDIT_USER_AGENT = "trend-pulse-bot/1.0 (by /u/trendpulse999)"

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "with", "by", "as", "from", "after", "over", "amid",
    "this", "that", "his", "her", "its", "their", "new", "says", "say",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z؀-ۿ]+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


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
                pub_date = item.findtext("pubDate")
                if pub_date:
                    context_lines.append(f"Trend detected on: {pub_date.strip()}")
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


def _fetch_news_rss(url: str, source_name: str):
    """Return a list of (title, description) tuples from a generic news RSS feed."""
    items = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = item.findtext("title")
            if not title:
                continue
            description = item.findtext("description") or ""
            description = re.sub(r"<[^>]+>", "", description).strip()
            items.append((title.strip(), description))
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[trends] {source_name} fetch failed: {exc}")
    return items


def _fetch_aljazeera_news():
    return _fetch_news_rss(ALJAZEERA_RSS_URL, "Al Jazeera")


def _fetch_cnn_news():
    return _fetch_news_rss(CNN_RSS_URL, "CNN")


def _news_context_line(title: str, description: str, source: str) -> str:
    line = title.strip()
    if description:
        line = f"{line} - {description.strip()}"
    return f"{line} ({source})"


def _matching_news_lines(topic: str, news_items: list[tuple[str, str, str]]) -> list[str]:
    """Find Al Jazeera/CNN headlines that share significant keywords with topic."""
    topic_words = _significant_words(topic)
    if not topic_words:
        return []
    lines = []
    for title, description, source in news_items:
        item_words = _significant_words(f"{title} {description}")
        if topic_words & item_words:
            lines.append(_news_context_line(title, description, source))
    return lines


def get_trending_topic() -> dict:
    """Return a fresh real-time trending topic from Google Trends or Reddit.

    The result is {"topic": str, "context": list[str]}, where "context" holds
    real news headlines associated with the topic (when available) so script
    generation has actual facts to ground narration in, instead of inventing
    a plausible-sounding but fabricated story for an ambiguous keyword.

    Raises RuntimeError if no live trend source returns a usable, unused topic.
    """
    used = _load_used()

    aljazeera_items = _fetch_aljazeera_news()
    cnn_items = _fetch_cnn_news()
    news_items = (
        [(t, d, "Al Jazeera") for t, d in aljazeera_items]
        + [(t, d, "CNN") for t, d in cnn_items]
    )

    candidates = _fetch_google_trends() + _fetch_reddit_trends()
    # Al Jazeera/CNN headlines are themselves valid trending topics, grounded
    # in their own reporting.
    candidates += [(t, [_news_context_line(t, d, s)]) for t, d, s in news_items]

    available = [(t, ctx) for t, ctx in candidates if t and t not in used]

    if not available:
        raise RuntimeError(
            "No live trending topics available from Google Trends, Reddit, "
            "Al Jazeera or CNN (all sources empty/failed, or all current "
            "trends already used)."
        )

    # Cross-reference each candidate against Al Jazeera/CNN reporting so the
    # script generator has real, attributed facts to ground narration in
    # instead of guessing what an ambiguous trending keyword refers to.
    enriched = []
    for topic, ctx in available:
        extra = _matching_news_lines(topic, news_items)
        merged_ctx = list(ctx)
        for line in extra:
            if line not in merged_ctx:
                merged_ctx.append(line)
        enriched.append((topic, merged_ctx))

    # Prefer topics with real news context attached: they ground the script
    # in actual facts and avoid the model guessing/fabricating context for a
    # bare, ambiguous keyword.
    with_context = [(t, ctx) for t, ctx in enriched if ctx]
    pool = with_context or enriched

    topic, context = pool[0]
    used.add(topic)
    _save_used(used)
    return {"topic": topic, "context": context}
