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


# ---- Overpass fetching: failover, stale cache, partial results ----

import httpx  # noqa: E402
import pytest  # noqa: E402

from growthlens import osm as osm_mod  # noqa: E402

BBOX = (12.8, 77.4, 13.2, 77.8)
TAGS = [("amenity", "cafe")]


@pytest.fixture
def fake_env(monkeypatch):
    store: dict = {}
    sleeps: list = []
    monkeypatch.setattr(osm_mod.cache, "get", lambda k, max_age_s=None: store.get(k) if max_age_s is None or store.get(k + ":fresh") else None)

    def put(k, v):
        store[k] = v
        store[k + ":fresh"] = True

    monkeypatch.setattr(osm_mod.cache, "put", put)
    monkeypatch.setattr(osm_mod.time, "sleep", lambda s: sleeps.append(s))
    return store, sleeps


def test_fetch_fails_over_to_next_mirror(fake_env, monkeypatch):
    calls = []

    def post(url, query):
        calls.append(url)
        if len(calls) < 3:
            raise httpx.ReadError("busy")
        return [{"id": 1}]

    monkeypatch.setattr(osm_mod, "_post", post)
    assert osm_mod.fetch_elements(BBOX, TAGS) == [{"id": 1}]
    assert calls == osm_mod.OVERPASS_URLS[:3]


def test_second_call_uses_cache(fake_env, monkeypatch):
    n = []
    monkeypatch.setattr(osm_mod, "_post", lambda u, q: n.append(1) or [{"id": 1}])
    osm_mod.fetch_elements(BBOX, TAGS)
    osm_mod.fetch_elements(BBOX, TAGS)
    assert len(n) == 1


def test_all_mirrors_down_raises_after_bounded_attempts(fake_env, monkeypatch):
    n = []

    def post(u, q):
        n.append(u)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(osm_mod, "_post", post)
    with pytest.raises(osm_mod.OverpassError):
        osm_mod.fetch_elements(BBOX, TAGS)
    assert len(n) == osm_mod.ROUNDS * len(osm_mod.OVERPASS_URLS)


def test_stale_cache_used_when_mirrors_down(fake_env, monkeypatch):
    store, _ = fake_env
    q = osm_mod.build_query(BBOX, TAGS)
    import hashlib

    store["overpass:" + hashlib.sha1(q.encode()).hexdigest()] = [{"id": "old"}]  # present but not marked fresh
    monkeypatch.setattr(osm_mod, "_post", lambda u, q: (_ for _ in ()).throw(httpx.ReadError("down")))
    assert osm_mod.fetch_elements(BBOX, TAGS) == [{"id": "old"}]


def test_deadline_stops_retrying(fake_env, monkeypatch):
    clock = iter([0, 0, 999, 999, 999, 999])  # start=0, first check ok, then past the deadline
    monkeypatch.setattr(osm_mod.time, "time", lambda: next(clock, 999))
    n = []
    monkeypatch.setattr(osm_mod, "_post", lambda u, q: n.append(1) or (_ for _ in ()).throw(httpx.ReadError("x")))
    with pytest.raises(osm_mod.OverpassError):
        osm_mod.fetch_elements(BBOX, TAGS)
    assert len(n) < osm_mod.ROUNDS * len(osm_mod.OVERPASS_URLS)


def test_partial_result_remark_is_rejected(monkeypatch):
    class R:
        def raise_for_status(self): ...
        def json(self): return {"elements": [{"id": 1}], "remark": "runtime error: Query timed out in \"query\" at line 1"}

    monkeypatch.setattr(osm_mod.httpx, "post", lambda *a, **k: R())
    with pytest.raises(osm_mod.OverpassError, match="partial"):
        osm_mod._post("http://x", "q")


def test_osm_metrics_single_request_and_split(fake_env, monkeypatch):
    cell = city_hexes(BLR, 8)[0]
    lat, lon = h3.cell_to_latlng(cell)
    els = [
        {"lat": lat, "lon": lon, "tags": {"amenity": "cafe"}},
        {"lat": lat, "lon": lon, "tags": {"amenity": "college"}},
        {"lat": lat, "lon": lon, "tags": {"highway": "bus_stop"}},
    ]
    calls = []
    monkeypatch.setattr(osm_mod, "_post", lambda u, q: calls.append(q) or els)
    profile = {
        "competitors": [("amenity", "cafe")],
        "demand": {("amenity", "college"): 3.0},
        "access": [("highway", "bus_stop")],
    }
    out = osm_mod.osm_metrics((12.9, 77.5, 13.0, 77.7), [cell], profile, 8)
    assert len(calls) == 1
    assert out["competitors"] == {cell: 1.0} and out["demand"] == {cell: 3.0} and out["access"] == {cell: 1.0}
    assert out["n_competitors"] == 1 and out["coverage"] == 1.0
