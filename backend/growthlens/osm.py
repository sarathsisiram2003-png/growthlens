"""OpenStreetMap counts per H3 hex via the Overpass API (cached, retried, polite)."""
import hashlib
import json
import time
from collections import defaultdict

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from . import cache
from .config import settings
from .grid import point_to_hex

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
CACHE_MAX_AGE = 7 * 24 * 3600
Tag = tuple[str, str | None]


class OverpassError(RuntimeError):
    pass


def _tag_filter(tag: Tag) -> str:
    k, v = tag
    return f'["{k}"]' if v is None else f'["{k}"="{v}"]'


def build_query(bbox: tuple[float, float, float, float], tags: list[Tag]) -> str:
    """bbox = (south, west, north, east)."""
    s, w, n, e = bbox
    parts = "".join(f"nwr{_tag_filter(t)}({s},{w},{n},{e});" for t in tags)
    return f"[out:json][timeout:120];({parts});out center tags;"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=5, max=60), reraise=True)
def _post(url: str, query: str) -> dict:
    r = httpx.post(url, data={"data": query}, headers={"User-Agent": settings.http_user_agent}, timeout=180)
    if r.status_code in (429, 504):
        raise httpx.HTTPError(f"Overpass busy ({r.status_code})")
    r.raise_for_status()
    return r.json()


def fetch_elements(bbox: tuple[float, float, float, float], tags: list[Tag]) -> list[dict]:
    query = build_query(bbox, tags)
    key = "overpass:" + hashlib.sha1(query.encode()).hexdigest()
    cached = cache.get(key, CACHE_MAX_AGE)
    if cached is not None:
        return cached
    last: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            data = _post(url, query)
            elements = data.get("elements", [])
            cache.put(key, elements)
            time.sleep(1)  # be polite between queries
            return elements
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            last = e
    raise OverpassError(f"All Overpass endpoints failed: {last}")


def element_latlon(el: dict) -> tuple[float, float] | None:
    if "lat" in el and "lon" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else None


def matches(el: dict, tag: Tag) -> bool:
    k, v = tag
    val = el.get("tags", {}).get(k)
    return val is not None if v is None else val == v


def count_per_hex(
    elements: list[dict], weights: dict[Tag, float], hexes: set[str], resolution: int
) -> dict[str, float]:
    """Weighted count of elements per hex; each element counted once using the best-matching weight."""
    out: dict[str, float] = defaultdict(float)
    for el in elements:
        pos = element_latlon(el)
        if pos is None:
            continue
        w = max((wt for tag, wt in weights.items() if matches(el, tag)), default=0.0)
        if w <= 0:
            continue
        cell = point_to_hex(pos[0], pos[1], resolution)
        if cell in hexes:
            out[cell] += w
    return dict(out)


def osm_metrics(bbox, hexes: list[str], profile: dict, resolution: int) -> dict:
    """Returns competitor/demand/access counts per hex plus a data-quality summary."""
    hexset = set(hexes)
    comp_w = {t: 1.0 for t in profile["competitors"]}
    acc_w = {t: 1.0 for t in profile["access"]}
    dem_w = profile["demand"]

    comp = fetch_elements(bbox, list(comp_w))
    dem = fetch_elements(bbox, list(dem_w))
    acc = fetch_elements(bbox, list(acc_w))

    competitors = count_per_hex(comp, comp_w, hexset, resolution)
    demand = count_per_hex(dem, dem_w, hexset, resolution)
    access = count_per_hex(acc, acc_w, hexset, resolution)

    # Thin-coverage heuristic: share of hexes with any mapped amenity at all.
    covered = len(set(competitors) | set(demand) | set(access))
    return {
        "competitors": competitors,
        "demand": demand,
        "access": access,
        "coverage": covered / max(len(hexes), 1),
        "n_competitors": len(comp),
    }
