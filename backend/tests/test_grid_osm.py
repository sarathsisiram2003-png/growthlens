import h3
from shapely.geometry import MultiPolygon, box

from growthlens.grid import city_hexes, hex_polygon, point_to_hex
from growthlens.osm import build_query, count_per_hex, element_latlon, matches

BLR = box(77.58, 12.95, 77.62, 12.99)  # small box in Bengaluru


def test_city_hexes_covers_box_and_valid():
    cells = city_hexes(BLR, 8)
    assert 5 < len(cells) < 100
    assert all(h3.is_valid_cell(c) and h3.get_resolution(c) == 8 for c in cells)
    assert len(cells) == len(set(cells))


def test_multipolygon_supported():
    mp = MultiPolygon([box(77.58, 12.95, 77.60, 12.97), box(77.70, 12.95, 77.72, 12.97)])
    assert len(city_hexes(mp, 8)) > len(city_hexes(box(77.58, 12.95, 77.60, 12.97), 8))


def test_hex_polygon_roundtrip():
    c = city_hexes(BLR, 8)[0]
    p = hex_polygon(c)
    centre = p.centroid
    assert point_to_hex(centre.y, centre.x, 8) == c


def test_build_query_contains_filters_and_bbox():
    q = build_query((12.8, 77.4, 13.2, 77.8), [("amenity", "cafe"), ("office", None)])
    assert 'nwr["amenity"="cafe"](12.8,77.4,13.2,77.8);' in q
    assert 'nwr["office"](12.8,77.4,13.2,77.8);' in q
    assert "out center" in q


def test_element_position_node_and_way():
    assert element_latlon({"lat": 1, "lon": 2}) == (1, 2)
    assert element_latlon({"center": {"lat": 3, "lon": 4}}) == (3, 4)
    assert element_latlon({}) is None


def test_matches_any_value():
    assert matches({"tags": {"office": "it"}}, ("office", None))
    assert not matches({"tags": {"shop": "x"}}, ("office", None))


def test_count_per_hex_weights_and_membership():
    cell = city_hexes(BLR, 8)[0]
    lat, lon = h3.cell_to_latlng(cell)
    els = [
        {"lat": lat, "lon": lon, "tags": {"amenity": "college"}},
        {"lat": lat, "lon": lon, "tags": {"office": "it"}},
        {"lat": lat, "lon": lon, "tags": {"shop": "bakery"}},  # no match -> ignored
        {"lat": 0.0, "lon": 0.0, "tags": {"amenity": "college"}},  # outside hexes -> ignored
    ]
    weights = {("amenity", "college"): 3.0, ("office", None): 1.0}
    out = count_per_hex(els, weights, {cell}, 8)
    assert out == {cell: 4.0}
