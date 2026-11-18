"""Geocode a city name to a boundary polygon using Nominatim (1 req/s, cached)."""
import time
from dataclasses import dataclass

import httpx
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from tenacity import retry, stop_after_attempt, wait_exponential

from . import cache
from .config import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_last_call = 0.0


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
    global _last_call
    wait = 1.1 - (time.time() - _last_call)  # Nominatim policy: max 1 req/s
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
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
