"""Geocode a city name to a boundary polygon using Nominatim (1 req/s, cached)."""
import math
import threading
import time
from dataclasses import dataclass

import httpx
from shapely import affinity
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry
from tenacity import retry, stop_after_attempt, wait_exponential

from . import cache
from .config import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_last_call = 0.0
_lock = threading.Lock()


def _throttle() -> None:
    """Nominatim policy: max 1 request/second, shared across threads."""
    global _last_call
    with _lock:
        wait = 1.1 - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


class GeocodeError(RuntimeError):
    pass


@dataclass
class City:
    name: str
    display_name: str
    lat: float
    lon: float
    boundary: BaseGeometry  # shapely geometry in lon/lat (EPSG:4326)
    approximate: bool = False  # True when no real boundary exists and we used a circle around the point


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=20), reraise=True)
def _query(name: str, featuretype: str | None = None) -> list[dict]:
    _throttle()
    params = {
        "q": name, "format": "jsonv2", "polygon_geojson": 1, "addressdetails": 1, "extratags": 1, "limit": 8,
        "accept-language": "en",
    }
    if featuretype:
        params["featuretype"] = featuretype  # e.g. "city": only settlements
    r = httpx.get(
        NOMINATIM_URL,
        params=params,
        headers={"User-Agent": settings.http_user_agent},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# Preferred kinds of place, best first.
_PREFERRED = ("city", "town", "municipality", "village", "borough", "city_district", "suburb", "hamlet", "county")
_NEVER = {"country", "continent", "ocean", "sea"}  # never a city, whatever the size
MIN_RADIUS_KM, MAX_RADIUS_KM = 3.0, 16.0


def _kind(res: dict) -> str:
    return res.get("addresstype") or res.get("type") or ""


def _rank(res: dict) -> tuple:
    """Lower is better: preferred kind first, then Nominatim's own importance."""
    kind = _kind(res)
    pref = _PREFERRED.index(kind) if kind in _PREFERRED else len(_PREFERRED)
    return (pref, -float(res.get("importance") or 0))


def _has_polygon(res: dict) -> bool:
    geom = res.get("geojson")
    return bool(geom) and geom.get("type") in ("Polygon", "MultiPolygon")


def approx_radius_km(res: dict) -> float:
    """Radius for a circle standing in for a place with no boundary, from its population when OSM has one.

    ~0.012 * sqrt(population) km: a town of 170k gets ~5 km, a metro of 12M gets the 16 km cap, a village ~3 km.
    """
    try:
        pop = float((res.get("extratags") or {}).get("population", "").replace(",", ""))
    except (TypeError, ValueError):
        pop = 0.0
    if pop > 0:
        return min(MAX_RADIUS_KM, max(MIN_RADIUS_KM, 0.012 * pop**0.5))
    kind = _kind(res)  # no population: a rough guess from the kind of place
    return 8.0 if kind == "city" else 5.0 if kind in ("town", "municipality") else MIN_RADIUS_KM


def _circle(lat: float, lon: float, radius_km: float) -> BaseGeometry:
    """A true circle on the ground (longitude degrees shrink with latitude)."""
    deg = radius_km / 111.32
    return affinity.scale(Point(lon, lat).buffer(deg), xfact=1 / max(math.cos(math.radians(lat)), 0.05), yfact=1.0, origin=(lon, lat))


def pick_place(results: list[dict], name: str) -> City:
    """Choose the best place for a search.

    1. a real boundary of a city/town/etc.;
    2. else a city/town POINT, approximated by a circle sized from its population (flagged approximate);
    3. else the smallest available boundary (choose_resolution refuses it later if it is too large).
    """
    usable = [r for r in results if _kind(r) not in _NEVER]
    if not usable:
        if results:
            raise GeocodeError(f"'{name}' is a country or ocean. Please choose a specific city or town.")
        raise GeocodeError(f"No place found for '{name}'")

    def city(res: dict, boundary: BaseGeometry, approximate: bool = False) -> City:
        return City(name=name, display_name=res["display_name"], lat=float(res["lat"]), lon=float(res["lon"]),
                    boundary=boundary, approximate=approximate)

    preferred = [r for r in usable if _kind(r) in _PREFERRED]
    polygons = sorted((r for r in preferred if _has_polygon(r)), key=_rank)
    if polygons:
        return city(polygons[0], shape(polygons[0]["geojson"]))

    points = sorted((r for r in preferred if not _has_polygon(r)), key=_rank)
    if points:
        res = points[0]
        lat, lon = float(res["lat"]), float(res["lon"])
        return city(res, _circle(lat, lon, approx_radius_km(res)), approximate=True)

    others = [r for r in usable if _has_polygon(r)]
    if others:
        res = min(others, key=lambda r: shape(r["geojson"]).area)
        return city(res, shape(res["geojson"]))

    raise GeocodeError(f"No usable boundary found for '{name}'")


def geocode_city(name: str) -> City:
    key = f"geocode:{name.strip().lower()}"
    results = cache.get(key)
    if results is None:
        try:
            results = _query(name)
            if not any(_kind(r) in _PREFERRED for r in results):
                # Only provinces/regions came back (e.g. "Tokyo"): ask again for settlements specifically
                results = results + [r for r in _query(name, "city") if r not in results]
        except httpx.HTTPError as e:
            raise GeocodeError(f"Geocoding service unavailable: {e}") from e
        cache.put(key, results)
    return pick_place(results, name)


_AREA_KEYS = ("neighbourhood", "suburb", "quarter", "city_district", "residential", "village", "town", "city")


def reverse_area(lat: float, lon: float) -> str | None:
    """Human-readable area name for a point (suburb/neighbourhood level). Never raises."""
    key = f"reverse:en:{lat:.4f},{lon:.4f}"  # "en": names in English where OSM has them (older keys held local-script names)
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    try:
        _throttle()
        r = httpx.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14, "addressdetails": 1, "accept-language": "en"},
            headers={"User-Agent": settings.http_user_agent},
            timeout=20,
        )
        r.raise_for_status()
        addr = r.json().get("address", {})
    except (httpx.HTTPError, ValueError):
        return None  # don't cache failures
    name = next((addr[k] for k in _AREA_KEYS if addr.get(k)), "")
    cache.put(key, name)
    return name or None
