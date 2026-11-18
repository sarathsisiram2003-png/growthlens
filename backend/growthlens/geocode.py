"""Geocode a city name to a boundary polygon using Nominatim (1 req/s, cached)."""
import threading
import time
from dataclasses import dataclass

import httpx
from shapely.geometry import shape
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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=20), reraise=True)
def _query(name: str) -> list[dict]:
    _throttle()
    r = httpx.get(
        NOMINATIM_URL,
        params={"q": name, "format": "jsonv2", "polygon_geojson": 1, "limit": 5},
        headers={"User-Agent": settings.http_user_agent},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def geocode_city(name: str) -> City:
    key = f"geocode:{name.strip().lower()}"
    results = cache.get(key)
    if results is None:
        try:
            results = _query(name)
        except httpx.HTTPError as e:
            raise GeocodeError(f"Geocoding service unavailable: {e}") from e
        cache.put(key, results)

    # Prefer a polygonal administrative result over a point/line.
    for res in results:
        geom = res.get("geojson")
        if geom and geom["type"] in ("Polygon", "MultiPolygon"):
            return City(
                name=name,
                display_name=res["display_name"],
                lat=float(res["lat"]),
                lon=float(res["lon"]),
                boundary=shape(geom),
            )
    raise GeocodeError(f"No city boundary found for '{name}'")


_AREA_KEYS = ("neighbourhood", "suburb", "quarter", "city_district", "residential", "village", "town", "city")


def reverse_area(lat: float, lon: float) -> str | None:
    """Human-readable area name for a point (suburb/neighbourhood level). Never raises."""
    key = f"reverse:{lat:.4f},{lon:.4f}"
    cached = cache.get(key)
    if cached is not None:
        return cached or None
    try:
        _throttle()
        r = httpx.get(
            NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 14, "addressdetails": 1},
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
