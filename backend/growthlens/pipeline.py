"""Orchestrates geocode -> H3 -> OSM -> satellite -> score -> JSON."""
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from shapely.geometry import mapping

from .geocode import geocode_city, reverse_area
from .grid import choose_resolution, hex_centre
from .intent import Intent
from .osm import osm_metrics
from .quality import assess
from .reasons import build_reason
from .satellite import EarthEngineError, satellite_metrics
from .scoring import METRICS, score_hexes, top_n

# progress(step, message, meta). Steps: map, satellite, competitors, scoring, briefs.
# meta may carry {"state": "skipped"} or {"boundary": geojson, "center": [lat, lon]}.
SCHEMA_VERSION = 3  # bump when the result JSON gains fields the UI needs (invalidates cached files)

Progress = Callable[[str, str, dict | None], None]


def _noop(_step: str, _msg: str, _meta: dict | None = None) -> None:
    pass


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_pipeline(
    city_name: str, intent: Intent, weights: dict[str, float] | None = None, progress: Progress | None = None,
    skip_satellite: bool = False,
) -> dict:
    say = progress or _noop
    profile = intent.to_profile()
    weights = weights or profile["weights"]

    say("map", "Geocoding city", None)
    city = geocode_city(city_name)
    minx, miny, maxx, maxy = city.boundary.bounds
    bbox = (miny, minx, maxy, maxx)  # south, west, north, east
    boundary_geojson = mapping(city.boundary.simplify(0.0008))
    say("map", "City boundary found", {"boundary": boundary_geojson, "center": [city.lat, city.lon]})

    # Grid resolution adapts to the city: finer for small towns, coarser for big metros, refused if enormous
    res, cells = choose_resolution(
        city.boundary, settings.h3_resolution, settings.min_hexes, settings.max_hexes, settings.max_area_km2
    )
    say("map", f"{len(cells)} areas at resolution {res}", None)

    flags: list[str] = []
    if skip_satellite:
        say("satellite", "Skipping satellite data", {"state": "skipped"})
        sat = {"growth": {}, "activity": {}}
        flags.append("satellite_skipped")
    else:
        say("satellite", "Reading satellite history (Dynamic World + VIIRS)", None)
        try:
            sat = satellite_metrics(cells, bbox, lambda m: say("satellite", m, None))
        except EarthEngineError as e:  # degrade gracefully: rank on OSM signals only
            say("satellite", f"Satellite data unavailable ({e}); continuing without it", {"state": "skipped"})
            sat = {"growth": {}, "activity": {}}
            flags.append("satellite_unavailable")
        else:
            for m in ("growth", "activity"):
                missing = sum(1 for c in cells if sat[m].get(c) is None)
                if missing > 0.2 * len(cells):
                    flags.append(f"{m}_data_missing")

    say("competitors", "Reading OpenStreetMap (competitors, demand, access)", None)
    osm = osm_metrics(bbox, cells, profile, res, lambda m: say("competitors", m, None))

    raw = {
        "growth": {c: sat["growth"].get(c) for c in cells},
        "activity": {c: sat["activity"].get(c) for c in cells},
        "demand": {c: osm["demand"].get(c, 0.0) for c in cells},
        "competition": {c: osm["competitors"].get(c, 0.0) for c in cells},
        "access": {c: osm["access"].get(c, 0.0) for c in cells},
    }

    say("scoring", "Scoring areas", None)
    scored = score_hexes(raw, weights)
    top = top_n(scored, 10)
    rank = {h: i + 1 for i, h in enumerate(top)}

    say("briefs", "Naming areas and writing summaries", None)
    hexes_out = []
    for c in cells:
        lat, lon = hex_centre(c)
        entry = {
            "hex": c,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "score": scored[c]["score"],
            "rank": rank.get(c),
            "raw": {m: raw[m][c] for m in METRICS},
            "norm": scored[c]["norm"],
        }
        if c in rank:
            entry["name"] = reverse_area(lat, lon) or f"Area near {lat:.3f}, {lon:.3f}"
            entry["reason"] = build_reason(scored[c]["norm"], entry["raw"])
        hexes_out.append(entry)

    return {
        "city": {
            "name": city.name, "display_name": city.display_name, "lat": city.lat, "lon": city.lon,
            "bbox": [minx, miny, maxx, maxy], "boundary": boundary_geojson,
        },
        "schema": SCHEMA_VERSION,
        "category": intent.category_key,
        "label": profile["label"],
        "intent": intent.model_dump(),
        "h3_resolution": res,
        "weights": weights,
        "windows": {
            "growth": [settings.growth_start_year, settings.growth_end_year],
            "viirs": [settings.viirs_start, settings.viirs_end],
            "imagery": [settings.imagery_start_year, settings.imagery_end_year],
        },
        "data_quality": assess(
            n_areas=len(cells), resolution=res, osm_coverage=osm["coverage"], n_competitors=osm["n_competitors"],
            n_demand_places=len(osm["places"]["drivers"]), tiles_failed=osm["tiles"]["failed"],
            tiles_total=osm["tiles"]["total"], approximate_boundary=city.approximate, extra_flags=flags,
            mean_growth=_mean([v for v in sat["growth"].values() if v is not None]),
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Scores are relative to this city and rank areas; they are not a guarantee of success.",
        "top10": top,
        "places": osm["places"],
        "hexes": hexes_out,
    }


def save_result(result: dict, out: Path | None = None) -> Path:
    path = out or settings.output_dir / f"{slug(result['city']['name'])}_{result['category']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    result["id"] = path.stem  # lets the UI address this result for briefs, imagery history, etc.
    path.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    return path
