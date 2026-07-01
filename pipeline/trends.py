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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

from pipeline.config import TOPICS_STATE_FILE
import json

GOOGLE_TRENDS_GEOS = ["SA", "EG", "US", "MX", "GB"]
REDDIT_URL = "https://www.reddit.com/r/all/top.json?limit=25&t=day"
ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
CNN_RSS_URL = "http://rss.cnn.com/rss/cnn_topstories.rss"
BBC_RSS_URL = "http://feeds.bbci.co.uk/news/world/rss.xml"
APNEWS_RSS_URL = "https://apnews.com/apf-topnews?outputType=rss"
SKYNEWS_RSS_URL = "https://feeds.skynews.com/feeds/rss/world.xml"

INCIDENT_KEYWORDS = {
    "kill", "killed", "killing", "dead", "death", "deaths", "crash", "explosion",
    "fire", "earthquake", "attack", "attacks", "arrest", "arrested", "war",
    "flood", "flooding", "shooting", "shot", "collapse", "evacuate", "evacuated",
    "disaster", "missing", "rescue", "injured", "wounded", "blast", "storm",
    "hurricane", "wildfire", "accident", "حادث", "حريق", "زلزال", "انفجار",
    "مقتل", "قتل", "اعتقال", "كارثة",
}
USER_AGENT = "Mozilla/5.0 (compatible; trend-pulse-bot/1.0)"
REDDIT_USER_AGENT = "trend-pulse-bot/1.0 (by /u/trendpulse999)"

_BANNED_KEYWORDS = {"cricket", "كريكيت", "ipl", "bcci", "t20", "odi", "icc"}


def _is_banned_topic(topic: str) -> bool:
    lowered = topic.lower()
    return any(kw in lowered for kw in _BANNED_KEYWORDS)


_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "is",
    "are", "was", "were", "with", "by", "as", "from", "after", "over", "amid",
    "this", "that", "his", "her", "its", "their", "new", "says", "say",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z؀-ۿ]+", text.lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


_RECENT_CATEGORY_WINDOW = 5  # how many recent topics to remember for diversity


def _load_state() -> dict:
    if TOPICS_STATE_FILE.exists():
        try:
            raw = json.loads(TOPICS_STATE_FILE.read_text())
            # Support old format (plain list) and new format (dict with keys)
            if isinstance(raw, list):
                return {"used": raw, "recent_keywords": []}
            return raw
        except Exception:
            pass
    return {"used": [], "recent_keywords": []}


def _save_state(state: dict):
    TOPICS_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _category_overlap_penalty(topic: str, ctx: list[str], recent_kw_sets: list[set]) -> int:
    """Return a negative penalty if this topic overlaps heavily with recent picks."""
    if not recent_kw_sets:
        return 0
    topic_words = _significant_words(f"{topic} {' '.join(ctx[:3])}")
    penalty = 0
    for prev_kw in recent_kw_sets:
        overlap = len(topic_words & prev_kw)
        if overlap >= 3:
            penalty -= 8   # strong category match — heavily penalise
        elif overlap >= 1:
            penalty -= 3   # mild overlap
    return penalty


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
                pub_dt = None
                if pub_date:
                    context_lines.append(f"Trend detected on: {pub_date.strip()}")
                    try:
                        pub_dt = parsedate_to_datetime(pub_date.strip())
                    except Exception:
                        pass
                for news_item in item.findall("ht:news_item", NS):
                    news_title = news_item.findtext("ht:news_item_title", namespaces=NS)
                    news_source = news_item.findtext("ht:news_item_source", namespaces=NS)
                    if news_title:
                        line = news_title.strip()
                        if news_source:
                            line = f"{line} ({news_source.strip()})"
                        context_lines.append(line)
                candidates.append((title.strip(), context_lines, pub_dt))
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"[trends] Google Trends fetch failed for geo={geo}: {exc}")
            continue
    return candidates


def _fetch_reddit_trends():
    """Return a list of (topic, context_lines, pub_dt) tuples from Reddit post titles."""
    candidates = []
    try:
        resp = requests.get(REDDIT_URL, headers={"User-Agent": REDDIT_USER_AGENT}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title")
            created = post.get("created_utc")
            pub_dt = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
            if title:
                candidates.append((title.strip(), [], pub_dt))
    except (requests.RequestException, ValueError) as exc:
        print(f"[trends] Reddit fetch failed: {exc}")
    return candidates


def _fetch_news_rss(url: str, source_name: str):
    """Return a list of (title, description, pub_dt) tuples from a news RSS feed.

    Articles without a parseable pubDate, or older than 3 days, are excluded
    so stale evergreen content never gets picked as a 'trending' topic.
    """
    now = datetime.now(tz=timezone.utc)
    items = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            title = item.findtext("title")
            if not title:
                continue
            pub_date_str = item.findtext("pubDate") or ""
            pub_dt = None
            if pub_date_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str.strip())
                except Exception:
                    pass
            # Skip articles we can't date, or that are older than 3 days.
            if pub_dt is None or (now - pub_dt).days > 3:
                continue
            description = item.findtext("description") or ""
            description = re.sub(r"<[^>]+>", "", description).strip()
            items.append((title.strip(), description, pub_dt))
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[trends] {source_name} fetch failed: {exc}")
    return items


def _fetch_aljazeera_news():
    return _fetch_news_rss(ALJAZEERA_RSS_URL, "Al Jazeera")


def _fetch_cnn_news():
    return _fetch_news_rss(CNN_RSS_URL, "CNN")


def _fetch_bbc_news():
    return _fetch_news_rss(BBC_RSS_URL, "BBC")


def _fetch_apnews():
    return _fetch_news_rss(APNEWS_RSS_URL, "AP News")


def _fetch_skynews():
    return _fetch_news_rss(SKYNEWS_RSS_URL, "Sky News")


def _is_incident_topic(text: str) -> bool:
    words = _significant_words(text)
    return bool(words & INCIDENT_KEYWORDS)


def _news_context_line(title: str, description: str, source: str) -> str:
    line = title.strip()
    if description:
        line = f"{line} - {description.strip()}"
    return f"{line} ({source})"


def _matching_news_lines(topic: str, news_items) -> list[str]:
    """Find recent news headlines that share significant keywords with topic."""
    topic_words = _significant_words(topic)
    if not topic_words:
        return []
    lines = []
    for title, description, _pub_dt, source in news_items:
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
    state = _load_state()
    used = set(state["used"])
    recent_kw_sets = [set(kws) for kws in state.get("recent_keywords", [])]

    aljazeera_items = _fetch_aljazeera_news()
    cnn_items = _fetch_cnn_news()
    bbc_items = _fetch_bbc_news()
    ap_items = _fetch_apnews()
    sky_items = _fetch_skynews()
    # news_items: (title, description, pub_dt, source)
    news_items = (
        [(t, d, dt, "Al Jazeera") for t, d, dt in aljazeera_items]
        + [(t, d, dt, "CNN") for t, d, dt in cnn_items]
        + [(t, d, dt, "BBC") for t, d, dt in bbc_items]
        + [(t, d, dt, "AP News") for t, d, dt in ap_items]
        + [(t, d, dt, "Sky News") for t, d, dt in sky_items]
    )

    now_utc = datetime.now(tz=timezone.utc)

    candidates = _fetch_google_trends() + _fetch_reddit_trends()
    # News headlines are themselves valid trending topics — use their pub_dt for recency scoring.
    candidates += [(t, [_news_context_line(t, d, s)], dt) for t, d, dt, s in news_items]

    available = [
        (t, ctx, pub_dt) for t, ctx, pub_dt in candidates
        if t and t not in used and not _is_banned_topic(t)
    ]

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
    for topic, ctx, pub_dt in available:
        extra = _matching_news_lines(topic, news_items)
        merged_ctx = list(ctx)
        for line in extra:
            if line not in merged_ctx:
                merged_ctx.append(line)
        enriched.append((topic, merged_ctx, pub_dt))

    # Only use topics that have real news context — no bare keywords where
    # the model would have to guess/fabricate what the topic actually refers to.
    with_context = [(t, ctx, dt) for t, ctx, dt in enriched if ctx]
    pool = with_context or enriched

    # Rank by hotness:
    # +1 per corroborating source, +5 for incident/accident content,
    # +8 if published today (UTC), +4 if published within the last 24 h.
    def _hotness(item):
        topic_text, ctx, pub_dt = item
        score = len(ctx)
        if _is_incident_topic(topic_text) or any(_is_incident_topic(line) for line in ctx):
            score += 5
        if pub_dt:
            age_hours = (now_utc - pub_dt).total_seconds() / 3600
            if age_hours <= 12:
                score += 8
            elif age_hours <= 24:
                score += 4
        score += _category_overlap_penalty(topic_text, ctx, recent_kw_sets)
        return score

    pool.sort(key=_hotness, reverse=True)

    topic, context, _ = pool[0]

    # Persist used topic and update recent-category window
    used.add(topic)
    topic_kws = sorted(_significant_words(f"{topic} {' '.join(context[:3])}"))
    recent_kw_sets_updated = ([list(s) for s in recent_kw_sets] + [topic_kws])[-_RECENT_CATEGORY_WINDOW:]
    _save_state({"used": sorted(used), "recent_keywords": recent_kw_sets_updated})
    return {"topic": topic, "context": context}
