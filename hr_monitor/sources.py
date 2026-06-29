"""Region-tagged news RSS feeds used as HR monitoring sources."""

# Each entry: (region_label, feed_url, source_name)
FEEDS = [
    ("Global", "http://feeds.bbci.co.uk/news/world/rss.xml", "BBC World"),
    ("Global", "https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
    ("Global", "http://rss.cnn.com/rss/cnn_topstories.rss", "CNN"),
    ("Middle East", "https://www.aljazeera.com/xml/rss/all.xml", "Al Jazeera"),
    ("Asia", "http://feeds.bbci.co.uk/news/world/asia/rss.xml", "BBC Asia"),
    ("Europe", "http://feeds.bbci.co.uk/news/world/europe/rss.xml", "BBC Europe"),
    ("Africa", "http://feeds.bbci.co.uk/news/world/africa/rss.xml", "BBC Africa"),
    ("US & Canada", "http://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "BBC US & Canada"),
    ("Latin America", "http://feeds.bbci.co.uk/news/world/latin_america/rss.xml", "BBC Latin America"),
]
