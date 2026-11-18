"""Orchestrates geocode -> H3 -> OSM -> satellite -> score -> JSON."""
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .geocode import geocode_city
from .grid import city_hexes, hex_centre
from .intent import Intent
from .osm import osm_metrics
from .satellite import satellite_metrics
from .scoring import METRICS, score_hexes, top_n

Progress = Callable[[str], None]


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def run_pipeline(
    city_name: str, intent: Intent, weights: dict[str, float] | None = None, progress: Progress | None = None,
    skip_satellite: bool = False,
) -> dict:
    say = progress or (lambda _m: None)
    profile = intent.to_profile()
    weights = weights or profile["weights"]
    res = settings.h3_resolution

    say("1/5 Geocoding city")
    city = geocode_city(city_name)
    minx, miny, maxx, maxy = city.boundary.bounds
    bbox = (miny, minx, maxy, maxx)  # south, west, north, east

    say("2/5 Building H3 grid")
    cells = city_hexes(city.boundary, res)
    if not cells:
        raise RuntimeError("City boundary produced no hexagons")
    say(f"  {len(cells)} hexes at resolution {res}")

    say("3/5 Reading OpenStreetMap (competitors, demand, access)")
    osm = osm_metrics(bbox, cells, profile, res)

    flags: list[str] = []
    if osm["coverage"] < 0.25:
        flags.append("thin_osm_coverage")

    if skip_satellite:
        say("4/5 Skipping satellite data (--skip-satellite)")
        sat = {"growth": {}, "activity": {}}
        flags.append("satellite_skipped")
    else:
        say("4/5 Reading satellite history (Dynamic World + VIIRS)")
        sat = satellite_metrics(cells, bbox, say)
        for m in ("growth", "activity"):
            missing = sum(1 for c in cells if sat[m].get(c) is None)
            if missing > 0.2 * len(cells):
                flags.append(f"{m}_data_missing")

    raw = {
        "growth": {c: sat["growth"].get(c) for c in cells},
        "activity": {c: sat["activity"].get(c) for c in cells},
        "demand": {c: osm["demand"].get(c, 0.0) for c in cells},
        "competition": {c: osm["competitors"].get(c, 0.0) for c in cells},
        "access": {c: osm["access"].get(c, 0.0) for c in cells},
    }

    say("5/5 Scoring areas")
    scored = score_hexes(raw, weights)
    top = top_n(scored, 10)
    rank = {h: i + 1 for i, h in enumerate(top)}

    hexes_out = []
    for c in cells:
        lat, lon = hex_centre(c)
        hexes_out.append(
            {
                "hex": c,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "score": scored[c]["score"],
                "rank": rank.get(c),
                "raw": {m: raw[m][c] for m in METRICS},
                "norm": scored[c]["norm"],
            }
        )

    return {
        "city": {"name": city.name, "display_name": city.display_name, "lat": city.lat, "lon": city.lon},
        "category": intent.category_key,
        "label": profile["label"],
        "intent": intent.model_dump(),
        "h3_resolution": res,
        "weights": weights,
        "windows": {
            "growth": [settings.growth_start_year, settings.growth_end_year],
            "viirs": [settings.viirs_start, settings.viirs_end],
        },
        "data_quality": {"osm_coverage": round(osm["coverage"], 3), "n_competitors": osm["n_competitors"], "flags": flags},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Scores are relative to this city and rank areas; they are not a guarantee of success.",
        "top10": top,
        "hexes": hexes_out,
    }


def save_result(result: dict, out: Path | None = None) -> Path:
    path = out or settings.output_dir / f"{slug(result['city']['name'])}_{result['category']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=1), encoding="utf-8")
    return path
