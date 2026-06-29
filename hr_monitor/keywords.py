"""Keyword categories used to classify HR-relevant news items."""

LABOR_DISPUTE = [
    "strike", "walkout", "labor dispute", "labour dispute", "union",
    "layoff", "layoffs", "mass layoff", "job cuts", "redundancies",
    "wage dispute", "picket", "labor strike", "labour strike",
    "workers protest", "industrial action", "collective bargaining",
    "factory closure", "plant closure", "unrest among workers",
]

WORKPLACE_SAFETY = [
    "workplace accident", "workplace injury", "occupational safety",
    "factory fire", "factory collapse", "building collapse",
    "chemical leak", "gas leak", "explosion at", "mine collapse",
    "construction site accident", "industrial accident",
    "workplace fatality", "worker killed", "workers killed",
]

DISASTER_EMERGENCY = [
    "earthquake", "tsunami", "wildfire", "flood", "flooding",
    "hurricane", "typhoon", "cyclone", "volcanic eruption",
    "landslide", "mudslide", "evacuation order", "state of emergency",
    "outbreak", "pandemic", "epidemic", "curfew", "civil unrest",
    "coup", "war", "airstrike", "terror attack", "terrorist attack",
    "power outage", "blackout", "travel ban", "border closure",
]

ALL_CATEGORIES = {
    "Labor/Workforce Issue": LABOR_DISPUTE,
    "Workplace Safety": WORKPLACE_SAFETY,
    "Disaster/Emergency": DISASTER_EMERGENCY,
}


def classify(text: str) -> list[str]:
    """Return the list of category names whose keywords match the text."""
    lowered = text.lower()
    matched = []
    for category, keywords in ALL_CATEGORIES.items():
        if any(kw in lowered for kw in keywords):
            matched.append(category)
    return matched
