"""Location briefs: a short, honest write-up for one area (why here, risks, suggested format).

The LLM is given only computed facts and told not to invent anything. If it is unavailable or returns
something unusable we fall back to a template built from the same facts, so the drawer never breaks.
"""
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from . import cache
from .config import settings
from .llm import generate_json
from .reasons import build_reason

RADIUS_M = 1200


class BriefCore(BaseModel):
    model_config = ConfigDict(extra="forbid")
    why_here: str = Field(description="2-3 sentences: why this area ranks well for this business, using only the facts given")
    risks: str = Field(description="2-3 sentences: the main risks or unknowns, including data limitations")
    suggested_format: str = Field(description="1-2 sentences: a sensible opening format/size, framed as a suggestion to validate")


class Brief(BriefCore):
    model_config = ConfigDict(extra="forbid")
    source: Literal["llm", "template"]


def _dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearby(result: dict, row: dict, radius_m: int = RADIUS_M) -> dict:
    """Competitors and demand drivers within radius of the hex centre, nearest first."""
    places = result.get("places", {"competitors": [], "drivers": []})
    lat, lon = row["lat"], row["lon"]
    comps = sorted(
        ({"name": p[2], "distance_m": round(_dist_m(lat, lon, p[0], p[1]))} for p in places["competitors"]),
        key=lambda x: x["distance_m"],
    )
    drivers = sorted(
        ({"name": p[2], "kind": p[3], "distance_m": round(_dist_m(lat, lon, p[0], p[1]))} for p in places["drivers"]),
        key=lambda x: x["distance_m"],
    )
    return {
        "competitors": [c for c in comps if c["distance_m"] <= radius_m],
        "drivers": [d for d in drivers if d["distance_m"] <= radius_m],
        "radius_m": radius_m,
    }


def _kind_counts(drivers: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in drivers:
        out[d["kind"]] = out.get(d["kind"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:6])


def facts(result: dict, row: dict) -> dict:
    near = nearby(result, row)
    named = lambda items, n: [i["name"] for i in items if i["name"]][:n]  # noqa: E731
    return {
        "business": result["label"],
        "business_summary": result["intent"]["summary"],
        "area": row.get("name") or f"area near {row['lat']:.3f}, {row['lon']:.3f}",
        "city": result["city"]["name"].split(",")[0],
        "rank_in_city": row.get("rank"),
        "score_out_of_100": round(row["score"]),
        "signals_percentile_in_city": {k: round(v * 100) for k, v in row["norm"].items()},  # competition: higher = fewer
        "raw": {
            "built_up_change": None if row["raw"]["growth"] is None else round(row["raw"]["growth"], 3),
            "night_light_trend": None if row["raw"]["activity"] is None else round(row["raw"]["activity"], 2),
            "weighted_demand_drivers_in_area": row["raw"]["demand"],
            "competitors_in_area": row["raw"]["competition"],
            "transit_stops_in_area": row["raw"]["access"],
        },
        "within_1200m": {
            "competitor_count": len(near["competitors"]),
            "nearest_competitors": named(near["competitors"], 4),
            "demand_driver_counts": _kind_counts(near["drivers"]),
            "nearest_named_drivers": named(near["drivers"], 4),
        },
        "data_quality_flags": result["data_quality"]["flags"],
        "osm_coverage_share": result["data_quality"]["osm_coverage"],
    }


SYSTEM_PROMPT = """You write short location briefs for someone deciding where to open a business inside one city.
You are given computed facts about one area. Rules:
- Use ONLY the facts provided. Never invent numbers, place names, rents, footfall or customer behaviour.
- Scores and percentiles are relative to this city; they rank areas, they do not predict success. Say so where relevant.
- Signals are percentiles within the city (0-100). For competition, higher means FEWER competitors.
- A competitor count of 0 may mean a genuine gap or thin OpenStreetMap coverage; say which is uncertain if flags suggest it.
- If data_quality_flags is non-empty or a raw value is null, mention that limitation under risks.
- Plain, concrete language. No marketing tone, no emojis, no markdown."""


def _template(result: dict, row: dict) -> BriefCore:
    f = facts(result, row)
    n = f["within_1200m"]["competitor_count"]
    drivers = f["within_1200m"]["demand_driver_counts"]
    why = build_reason(row["norm"], row["raw"])
    if drivers:
        why += " Nearby demand drivers include " + ", ".join(f"{c} {k}" for k, c in list(drivers.items())[:3]) + "."
    risks = [
        f"{n} competitor{'s' if n != 1 else ''} are mapped within about 1.2 km"
        + (", so the market may already be served." if n >= 5 else ".")
    ]
    if row["norm"].get("competition", 0.5) >= 0.9 and n == 0:
        risks.append("Zero mapped competitors can mean a real gap or incomplete OpenStreetMap data; check on the ground.")
    if result["data_quality"]["flags"]:
        risks.append("Some data was limited for this city, so treat the ranking with extra caution.")
    risks.append("Scores are relative to this city and do not predict revenue.")
    return BriefCore(
        why_here=why,
        risks=" ".join(risks),
        suggested_format="Start with a small, lower-commitment outlet or short lease, and validate demand with a "
        "foot-traffic count before scaling.",
    )


def build_brief(result: dict, row: dict) -> Brief:
    key = f"brief:{result['id']}:{row['hex']}:{settings.llm_model}"
    cached = cache.get(key)
    if cached is not None:
        return Brief.model_validate(cached)

    brief: Brief
    if settings.gemini_api_key:
        try:
            raw = generate_json(
                SYSTEM_PROMPT, "Facts:\n" + json.dumps(facts(result, row), ensure_ascii=False),
                BriefCore.model_json_schema(), max_tokens=1200, temperature=0.3,
            )
            brief = Brief.model_validate({**raw, "source": "llm"})
            cache.put(key, brief.model_dump())  # only cache real LLM output; retry templates next time
            return brief
        except Exception:  # noqa: BLE001 - any LLM failure falls back to the template
            pass
    return Brief(**_template(result, row).model_dump(), source="template")
