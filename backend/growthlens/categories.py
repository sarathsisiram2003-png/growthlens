"""Hardcoded business profiles for Phase 1. Phase 2 replaces this with LLM intent parsing.

Tags are (key, value) pairs; value None means "any value for this key".
"""

PROFILES: dict[str, dict] = {
    "cafe": {
        "label": "Specialty café",
        "competitors": [("amenity", "cafe")],
        # demand drivers with relative weights
        "demand": {
            ("amenity", "college"): 3.0,
            ("amenity", "university"): 3.0,
            ("amenity", "coworking_space"): 2.0,
            ("office", None): 1.0,
            ("amenity", "library"): 1.0,
            ("shop", "mall"): 1.0,
        },
        "access": [("highway", "bus_stop"), ("railway", "station"), ("railway", "subway_entrance")],
        "weights": {  # must sum to 1 (positive terms; competition is inverted in scoring)
            "growth": 0.25,
            "activity": 0.15,
            "demand": 0.30,
            "competition": 0.20,
            "access": 0.10,
        },
    },
}


def get_profile(category: str) -> dict:
    try:
        return PROFILES[category]
    except KeyError as e:
        raise ValueError(f"Unknown category '{category}'. Available: {', '.join(PROFILES)}") from e
