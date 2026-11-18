"""H3 grid helpers."""
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
