"""Satellite metrics per H3 hex from Google Earth Engine.

- Growth:   change in Dynamic World 'built' probability (annual mean), end year minus start year.
- Activity: slope of VIIRS monthly average radiance (nW/cm2/sr per year).
Earth Engine is used under non-commercial terms for this portfolio project.
"""
import hashlib
from collections.abc import Callable

import ee
from tenacity import retry, stop_after_attempt, wait_exponential

from . import cache
from .config import settings
from .grid import hex_polygon

BATCH = 400  # features per reduceRegions call (stays well under EE limits)
DW = "GOOGLE/DYNAMICWORLD/V1"
VIIRS = "NOAA/VIIRS/DNB/MONTHLY_V1/VCMCFG"


class EarthEngineError(RuntimeError):
    pass


def init_ee() -> None:
    """Initialise EE with a service account key if configured, else cached `earthengine authenticate` login."""
    s = settings
    if not s.ee_project:
        raise EarthEngineError("EE_PROJECT is not set in backend/.env")
    try:
        if s.ee_service_account_key and s.ee_service_account_email:
            creds = ee.ServiceAccountCredentials(s.ee_service_account_email, s.ee_service_account_key)
            ee.Initialize(creds, project=s.ee_project)
        else:
            ee.Initialize(project=s.ee_project)
    except Exception as e:  # noqa: BLE001 - surface any auth/project error clearly
        raise EarthEngineError(
            f"Earth Engine init failed ({e}). Run `earthengine authenticate` or set service-account vars."
        ) from e


def _hex_collection(cells: list[str]) -> ee.FeatureCollection:
    feats = []
    for c in cells:
        coords = [list(xy) for xy in hex_polygon(c).exterior.coords]
        feats.append(ee.Feature(ee.Geometry.Polygon([coords]), {"hex": c}))
    return ee.FeatureCollection(feats)


def _built_mean(year: int, region: ee.Geometry) -> ee.Image:
    return (
        ee.ImageCollection(DW)
        .filterBounds(region)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select("built")
        .mean()
    )


def growth_image(start_year: int, end_year: int, region: ee.Geometry) -> ee.Image:
    return _built_mean(end_year, region).subtract(_built_mean(start_year, region)).rename("growth")


def viirs_trend_image(start: str, end: str, region: ee.Geometry) -> ee.Image:
    def add_t(img: ee.Image) -> ee.Image:
        years = ee.Date(img.get("system:time_start")).difference(ee.Date(start), "year")
        return ee.Image.constant(years).float().rename("t").addBands(img.select("avg_rad"))

    col = ee.ImageCollection(VIIRS).filterBounds(region).filterDate(start, end).map(add_t)
    return col.select(["t", "avg_rad"]).reduce(ee.Reducer.linearFit()).select("scale").rename("activity")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=3, max=30), reraise=True)
def _reduce(image: ee.Image, cells: list[str], scale: int, band: str) -> dict[str, float | None]:
    fc = _hex_collection(cells)
    res = image.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=scale, tileScale=4).getInfo()
    return {f["properties"]["hex"]: f["properties"].get("mean") for f in res["features"]}


def _batched(
    image_fn: Callable[[ee.Geometry], ee.Image], cells: list[str], scale: int, band: str, bbox, tag: str,
    progress: Callable[[str], None] | None,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    region = ee.Geometry.Rectangle([bbox[1], bbox[0], bbox[3], bbox[2]])
    image = image_fn(region)
    for i in range(0, len(cells), BATCH):
        chunk = cells[i : i + BATCH]
        key = f"ee:{tag}:" + hashlib.sha1(",".join(chunk).encode()).hexdigest()
        part = cache.get(key)
        if part is None:
            try:
                part = _reduce(image, chunk, scale, band)
            except Exception as e:  # noqa: BLE001 - degrade gracefully: missing -> neutral score
                if progress:
                    progress(f"  ! {tag} batch {i // BATCH + 1} failed ({e}); marking missing")
                part = {c: None for c in chunk}
            else:
                cache.put(key, part)
        out.update(part)
        if progress:
            progress(f"  {tag}: {min(i + BATCH, len(cells))}/{len(cells)} hexes")
    return out


def satellite_metrics(cells: list[str], bbox, progress: Callable[[str], None] | None = None) -> dict:
    """bbox = (south, west, north, east). Returns {'growth': {hex: v}, 'activity': {hex: v}}."""
    init_ee()
    s = settings
    tag_g = f"growth{s.growth_start_year}-{s.growth_end_year}"
    tag_a = f"viirs{s.viirs_start}-{s.viirs_end}"
    growth = _batched(
        lambda r: growth_image(s.growth_start_year, s.growth_end_year, r), cells, 10, "growth", bbox, tag_g, progress
    )
    activity = _batched(
        lambda r: viirs_trend_image(s.viirs_start, s.viirs_end, r), cells, 500, "activity", bbox, tag_a, progress
    )
    return {"growth": growth, "activity": activity}
