"""Data-quality assessment for a result: which signals are weak, and an overall level the UI can show.

Levels: "good" (nothing notable), "caution" (something to keep in mind) and "limited" (treat the ranking
as a rough guide only). Flags are stable ids; the frontend maps them to plain-language messages.
"""

SEVERITY = {
    # information only
    "finer_grid": "info",
    "coarser_grid": "info",
    # worth knowing
    "few_areas": "caution",
    "approximate_boundary": "caution",
    "thin_osm_coverage": "caution",
    "few_competitors": "caution",
    "osm_partial": "caution",
    "satellite_unavailable": "caution",
    "satellite_skipped": "caution",
    "growth_data_missing": "caution",
    "activity_data_missing": "caution",
    "intent_fallback_preset": "caution",
    # the ranking is a rough guide at best
    "very_thin_osm": "limited",
    "no_competitors_mapped": "limited",
}

THIN_OSM = 0.25  # share of areas with any mapped place below which OSM looks thin
VERY_THIN_OSM = 0.10
FEW_COMPETITORS = 10
FEW_AREAS = 30
PREFERRED_RESOLUTION = 8


def level_of(flags: list[str]) -> str:
    severities = [SEVERITY.get(f, "caution") for f in flags]
    if "limited" in severities or severities.count("caution") >= 3:
        return "limited"
    if "caution" in severities:
        return "caution"
    return "good"


def severities(flags: list[str]) -> dict[str, str]:
    """flag -> 'info' | 'caution' | 'limited' (sent to the UI so it never has to duplicate this table)."""
    return {f: SEVERITY.get(f, "caution") for f in flags}


def assess(
    *,
    n_areas: int,
    resolution: int,
    osm_coverage: float,
    n_competitors: int,
    n_demand_places: int,
    tiles_failed: int = 0,
    tiles_total: int = 1,
    approximate_boundary: bool = False,
    extra_flags: list[str] | None = None,
) -> dict:
    flags: list[str] = list(extra_flags or [])

    if osm_coverage < VERY_THIN_OSM:
        flags.append("very_thin_osm")
    elif osm_coverage < THIN_OSM:
        flags.append("thin_osm_coverage")

    if n_competitors == 0:
        flags.append("no_competitors_mapped")
    elif n_competitors < FEW_COMPETITORS:
        flags.append("few_competitors")

    if tiles_failed > 0:
        flags.append("osm_partial")
    if approximate_boundary:
        flags.append("approximate_boundary")
    if n_areas < FEW_AREAS:
        flags.append("few_areas")
    if resolution < PREFERRED_RESOLUTION:
        flags.append("coarser_grid")
    elif resolution > PREFERRED_RESOLUTION:
        flags.append("finer_grid")

    flags = list(dict.fromkeys(flags))  # de-duplicate, keep order
    return {
        "level": level_of(flags),
        "flags": flags,
        "severities": severities(flags),
        "osm_coverage": round(osm_coverage, 3),
        "n_competitors": n_competitors,
        "n_demand_places": n_demand_places,
        "n_areas": n_areas,
        "resolution": resolution,
        "osm_tiles": {"total": tiles_total, "failed": tiles_failed},
    }


def add_flag(dq: dict, flag: str) -> dict:
    """Add a flag after the fact (e.g. 'intent_fallback_preset') and recompute the level."""
    if flag not in dq["flags"]:
        dq["flags"].append(flag)
    dq["level"] = level_of(dq["flags"])
    dq["severities"] = severities(dq["flags"])
    return dq
