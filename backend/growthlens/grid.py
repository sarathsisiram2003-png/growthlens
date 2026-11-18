"""H3 grid helpers."""
import math

import h3
from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry


def _polygons(geom: BaseGeometry) -> list[Polygon]:
    return [geom] if geom.geom_type == "Polygon" else list(geom.geoms)


def city_hexes(boundary: BaseGeometry, resolution: int = 8) -> list[str]:
    """All H3 cells whose centre lies inside the boundary (sorted, unique)."""
    cells: set[str] = set()
    for poly in _polygons(boundary):
        gj = mapping(poly)  # GeoJSON-like, lon/lat order
        outer = [(lat, lon) for lon, lat in gj["coordinates"][0]]
        holes = [[(lat, lon) for lon, lat in ring] for ring in gj["coordinates"][1:]]
        h3poly = h3.LatLngPoly(outer, *holes)
        cells.update(h3.polygon_to_cells(h3poly, resolution))
    return sorted(cells)


def hex_polygon(cell: str) -> Polygon:
    """Hex boundary as a shapely polygon in lon/lat."""
    return Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(cell)])


def hex_centre(cell: str) -> tuple[float, float]:
    """(lat, lon)"""
    return h3.cell_to_latlng(cell)


def point_to_hex(lat: float, lon: float, resolution: int = 8) -> str:
    return h3.latlng_to_cell(lat, lon, resolution)


def is_hex(cell: str, resolution: int | None = None) -> bool:
    """True for a valid H3 cell (optionally of the given resolution)."""
    try:
        return h3.is_valid_cell(cell) and (resolution is None or h3.get_resolution(cell) == resolution)
    except (ValueError, TypeError):
        return False


class AreaTooLarge(ValueError):
    """Raised when a boundary is too big to analyse in detail. The message is shown to the user."""

    def __init__(self, area_km2: float):
        super().__init__(
            f"That area is about {area_km2:,.0f} km², too large to analyse in detail. "
            "Try a specific city, town or district."
        )
        self.area_km2 = area_km2


def estimate_area_km2(boundary: BaseGeometry) -> float:
    """Rough area from degrees (good enough to pick a grid resolution)."""
    minx, miny, maxx, maxy = boundary.bounds
    return boundary.area * (111.32**2) * max(math.cos(math.radians((miny + maxy) / 2)), 0.05)


def choose_resolution(
    boundary: BaseGeometry, preferred: int = 8, min_hexes: int = 40, max_hexes: int = 3500,
    max_area_km2: float = 12000,
) -> tuple[int, list[str]]:
    """Pick an H3 resolution so the grid has between ~min_hexes and max_hexes areas.

    Small towns get a finer grid (up to res 9, ~0.1 km2); big metros a coarser one (down to res 5).
    Areas that would still exceed max_hexes at res 5 are refused before any expensive polygon work.
    """
    area = estimate_area_km2(boundary)
    if area > max_area_km2:  # a province or region, not a city: a coarse grid over it would not be useful
        raise AreaTooLarge(area)

    def est(res: int) -> float:
        return area / h3.average_hexagon_area(res, unit="km^2")

    res = preferred
    while est(res) > max_hexes and res > 5:
        res -= 1
    if est(res) > max_hexes:
        raise AreaTooLarge(area)
    while est(res) < min_hexes and res < 9:
        res += 1

    cells = city_hexes(boundary, res)
    # The estimate can be off for very concave shapes; tighten if the real count is well over budget.
    while len(cells) > max_hexes * 1.25 and res > 5:
        res -= 1
        cells = city_hexes(boundary, res)
    if len(cells) > max_hexes * 1.25:
        raise AreaTooLarge(area)
    if not cells:  # tiny boundary smaller than one cell: use the cell under its centre
        c = boundary.representative_point()
        cells = [h3.latlng_to_cell(c.y, c.x, res)]
    return res, cells
