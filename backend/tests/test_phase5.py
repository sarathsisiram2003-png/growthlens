import json
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, box

from growthlens import api as api_mod
from growthlens import geocode as geocode_mod
from growthlens import jobs as jobs_mod
from growthlens import osm as osm_mod
from growthlens import pipeline as pipeline_mod
from growthlens import quality, ratelimit
from growthlens.config import settings
from growthlens.geocode import City, GeocodeError, pick_place
from growthlens.grid import AreaTooLarge, choose_resolution
from growthlens.intent import intent_from_preset
from growthlens.pipeline import SCHEMA_VERSION
from growthlens.satellite import EarthEngineError

client = TestClient(app=api_mod.app)


# ======================================================================= grid resolution

def test_small_town_gets_a_finer_grid():
    res, cells = choose_resolution(box(77.50, 13.00, 77.53, 13.03))  # ~3 km square
    assert res == 9 and len(cells) >= 40


def test_mid_size_city_keeps_default_resolution():
    res, cells = choose_resolution(box(77.46, 12.83, 77.78, 13.14))
    assert res == 8 and 800 < len(cells) < 2000


def test_big_metro_gets_a_coarser_grid_within_budget():
    res, cells = choose_resolution(box(-0.5, 51.28, 0.3, 51.7), max_hexes=1000)
    assert res < 8 and len(cells) <= 1250


def test_huge_area_is_refused_with_a_friendly_message():
    with pytest.raises(AreaTooLarge, match="too large"):
        choose_resolution(box(50, 20, 60, 30))


def test_province_sized_area_is_refused_even_if_a_coarse_grid_would_fit():
    big = box(138, 34, 140.2, 36)  # ~45,000 km2: fits in <3500 cells at res 6, but is not a city
    with pytest.raises(AreaTooLarge):
        choose_resolution(big)
    assert choose_resolution(big, max_area_km2=1e6)[0] <= 6  # the cap, not the cell budget, is what refused it


def test_tiny_boundary_still_yields_a_cell():
    res, cells = choose_resolution(Point(77.5, 13.0).buffer(0.0004))
    assert len(cells) >= 1


# ======================================================================= choosing the place

def poly(lon, lat, size=0.1):
    b = box(lon, lat, lon + size, lat + size)
    return {"type": "Polygon", "coordinates": [list(map(list, b.exterior.coords))]}


def place(kind, name, importance=0.5, geojson=None, lat=13.0, lon=77.5):
    return {"addresstype": kind, "display_name": name, "importance": importance, "lat": str(lat), "lon": str(lon),
            "geojson": geojson or {"type": "Point", "coordinates": [lon, lat]}}


def test_prefers_a_city_polygon_over_a_county():
    got = pick_place([place("county", "Pune District", 0.9, poly(73, 18)), place("city", "Pune", 0.6, poly(73.8, 18.5))], "Pune")
    assert got.display_name == "Pune" and not got.approximate


def test_importance_breaks_ties_between_same_kind():
    got = pick_place([place("city", "Springfield A", 0.2, poly(1, 1)), place("city", "Springfield B", 0.7, poly(2, 2))], "Springfield")
    assert got.display_name == "Springfield B"


def test_countries_are_refused():
    with pytest.raises(GeocodeError, match="country or ocean"):
        pick_place([place("country", "India", 1.0, poly(70, 10))], "India")


def test_a_big_polygon_is_a_last_resort_and_a_city_beats_it():
    # Tokyo-like: only a province boundary exists. It is returned (and refused later if too large)...
    got = pick_place([place("province", "Tokyo Metropolis", 0.8, poly(139, 35))], "Tokyo")
    assert got.display_name == "Tokyo Metropolis" and not got.approximate
    # ...but a real city polygon always wins over it
    got = pick_place([place("state", "Delhi state", 0.9, poly(77, 28)), place("city", "Delhi", 0.8, poly(77.1, 28.6))], "Delhi")
    assert got.display_name == "Delhi"


def test_city_point_beats_a_province_polygon_of_the_wrong_scale():
    # Lagos/Dubai-like: a place=city node plus a huge state polygon -> a circle around the city
    got = pick_place([place("state", "Lagos State", 0.55, poly(3, 6, 0.5)), place("city", "Lagos", 0.65, None, lat=6.5, lon=3.4)], "Lagos")
    assert got.approximate and got.display_name == "Lagos"


def test_smallest_polygon_is_used_when_there_is_no_city_kind():
    got = pick_place([place("state", "Big", 0.9, poly(0, 0, 5)), place("administrative", "Smaller", 0.5, poly(0, 0, 1))], "X")
    assert got.display_name == "Smaller"


def test_point_only_place_gets_an_approximate_boundary():
    got = pick_place([place("village", "Tiny Village", 0.1, None, lat=12.5, lon=75.5)], "Tiny Village")
    assert got.approximate and got.boundary.contains(Point(75.5, 12.5))


def test_circle_size_follows_population():
    def with_pop(pop, kind="city"):
        r = place(kind, "P", 0.5, None)
        r["extratags"] = {"population": pop} if pop else {}
        return r

    assert geocode_mod.approx_radius_km(with_pop("12442373")) == geocode_mod.MAX_RADIUS_KM  # metro: capped
    assert 4 < geocode_mod.approx_radius_km(with_pop("170000")) < 6  # town
    assert geocode_mod.approx_radius_km(with_pop("2,000", "village")) == geocode_mod.MIN_RADIUS_KM
    assert geocode_mod.approx_radius_km(with_pop(None)) == 8.0  # city, no population
    assert geocode_mod.approx_radius_km(with_pop("not-a-number", "town")) == 5.0


def test_circle_is_round_on_the_ground_at_high_latitude():
    from growthlens.grid import estimate_area_km2

    c = geocode_mod._circle(60.0, 10.0, 10.0)
    import math

    assert estimate_area_km2(c) == pytest.approx(math.pi * 100, rel=0.03)  # ~314 km2 regardless of latitude


def test_no_results_is_a_clear_error():
    with pytest.raises(GeocodeError, match="No place found"):
        pick_place([], "Nowhereville")


# ======================================================================= OSM tiling

def test_small_city_uses_a_single_query():
    bbox = (12.83, 77.46, 13.14, 77.78)
    assert osm_mod.plan_tiles(bbox, [(13.0, 77.6)]) == [bbox]


def test_large_city_is_split_into_tiles_that_cover_every_area():
    bbox = (51.2, -0.6, 51.7, 0.4)
    centres = [(51.25, -0.55), (51.5, -0.1), (51.68, 0.35)]
    tiles = osm_mod.plan_tiles(bbox, centres)
    assert 1 < len(tiles) < 15
    for lat, lon in centres:
        assert any(s <= lat <= n and w <= lon <= e for s, w, n, e in tiles)


def test_empty_tiles_are_skipped():
    bbox = (51.2, -0.6, 51.7, 0.4)
    all_tiles = osm_mod.plan_tiles(bbox, [(51.2 + i * 0.05, -0.6 + j * 0.05) for i in range(10) for j in range(20)])
    few = osm_mod.plan_tiles(bbox, [(51.25, -0.55)])
    assert len(few) == 1 < len(all_tiles)


@pytest.fixture
def tiled(monkeypatch):
    monkeypatch.setattr(osm_mod, "plan_tiles", lambda bbox, centres: [(i, i, i + 1, i + 1) for i in range(4)])


def test_tiles_are_merged_and_overlap_is_deduplicated(tiled, monkeypatch):
    data = {0: [{"type": "node", "id": 1}, {"type": "node", "id": 2}], 1: [{"type": "node", "id": 2}, {"type": "node", "id": 3}],
            2: [], 3: [{"type": "way", "id": 1}]}  # way 1 and node 1 are different objects
    monkeypatch.setattr(osm_mod, "fetch_elements", lambda tile, tags, beat=None: data[int(tile[0])])
    els, stats = osm_mod.fetch_tiled((0, 0, 4, 4), [("a", None)], [])
    assert len(els) == 4 and stats == {"total": 4, "failed": 0}


def test_one_failed_tile_is_tolerated_and_reported(tiled, monkeypatch):
    def fetch(tile, tags, beat=None):
        if int(tile[0]) == 1:
            raise osm_mod.OverpassError("busy")
        return [{"type": "node", "id": int(tile[0])}]

    monkeypatch.setattr(osm_mod, "fetch_elements", fetch)
    els, stats = osm_mod.fetch_tiled((0, 0, 4, 4), [("a", None)], [])
    assert stats == {"total": 4, "failed": 1} and len(els) == 3


def test_too_many_failures_raise(tiled, monkeypatch):
    def fetch(tile, tags, beat=None):
        if int(tile[0]) in (0, 2):  # alternate so the early-stop rule does not trigger first
            raise osm_mod.OverpassError("busy")
        return []

    monkeypatch.setattr(osm_mod, "fetch_elements", fetch)
    with pytest.raises(osm_mod.OverpassError, match="2 of 4 parts failed"):
        osm_mod.fetch_tiled((0, 0, 4, 4), [("a", None)], [])


def test_two_failures_in_a_row_stop_early(tiled, monkeypatch):
    calls = []

    def fetch(tile, tags, beat=None):
        calls.append(tile)
        raise osm_mod.OverpassError("down")

    monkeypatch.setattr(osm_mod, "fetch_elements", fetch)
    with pytest.raises(osm_mod.OverpassError):
        osm_mod.fetch_tiled((0, 0, 4, 4), [("a", None)], [])
    assert len(calls) == osm_mod.CONSECUTIVE_FAIL_LIMIT  # did not grind through every tile


def test_single_tile_failure_is_fatal(monkeypatch):
    monkeypatch.setattr(osm_mod, "plan_tiles", lambda b, c: [b])
    monkeypatch.setattr(osm_mod, "fetch_elements", lambda t, tags, beat=None: (_ for _ in ()).throw(osm_mod.OverpassError("x")))
    with pytest.raises(osm_mod.OverpassError):
        osm_mod.fetch_tiled((0, 0, 1, 1), [("a", None)], [])


def test_progress_is_reported_per_tile(tiled, monkeypatch):
    monkeypatch.setattr(osm_mod, "fetch_elements", lambda t, tags, beat=None: [])
    msgs = []
    osm_mod.fetch_tiled((0, 0, 4, 4), [("a", None)], [], msgs.append)
    assert msgs == [f"Reading OpenStreetMap, part {i} of 4" for i in range(1, 5)]


# ======================================================================= data quality

def dq(**over):
    base = dict(n_areas=900, resolution=8, osm_coverage=0.8, n_competitors=500, n_demand_places=900)
    return quality.assess(**{**base, **over})


def test_healthy_data_is_good():
    r = dq()
    assert r["level"] == "good" and r["flags"] == []


def test_thin_coverage_is_caution_and_very_thin_is_limited():
    assert dq(osm_coverage=0.2)["level"] == "caution" and "thin_osm_coverage" in dq(osm_coverage=0.2)["flags"]
    assert dq(osm_coverage=0.05)["level"] == "limited" and "very_thin_osm" in dq(osm_coverage=0.05)["flags"]


def test_no_competitors_is_limited_and_few_is_caution():
    assert dq(n_competitors=0)["level"] == "limited"
    r = dq(n_competitors=4)
    assert r["level"] == "caution" and r["flags"] == ["few_competitors"]


def test_grid_adjustments_are_information_only():
    assert dq(resolution=9)["level"] == "good" and dq(resolution=9)["flags"] == ["finer_grid"]
    assert dq(resolution=6)["flags"] == ["coarser_grid"] and dq(resolution=6)["level"] == "good"


def test_partial_osm_and_approximate_boundary_are_cautions():
    r = dq(tiles_failed=1, tiles_total=4, approximate_boundary=True)
    assert set(r["flags"]) == {"osm_partial", "approximate_boundary"} and r["level"] == "caution"


def test_three_cautions_add_up_to_limited():
    r = dq(osm_coverage=0.2, tiles_failed=1, tiles_total=4, extra_flags=["satellite_unavailable"])
    assert len([f for f in r["flags"] if quality.SEVERITY[f] == "caution"]) == 3 and r["level"] == "limited"


def test_severities_are_sent_for_every_flag():
    r = dq(osm_coverage=0.05, resolution=9)
    assert r["severities"] == {"very_thin_osm": "limited", "finer_grid": "info"}


def test_few_areas_flag():
    assert "few_areas" in dq(n_areas=12)["flags"]


def test_add_flag_recomputes_level_and_is_idempotent():
    r = dq()
    quality.add_flag(r, "intent_fallback_preset")
    quality.add_flag(r, "intent_fallback_preset")
    assert r["flags"] == ["intent_fallback_preset"] and r["level"] == "caution"
    assert r["severities"] == {"intent_fallback_preset": "caution"}
    assert quality.level_of(["some_future_flag"]) == "caution"  # unknown flags are cautious, not ignored


# ======================================================================= pipeline (all services mocked)

@pytest.fixture
def mocked_pipeline(monkeypatch):
    boundary = box(77.50, 13.00, 77.53, 13.03)
    monkeypatch.setattr(pipeline_mod, "geocode_city", lambda name: City(name, f"{name}, India", 13.015, 77.515, boundary))
    monkeypatch.setattr(pipeline_mod, "reverse_area", lambda lat, lon: "Testpura")

    def fake_osm(bbox, cells, profile, res, progress=None):
        return {
            "competitors": {c: 1.0 for c in cells[:5]}, "demand": {c: 2.0 for c in cells[:50]}, "access": {},
            "coverage": 0.6, "n_competitors": 5, "places": {"competitors": [], "drivers": []},
            "tiles": {"total": 1, "failed": 0},
        }

    monkeypatch.setattr(pipeline_mod, "osm_metrics", fake_osm)
    return monkeypatch


def test_pipeline_adapts_grid_and_reports_quality(mocked_pipeline):
    mocked_pipeline.setattr(pipeline_mod, "satellite_metrics", lambda cells, bbox, progress=None: {"growth": {c: 0.1 for c in cells}, "activity": {c: 1.0 for c in cells}})
    r = pipeline_mod.run_pipeline("Smalltown", intent_from_preset("cafe"))
    assert r["schema"] == SCHEMA_VERSION and r["h3_resolution"] == 9
    assert r["data_quality"]["level"] == "caution"  # few competitors (5)
    assert set(r["data_quality"]["flags"]) == {"few_competitors", "finer_grid"}
    assert len(r["top10"]) == 10 and all(h["name"] == "Testpura" for h in r["hexes"] if h["rank"])


def test_pipeline_survives_earth_engine_failure(mocked_pipeline):
    def boom(cells, bbox, progress=None):
        raise EarthEngineError("not configured")

    mocked_pipeline.setattr(pipeline_mod, "satellite_metrics", boom)
    r = pipeline_mod.run_pipeline("Smalltown", intent_from_preset("cafe"))
    assert "satellite_unavailable" in r["data_quality"]["flags"] and len(r["top10"]) == 10


def test_pipeline_flags_an_approximate_boundary(mocked_pipeline):
    mocked_pipeline.setattr(pipeline_mod, "geocode_city", lambda n: City(n, n, 12.5, 75.5, Point(75.5, 12.5).buffer(0.035), approximate=True))
    mocked_pipeline.setattr(pipeline_mod, "satellite_metrics", lambda cells, bbox, progress=None: {"growth": {}, "activity": {}})
    r = pipeline_mod.run_pipeline("Village", intent_from_preset("cafe"), skip_satellite=True)
    assert "approximate_boundary" in r["data_quality"]["flags"]


def test_too_large_area_fails_with_the_friendly_message(mocked_pipeline):
    mocked_pipeline.setattr(pipeline_mod, "geocode_city", lambda n: City(n, n, 25, 55, box(50, 20, 60, 30)))
    with pytest.raises(AreaTooLarge):
        pipeline_mod.run_pipeline("Huge", intent_from_preset("cafe"))
    assert "too large" in jobs_mod._friendly(AreaTooLarge(1e6))


# ======================================================================= jobs: persistence, resume, cancel

@pytest.fixture
def jobenv(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(jobs_mod, "parse_intent", lambda q: (intent_from_preset("cafe"), None))
    gate = threading.Event()
    gate.set()  # open by default; tests close it to hold workers busy
    ran: list[str] = []

    def fake_run(city, intent, progress=None, **_):
        ran.append(city)
        for step in ("map", "satellite", "competitors", "scoring", "briefs"):
            progress(step, f"doing {step}", {"boundary": {"type": "Polygon", "coordinates": []}, "center": [1, 2]} if step == "map" else None)
            gate.wait(5)
        return {"schema": SCHEMA_VERSION, "city": {"name": city, "lat": 1, "lon": 2, "boundary": {}}, "category": "cafe",
                "data_quality": {"flags": [], "level": "good"}, "hexes": []}

    monkeypatch.setattr(jobs_mod, "run_pipeline", fake_run)
    with jobs_mod._lock:
        jobs_mod._jobs.clear(); jobs_mod._by_key.clear(); jobs_mod._waiting.clear()
    return gate, ran


def wait_for(job_id, states, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        st = client.get(f"/jobs/{job_id}").json()
        if st["status"] in states:
            return st
        time.sleep(0.02)
    raise AssertionError(f"job stuck in {client.get(f'/jobs/{job_id}').json()['status']}")


def test_finished_job_is_readable_after_a_restart(jobenv):
    jid = client.post("/jobs", json={"city": "Persistville", "query": "cafe"}).json()["id"]
    wait_for(jid, {"done"})
    with jobs_mod._lock:  # simulate a restart: memory is gone, SQLite remains
        jobs_mod._jobs.clear(); jobs_mod._by_key.clear()
    st = client.get(f"/jobs/{jid}").json()
    assert st["status"] == "done" and st["result_id"] and st["meta"]["center"] == [1, 2]
    assert client.get(f"/jobs/{jid}/result").status_code == 200


def test_interrupted_job_is_resumed_on_startup(jobenv):
    gate, ran = jobenv
    job = jobs_mod.Job(id="resume000001", city="Resumetown", query="cafe", key="resumetown|cafe", status="running")
    jobs_mod._save(job)  # as if the server died mid-run
    assert jobs_mod.recover() == 1
    wait_for("resume000001", {"done"})
    assert ran == ["Resumetown"]


def test_expired_jobs_are_pruned_but_active_ones_kept(jobenv, monkeypatch):
    jobs_mod._save(jobs_mod.Job(id="old000000001", city="A", query="q", key="a|q", status="done"))
    jobs_mod._save(jobs_mod.Job(id="old000000002", city="B", query="q", key="b|q", status="running"))
    monkeypatch.setattr(settings, "job_retention_days", 0)
    time.sleep(0.01)
    assert jobs_mod.prune() == 1
    assert jobs_mod._load("old000000001") is None and jobs_mod._load("old000000002") is not None


def test_queued_job_reports_position_and_can_be_cancelled(jobenv, monkeypatch):
    gate, ran = jobenv
    gate.clear()  # hold workers
    first = [client.post("/jobs", json={"city": f"Busy{i}", "query": "cafe"}).json()["id"] for i in range(settings.job_workers)]
    for jid in first:
        wait_for(jid, {"running"})
    queued = client.post("/jobs", json={"city": "Patient", "query": "cafe"}).json()
    assert queued["status"] == "queued" and queued["queue_position"] == 1
    cancelled = client.post(f"/jobs/{queued['id']}/cancel").json()
    assert cancelled["status"] == "cancelled" and cancelled["queue_position"] is None
    gate.set()
    for jid in first:
        wait_for(jid, {"done"})
    assert "Patient" not in ran  # never started


def test_running_job_can_be_cancelled(jobenv):
    gate, ran = jobenv
    gate.clear()
    jid = client.post("/jobs", json={"city": "Walkaway", "query": "cafe"}).json()["id"]
    wait_for(jid, {"running"})
    assert client.post(f"/jobs/{jid}/cancel").json()["status"] == "cancelled"  # reported immediately
    gate.set()
    time.sleep(0.3)  # the worker notices and stops; it must not flip back to done
    assert client.get(f"/jobs/{jid}").json()["status"] == "cancelled"
    assert not list(settings.output_dir.glob("walkaway_cafe_*.json"))  # nothing saved for an abandoned search


def test_shared_job_is_only_cancelled_when_nobody_wants_it(jobenv):
    gate, _ = jobenv
    gate.clear()
    a = client.post("/jobs", json={"city": "Shared", "query": "cafe"}).json()["id"]
    b = client.post("/jobs", json={"city": "Shared", "query": "cafe"}).json()["id"]
    assert a == b
    client.post(f"/jobs/{a}/cancel")  # first viewer leaves
    assert client.get(f"/jobs/{a}").json()["status"] in ("queued", "running")
    client.post(f"/jobs/{a}/cancel")  # second viewer leaves
    gate.set()
    assert wait_for(a, {"cancelled", "done"})["status"] == "cancelled"


def test_cancel_of_unknown_or_finished_job(jobenv):
    assert client.post("/jobs/nope/cancel").status_code == 404
    jid = client.post("/jobs", json={"city": "Doneville", "query": "cafe"}).json()["id"]
    wait_for(jid, {"done"})
    assert client.post(f"/jobs/{jid}/cancel").json()["status"] == "done"  # unchanged


def test_job_timeout_gives_a_friendly_error(jobenv, monkeypatch):
    monkeypatch.setattr(settings, "job_timeout_s", -1)  # already past the deadline at the first check
    jid = client.post("/jobs", json={"city": "Slowville", "query": "cafe"}).json()["id"]
    st = wait_for(jid, {"error"})
    assert "took too long" in st["error"]


def test_stale_cached_result_is_recomputed(jobenv, monkeypatch):
    _, ran = jobenv
    wait_for(client.post("/jobs", json={"city": "Agetown", "query": "cafe"}).json()["id"], {"done"})
    path = next(settings.output_dir.glob("agetown_cafe_*.json"))
    old = time.time() - (settings.result_max_age_days + 1) * 86400
    os.utime(path, (old, old))
    wait_for(client.post("/jobs", json={"city": "Agetown", "query": "cafe"}).json()["id"], {"done"})
    assert ran.count("Agetown") == 2


def test_refresh_bypasses_the_cache(jobenv):
    _, ran = jobenv
    wait_for(client.post("/jobs", json={"city": "Freshville", "query": "cafe"}).json()["id"], {"done"})
    wait_for(client.post("/jobs", json={"city": "Freshville", "query": "cafe"}).json()["id"], {"done"})
    assert ran.count("Freshville") == 1
    wait_for(client.post("/jobs", json={"city": "Freshville", "query": "cafe", "refresh": True}).json()["id"], {"done"})
    assert ran.count("Freshville") == 2


def test_missing_result_file_gives_a_clean_404(jobenv):
    jid = client.post("/jobs", json={"city": "Gonetown", "query": "cafe"}).json()["id"]
    wait_for(jid, {"done"})
    jobs_mod.get_job(jid).result_path.unlink()
    r = client.get(f"/jobs/{jid}/result")
    assert r.status_code == 404 and "expired" in r.json()["detail"]


def test_job_failures_are_friendly(jobenv):
    assert "OpenStreetMap is busy" in jobs_mod._friendly(osm_mod.OverpassError("x"))
    assert "couldn't find" in jobs_mod._friendly(GeocodeError("none"))
    assert "Something went wrong" in jobs_mod._friendly(RuntimeError("secret"))


# ======================================================================= rate limiting

@pytest.fixture
def limited(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setitem(ratelimit.LIMITS, "area_name", (3, 600))
    monkeypatch.setattr(api_mod, "reverse_area", lambda lat, lon: "X")
    ratelimit.reset()


def test_requests_over_the_limit_get_429_with_retry_after(limited):
    for _ in range(3):
        assert client.get("/area-name?lat=1&lon=1").status_code == 200
    r = client.get("/area-name?lat=1&lon=1")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0 and "Too many requests" in r.json()["detail"]


def test_limit_window_expires():
    assert ratelimit.check("area_name", "c1", now=1000) == 0
    for t in range(1001, 1003):
        ratelimit.check("area_name", "c1", now=t)
    for t in range(1003, 1003 + 117):  # fill the rest of the 120-request window
        ratelimit.check("area_name", "c1", now=t)
    assert ratelimit.check("area_name", "c1", now=1200) > 0  # blocked inside the window
    assert ratelimit.check("area_name", "c1", now=1000 + 601) == 0  # window slid past the first hit


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(limited, monkeypatch):
    for i in range(3):
        client.get("/area-name?lat=1&lon=1", headers={"X-Forwarded-For": f"9.9.9.{i}"})
    assert client.get("/area-name?lat=1&lon=1", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 429  # spoofing doesn't help
    monkeypatch.setattr(settings, "trust_proxy", True)
    assert client.get("/area-name?lat=1&lon=1", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 200  # distinct client


def test_limits_are_per_bucket(limited):
    for _ in range(3):
        client.get("/area-name?lat=1&lon=1")
    assert client.get("/health").status_code == 200  # unrelated endpoint unaffected


# ======================================================================= cancel/timeout can interrupt an Overpass wait

def test_heartbeat_can_stop_a_long_overpass_wait(monkeypatch):
    class Stop(Exception):
        pass

    attempts = []

    def post(url, query):
        attempts.append(url)
        raise osm_mod.httpx.ReadError("slow")

    def beat():
        if len(attempts) >= 2:
            raise Stop()

    monkeypatch.setattr(osm_mod, "_post", post)
    monkeypatch.setattr(osm_mod.cache, "get", lambda k, max_age_s=None: None)
    monkeypatch.setattr(osm_mod.cache, "put", lambda k, v: None)
    monkeypatch.setattr(osm_mod.time, "sleep", lambda s: None)
    with pytest.raises(Stop):
        osm_mod.fetch_elements((0, 0, 1, 1), [("a", None)], beat)
    assert len(attempts) == 2  # stopped after two mirrors, not after all of them in all rounds


def test_cancelling_a_job_interrupts_the_osm_step(jobenv, monkeypatch):
    """End to end through the job layer: the progress callback raises JobCancelled from inside the OSM wait."""
    gate, _ = jobenv
    started = threading.Event()

    def pipeline_stuck_in_osm(city, intent, progress=None, **_):
        started.set()
        for _ in range(500):  # like fetch_elements retrying mirrors: the callback is the only way out
            progress("competitors", "Reading OpenStreetMap", None)
            time.sleep(0.01)
        raise AssertionError("was not interrupted")

    monkeypatch.setattr(jobs_mod, "run_pipeline", pipeline_stuck_in_osm)
    jid = client.post("/jobs", json={"city": "Stuckville", "query": "cafe"}).json()["id"]
    assert started.wait(3)
    client.post(f"/jobs/{jid}/cancel")
    assert wait_for(jid, {"cancelled", "error"})["status"] == "cancelled"


# ======================================================================= geocoder asks again when only regions come back

def test_geocoder_retries_with_a_city_filter_when_only_provinces_are_returned(monkeypatch):
    calls = []
    province = place("province", "Tokyo Metropolis", 0.8, poly(139, 35))
    city_node = place("city", "Shinjuku", 0.5, None, lat=35.69, lon=139.7)

    def fake_query(name, featuretype=None):
        calls.append(featuretype)
        return [city_node] if featuretype == "city" else [province]

    monkeypatch.setattr(geocode_mod, "_query", fake_query)
    store = {}
    monkeypatch.setattr(geocode_mod.cache, "get", lambda k, max_age_s=None: store.get(k))
    monkeypatch.setattr(geocode_mod.cache, "put", lambda k, v: store.__setitem__(k, v))
    got = geocode_mod.geocode_city("Tokyo")
    assert calls == [None, "city"] and got.display_name == "Shinjuku" and got.approximate


def test_geocoder_does_not_retry_when_a_city_is_already_found(monkeypatch):
    calls = []
    monkeypatch.setattr(geocode_mod, "_query", lambda name, featuretype=None: calls.append(featuretype) or [place("city", "Pune", 0.6, poly(73, 18))])
    monkeypatch.setattr(geocode_mod.cache, "get", lambda k, max_age_s=None: None)
    monkeypatch.setattr(geocode_mod.cache, "put", lambda k, v: None)
    geocode_mod.geocode_city("Pune")
    assert calls == [None]


# ======================================================================= names are requested in English

def test_nominatim_calls_ask_for_english_names(monkeypatch):
    seen = []

    class R:
        def raise_for_status(self): ...
        def json(self): return {"address": {"suburb": "Downtown Dubai"}}

    monkeypatch.setattr(geocode_mod.httpx, "get", lambda url, params=None, **k: seen.append(params) or R())
    monkeypatch.setattr(geocode_mod, "_throttle", lambda: None)
    store = {}
    monkeypatch.setattr(geocode_mod.cache, "get", lambda k, max_age_s=None: store.get(k))
    monkeypatch.setattr(geocode_mod.cache, "put", lambda k, v: store.__setitem__(k, v))
    assert geocode_mod.reverse_area(25.2, 55.27) == "Downtown Dubai"
    geocode_mod._query("Dubai")
    assert all(p["accept-language"] == "en" for p in seen) and len(seen) == 2
    assert any(k.startswith("reverse:en:") for k in store)  # separate cache namespace from older local-script names


# ======================================================================= weak growth signal flag

def test_negative_citywide_growth_is_flagged_as_unreliable():
    r = dq(mean_growth=-0.025)
    assert "weak_growth_signal" in r["flags"] and r["level"] == "caution"
    assert r["severities"]["weak_growth_signal"] == "caution"


@pytest.mark.parametrize("mean", [0.0, 0.003, 0.04, None])
def test_zero_positive_or_unknown_growth_is_not_flagged(mean):
    assert "weak_growth_signal" not in dq(mean_growth=mean)["flags"]


def test_pipeline_passes_the_citywide_mean_growth(mocked_pipeline):
    mocked_pipeline.setattr(
        pipeline_mod, "satellite_metrics",
        lambda cells, bbox, progress=None: {"growth": {c: -0.02 for c in cells}, "activity": {c: 1.0 for c in cells}},
    )
    r = pipeline_mod.run_pipeline("Smalltown", intent_from_preset("cafe"))
    assert "weak_growth_signal" in r["data_quality"]["flags"]


def test_pipeline_ignores_missing_growth_values_in_the_mean(mocked_pipeline):
    mocked_pipeline.setattr(
        pipeline_mod, "satellite_metrics",
        lambda cells, bbox, progress=None: {"growth": {c: (None if i % 2 else 0.03) for i, c in enumerate(cells)}, "activity": {}},
    )
    r = pipeline_mod.run_pipeline("Smalltown", intent_from_preset("cafe"))
    assert "weak_growth_signal" not in r["data_quality"]["flags"]
