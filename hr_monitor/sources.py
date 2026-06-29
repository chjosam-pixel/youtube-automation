"""Location-scoped news sources for the Global HR monitoring system.

Each entry is a specific office/plant location to monitor. News is fetched
per-location via Google News RSS search so results stay scoped to that city
and aren't drowned out by generic world-news noise.
"""

import urllib.parse

LOCATIONS = [
    ("Chennai, India", "Chennai India"),
    ("Pune, India", "Pune India"),
    ("Monterrey, Mexico", "Monterrey Mexico"),
    ("Qingdao, China", "Qingdao China"),
    ("Wuxi, China", "Wuxi China"),
    ("Troy, Michigan", "Troy Michigan"),
    ("Tokyo, Japan", "Tokyo Japan"),
]


def google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"


# (region_label, feed_url) pairs, kept as FEEDS for compatibility with monitor.py.
FEEDS = [(label, google_news_rss_url(query), "Google News") for label, query in LOCATIONS]
