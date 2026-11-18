"""Before/after satellite imagery for one H3 hex: Sentinel-2 annual median composite as a PNG thumbnail.

Served via our API (cached on disk) so the browser never holds Earth Engine URLs/tokens.
Earth Engine is used under non-commercial terms for this portfolio project.
"""
import threading
from datetime import date

import ee
import httpx

from .config import settings
from .grid import hex_polygon
from .satellite import EarthEngineError, init_ee

SIZE_PX = 512
PAD_DEG = 0.004  # ~450 m of context around the hex
S2 = "COPERNICUS/S2_SR_HARMONIZED"
_slots = threading.Semaphore(3)  # protect Earth Engine quota / latency


class ImageryError(RuntimeError):
    pass


def valid_year(year: int) -> bool:
    return 2017 <= year <= date.today().year  # Sentinel-2 has reliable global coverage from 2017


def _cache_path(hex_id: str, year: int):
    d = settings.cache_dir / "imagery"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{hex_id}_{year}.png"


def thumbnail_png(hex_id: str, year: int) -> bytes:
    path = _cache_path(hex_id, year)
    if path.exists():
        return path.read_bytes()
    with _slots:
        if path.exists():  # another request filled it while we waited
            return path.read_bytes()
        try:
            init_ee()
            minx, miny, maxx, maxy = hex_polygon(hex_id).bounds
            region = ee.Geometry.Rectangle([minx - PAD_DEG, miny - PAD_DEG, maxx + PAD_DEG, maxy + PAD_DEG])
            col = (
                ee.ImageCollection(S2)
                .filterBounds(region)
                .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )
            if col.size().getInfo() == 0:
                raise ImageryError(f"No clear satellite scenes for {year}")
            img = col.median().select(["B4", "B3", "B2"])
            url = img.getThumbURL(
                {"region": region, "dimensions": SIZE_PX, "min": 0, "max": 3000, "format": "png"}
            )
            r = httpx.get(url, timeout=90)
            r.raise_for_status()
        except (EarthEngineError, ImageryError):
            raise
        except Exception as e:  # noqa: BLE001 - EE client raises many exception types
            raise ImageryError(f"Satellite imagery unavailable: {e}") from e
    path.write_bytes(r.content)
    return r.content
