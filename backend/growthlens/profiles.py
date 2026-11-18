"""Preset business profiles: priors for the LLM, and the offline fallback when it is unavailable.

Tag values of "" mean "any value for this key". Weights are relative (normalised at scoring time).
"""

# (key, value, weight) for demand drivers; (key, value) for competitors / access
PRESETS: dict[str, dict] = {
    "cafe": {
        "label": "Specialty café",
        "keywords": ["cafe", "café", "coffee", "espresso", "tea house", "bakery cafe"],
        "competitors": [("amenity", "cafe")],
        "demand": [
            ("amenity", "college", 3.0), ("amenity", "university", 3.0), ("amenity", "coworking_space", 2.0),
            ("office", "", 1.0), ("amenity", "library", 1.0), ("shop", "mall", 1.0),
        ],
        "access": [("highway", "bus_stop"), ("railway", "station"), ("railway", "subway_entrance")],
        "weights": {"growth": 0.25, "activity": 0.15, "demand": 0.30, "competition": 0.20, "access": 0.10},
    },
    "pharmacy": {
        "label": "Pharmacy",
        "keywords": ["pharmacy", "chemist", "drugstore", "medical store", "medicine"],
        "competitors": [("amenity", "pharmacy"), ("shop", "chemist")],
        "demand": [
            ("amenity", "hospital", 3.0), ("amenity", "clinic", 3.0), ("amenity", "doctors", 2.0),
            ("building", "apartments", 0.5), ("landuse", "residential", 0.5),
        ],
        "access": [("highway", "bus_stop"), ("railway", "station")],
        "weights": {"growth": 0.25, "activity": 0.10, "demand": 0.35, "competition": 0.20, "access": 0.10},
    },
    "gym": {
        "label": "Gym / fitness studio",
        "keywords": ["gym", "fitness", "yoga", "crossfit", "workout"],
        "competitors": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
        "demand": [
            ("office", "", 1.5), ("amenity", "college", 1.5), ("amenity", "university", 1.5),
            ("building", "apartments", 1.0), ("landuse", "residential", 1.0),
        ],
        "access": [("highway", "bus_stop"), ("railway", "station")],
        "weights": {"growth": 0.30, "activity": 0.10, "demand": 0.25, "competition": 0.25, "access": 0.10},
    },
    "clinic": {
        "label": "Clinic",
        "keywords": ["clinic", "doctor", "dental", "dentist", "polyclinic", "diagnostic"],
        "competitors": [("amenity", "clinic"), ("amenity", "doctors"), ("amenity", "dentist")],
        "demand": [
            ("building", "apartments", 1.0), ("landuse", "residential", 1.0), ("amenity", "pharmacy", 1.0),
            ("amenity", "hospital", 0.5),
        ],
        "access": [("highway", "bus_stop"), ("railway", "station")],
        "weights": {"growth": 0.30, "activity": 0.10, "demand": 0.25, "competition": 0.25, "access": 0.10},
    },
    "ev_charging": {
        "label": "EV charging station",
        "keywords": ["ev charging", "ev charger", "electric vehicle", "charging station"],
        "competitors": [("amenity", "charging_station")],
        "demand": [
            ("shop", "mall", 2.0), ("office", "", 1.5), ("amenity", "parking", 1.5),
            ("amenity", "fuel", 1.0), ("tourism", "hotel", 1.0),
        ],
        "access": [("highway", "motorway_junction"), ("highway", "trunk")],
        "weights": {"growth": 0.30, "activity": 0.15, "demand": 0.25, "competition": 0.15, "access": 0.15},
    },
    "supermarket": {
        "label": "Supermarket",
        "keywords": ["supermarket", "grocery", "grocer", "hypermarket", "mart", "convenience store"],
        "competitors": [("shop", "supermarket"), ("shop", "convenience")],
        "demand": [
            ("building", "apartments", 1.5), ("landuse", "residential", 1.5),
            ("office", "", 0.5), ("amenity", "marketplace", 0.5),
        ],
        "access": [("highway", "bus_stop"), ("railway", "station")],
        "weights": {"growth": 0.25, "activity": 0.10, "demand": 0.30, "competition": 0.25, "access": 0.10},
    },
}


def match_preset(text: str) -> str | None:
    """Keyword match (whole-word-ish) against preset keywords. First preset with the longest hit wins."""
    t = text.lower()
    best, best_len = None, 0
    for key, p in PRESETS.items():
        for kw in [key.replace("_", " "), *p["keywords"]]:
            if kw in t and len(kw) > best_len:
                best, best_len = key, len(kw)
    return best
