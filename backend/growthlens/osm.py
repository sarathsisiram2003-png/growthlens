"""OpenStreetMap counts per H3 hex via the Overpass API (cached, retried, polite)."""
import hashlib
import json
import math
import time
from collections import defaultdict
from collections.abc import Callable

import httpx

from . import cache
from .config import settings
from .grid import hex_centre, point_to_hex

# Public mirrors, tried in rotation. The main server is often at capacity.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
CACHE_MAX_AGE = 7 * 24 * 3600
REQUEST_TIMEOUT_S = 100  # client-side; the query itself is limited to 90s server-side
DEADLINE_S = 240  # give up (or fall back to stale cache) after this long overall
ROUNDS = 3
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
    return f"[out:json][timeout:90];({parts});out center tags;"


def _post(url: str, query: str) -> list[dict]:
    r = httpx.post(url, data={"data": query}, headers={"User-Agent": settings.http_user_agent}, timeout=REQUEST_TIMEOUT_S)
    r.raise_for_status()
    data = r.json()
    # Overpass can answer 200 with a partial result and a "remark" when it ran out of time or memory.
    remark = str(data.get("remark", ""))
    if "error" in remark.lower() or "timed out" in remark.lower():
        raise OverpassError(f"Overpass returned a partial result: {remark[:120]}")
    return data.get("elements", [])


def fetch_elements(
    bbox: tuple[float, float, float, float], tags: list[Tag], heartbeat: Callable[[], None] | None = None
) -> list[dict]:
    """One Overpass request for all tags, with mirror rotation, a hard deadline and a stale-cache fallback.

    `heartbeat` is called before every attempt; it may raise (e.g. job cancelled / timed out) to stop waiting."""
    query = build_query(bbox, tags)
    key = "overpass:" + hashlib.sha1(query.encode()).hexdigest()
    cached = cache.get(key, CACHE_MAX_AGE)
    if cached is not None:
        return cached

    start = time.time()
    last: Exception | None = None
    for round_ in range(ROUNDS):
        for url in OVERPASS_URLS:
            if time.time() - start > DEADLINE_S:
                break
            if heartbeat:
                heartbeat()
            try:
                elements = _post(url, query)
            except (httpx.HTTPError, ValueError, OverpassError) as e:  # ValueError covers bad JSON
                last = e
                continue
            cache.put(key, elements)
            return elements
        else:
            if round_ < ROUNDS - 1:
                time.sleep(min(5 * 2**round_, 20))  # all mirrors failed this round; back off
            continue
        break  # deadline hit

    stale = cache.get(key)  # any age: old data beats no data
    if stale is not None:
        return stale
    raise OverpassError(f"All Overpass endpoints failed: {last}")


# ---- tiling: big cities are fetched in pieces so no single Overpass query is huge ----
SINGLE_MAX_DEG = 0.35  # cities up to ~39 km across use one request (keeps earlier cache entries valid)
TILE_DEG = 0.2
TILE_PAD = 0.02  # overlap so places near a tile edge are not lost
MAX_FAILED_FRACTION = 0.34  # tolerate a few failed tiles (flagged); more than this and we give up
CONSECUTIVE_FAIL_LIMIT = 2  # two tiles in a row failing means Overpass is down: stop early
TOTAL_DEADLINE_S = 20 * 60

Bbox = tuple[float, float, float, float]


def plan_tiles(bbox: Bbox, centres: list[tuple[float, float]]) -> list[Bbox]:
    """bbox = (south, west, north, east). Returns query boxes covering every area centre."""
    s, w, n, e = bbox
    if (n - s) <= SINGLE_MAX_DEG and (e - w) <= SINGLE_MAX_DEG:
        return [bbox]
    rows = max(1, math.ceil((n - s) / TILE_DEG))
    cols = max(1, math.ceil((e - w) / TILE_DEG))
    used = {
        (min(int((lat - s) / TILE_DEG), rows - 1), min(int((lon - w) / TILE_DEG), cols - 1))
        for lat, lon in centres
    }
    return [
        (
            round(s + r * TILE_DEG - TILE_PAD, 5), round(w + c * TILE_DEG - TILE_PAD, 5),
            round(min(s + (r + 1) * TILE_DEG, n) + TILE_PAD, 5), round(min(w + (c + 1) * TILE_DEG, e) + TILE_PAD, 5),
        )
        for r, c in sorted(used)
    ]


def fetch_tiled(
    bbox: Bbox, tags: list[Tag], centres: list[tuple[float, float]], progress: Callable[[str], None] | None = None
) -> tuple[list[dict], dict]:
    """Fetch all tiles, de-duplicating places that fall in overlapping tiles.

    Returns (elements, {"total": n_tiles, "failed": n_failed}). Raises OverpassError if too many tiles fail.
    """
    tiles = plan_tiles(bbox, centres)
    beat = (lambda: progress("Reading OpenStreetMap")) if progress else None  # keeps cancel/timeout responsive
    found: dict = {}
    failed = consecutive = 0
    last: Exception | None = None
    start = time.time()
    for i, tile in enumerate(tiles):
        if time.time() - start > TOTAL_DEADLINE_S:
            failed += len(tiles) - i
            break
        if progress and len(tiles) > 1:
            progress(f"Reading OpenStreetMap, part {i + 1} of {len(tiles)}")
        try:
            elements = fetch_elements(tile, tags, beat)
        except OverpassError as e:
            failed += 1
            consecutive += 1
            last = e
            if consecutive >= CONSECUTIVE_FAIL_LIMIT:
                failed += len(tiles) - i - 1
                break
            continue
        consecutive = 0
        for el in elements:
            key = (el.get("type"), el["id"]) if "id" in el else id(el)
            found[key] = el
    if failed / len(tiles) > MAX_FAILED_FRACTION:
        raise OverpassError(f"OpenStreetMap data could not be loaded ({failed} of {len(tiles)} parts failed): {last}")
    return list(found.values()), {"total": len(tiles), "failed": failed}


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


MAX_DRIVER_PLACES = 6000


def collect_places(elements: list[dict], comp_w: dict, dem_w: dict, hexset: set[str], resolution: int) -> dict:
    """Compact place lists for the UI's "nearby" panels: [lat, lon, name|None(, label)] per place."""
    competitors: list[list] = []
    drivers: list[list] = []
    for el in elements:
        pos = element_latlon(el)
        if pos is None or point_to_hex(pos[0], pos[1], resolution) not in hexset:
            continue
        tags = el.get("tags", {})
        name = tags.get("name")
        lat, lon = round(pos[0], 5), round(pos[1], 5)
        if any(matches(el, t) for t in comp_w):
            competitors.append([lat, lon, name])
            continue
        for key, value in dem_w:
            if matches(el, (key, value)):
                if len(drivers) < MAX_DRIVER_PLACES:
                    drivers.append([lat, lon, name, (value or tags.get(key, key)).replace("_", " ")])
                break
    return {"competitors": competitors, "drivers": drivers}


def osm_metrics(
    bbox, hexes: list[str], profile: dict, resolution: int, progress: Callable[[str], None] | None = None
) -> dict:
    """Returns competitor/demand/access counts per hex plus a data-quality summary."""
    hexset = set(hexes)
    comp_w = {t: 1.0 for t in profile["competitors"]}
    acc_w = {t: 1.0 for t in profile["access"]}
    dem_w = profile["demand"]

    all_tags = list(dict.fromkeys([*comp_w, *dem_w, *acc_w]))  # unique, order kept
    # One query per tile for all tags; each count below ignores non-matching places.
    elements, tiles = fetch_tiled(bbox, all_tags, [hex_centre(h) for h in hexes], progress)

    competitors = count_per_hex(elements, comp_w, hexset, resolution)
    demand = count_per_hex(elements, dem_w, hexset, resolution)
    access = count_per_hex(elements, acc_w, hexset, resolution)

    # Thin-coverage heuristic: share of hexes with any mapped amenity at all.
    covered = len(set(competitors) | set(demand) | set(access))
    return {
        "places": collect_places(elements, comp_w, dem_w, hexset, resolution),
        "tiles": tiles,
        "competitors": competitors,
        "demand": demand,
        "access": access,
        "coverage": covered / max(len(hexes), 1),
        "n_competitors": sum(1 for el in elements if any(matches(el, t) for t in comp_w)),
    }
