import json
import time

import pytest
from fastapi.testclient import TestClient

from growthlens import api as api_mod
from growthlens import brief as brief_mod
from growthlens import history as history_mod
from growthlens import imagery as imagery_mod
from growthlens import results as results_mod
from growthlens.api import app
from growthlens.brief import Brief, nearby
from growthlens.osm import collect_places
from growthlens.results import ResultNotFound, find_hex, result_file

client = TestClient(app)
HEX = "8860145949fffff"


def make_result(rid="bengaluru_cafe_0123456789"):
    norm = {"growth": 0.9, "activity": 0.6, "demand": 0.8, "competition": 0.95, "access": 0.5}
    row = {
        "hex": HEX, "lat": 13.0, "lon": 77.5, "score": 84.2, "rank": 1, "name": "Testpura",
        "raw": {"growth": 0.07, "activity": 4.4, "demand": 26.0, "competition": 0.0, "access": 2.0}, "norm": norm,
    }
    return {
        "id": rid, "schema": 2, "label": "Specialty café",
        "city": {"name": "Bengaluru, Karnataka", "bbox": [77.4, 12.9, 77.7, 13.1]},
        "intent": {"summary": "Cafés near students"},
        "data_quality": {"flags": [], "osm_coverage": 0.9},
        "places": {
            "competitors": [[13.0005, 77.5, "Near Cafe"], [13.2, 77.9, "Far Cafe"]],
            "drivers": [[13.001, 77.5, "Test College", "college"], [13.002, 77.5, None, "office"]],
        },
        "hexes": [row], "top10": [HEX],
    }


@pytest.fixture
def stored(monkeypatch, tmp_path):
    monkeypatch.setattr(results_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(history_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(imagery_mod.settings, "data_dir", tmp_path)
    r = make_result()
    (results_mod.settings.output_dir / f"{r['id']}.json").write_text(json.dumps(r), encoding="utf-8")
    # LLM off and cache in memory by default
    monkeypatch.setattr(brief_mod.settings, "gemini_api_key", "")
    mem: dict = {}
    monkeypatch.setattr(brief_mod.cache, "get", lambda k, max_age_s=None: mem.get(k))
    monkeypatch.setattr(brief_mod.cache, "put", lambda k, v: mem.__setitem__(k, v))
    return r


# ---- places / nearby ----

def test_collect_places_splits_and_labels():
    import h3

    cell = h3.latlng_to_cell(13.0, 77.5, 8)
    els = [
        {"type": "node", "lat": 13.0, "lon": 77.5, "tags": {"amenity": "cafe", "name": "A"}},
        {"type": "node", "lat": 13.0, "lon": 77.5, "tags": {"office": "it"}},
        {"type": "node", "lat": 13.0, "lon": 77.5, "tags": {"amenity": "college"}},
        {"type": "node", "lat": 0.0, "lon": 0.0, "tags": {"amenity": "cafe"}},  # outside city
    ]
    out = collect_places(els, {("amenity", "cafe"): 1.0}, {("office", None): 1.0, ("amenity", "college"): 3.0}, {cell}, 8)
    assert out["competitors"] == [[13.0, 77.5, "A"]]
    assert sorted(d[3] for d in out["drivers"]) == ["college", "it"]  # value-less tag labelled by its value


def test_nearby_filters_by_radius_and_sorts(stored):
    near = nearby(stored, stored["hexes"][0])
    assert [c["name"] for c in near["competitors"]] == ["Near Cafe"]  # "Far Cafe" is ~80 km away
    assert near["drivers"][0]["kind"] == "college" and near["drivers"][0]["distance_m"] < near["drivers"][1]["distance_m"]


# ---- result ids are safe ----

@pytest.mark.parametrize("bad", ["../secret", "a", "..\\x", "UPPER_case_xx", "x" * 200, "a/b_cafe_0123456789"])
def test_result_ids_reject_traversal(stored, bad):
    with pytest.raises(ResultNotFound):
        result_file(bad)


def test_find_hex_validates(stored):
    assert find_hex(stored, HEX)["name"] == "Testpura"
    with pytest.raises(ResultNotFound):
        find_hex(stored, "not-a-hex")
    with pytest.raises(ResultNotFound):
        find_hex(stored, "8860145941fffff")


def test_results_endpoint(stored):
    assert client.get(f"/results/{stored['id']}").json()["label"] == "Specialty café"
    assert client.get("/results/nope_nope_0000000000").status_code == 404
    assert client.get("/results/..%2Fetc").status_code in (404, 422)


# ---- brief ----

def test_brief_template_without_key(stored):
    r = client.get(f"/results/{stored['id']}/brief/{HEX}")
    b = r.json()
    assert r.status_code == 200 and b["source"] == "template"
    assert "1 competitor" in b["risks"] and "do not predict revenue" in b["risks"]
    assert "college" in b["why_here"]


def test_brief_uses_llm_and_caches(stored, monkeypatch):
    monkeypatch.setattr(brief_mod.settings, "gemini_api_key", "k")
    calls = []

    def fake(system, content, schema, **kw):
        calls.append(content)
        return {"why_here": "W", "risks": "R", "suggested_format": "F"}

    monkeypatch.setattr(brief_mod, "generate_json", fake)
    for _ in range(2):
        b = client.get(f"/results/{stored['id']}/brief/{HEX}").json()
    assert b == {"why_here": "W", "risks": "R", "suggested_format": "F", "source": "llm"}
    assert len(calls) == 1
    facts = json.loads(calls[0].split("Facts:\n")[1])
    assert facts["area"] == "Testpura" and facts["within_1200m"]["competitor_count"] == 1


def test_brief_prompt_forbids_invention():
    assert "Never invent" in brief_mod.SYSTEM_PROMPT and "relative" in brief_mod.SYSTEM_PROMPT


@pytest.mark.parametrize("bad", [RuntimeError("boom"), {"why_here": "x"}, {"why_here": "a", "risks": "b", "suggested_format": "c", "extra": 1}])
def test_brief_falls_back_on_llm_failure(stored, monkeypatch, bad):
    monkeypatch.setattr(brief_mod.settings, "gemini_api_key", "k")

    def fake(*a, **k):
        if isinstance(bad, Exception):
            raise bad
        return bad

    monkeypatch.setattr(brief_mod, "generate_json", fake)
    assert client.get(f"/results/{stored['id']}/brief/{HEX}").json()["source"] == "template"


def test_brief_unknown_hex_404(stored):
    assert client.get(f"/results/{stored['id']}/brief/8860145941fffff").status_code == 404
    assert client.get(f"/results/{stored['id']}/brief/zzz").status_code == 404


# ---- imagery ----

def test_imagery_validation_and_success(monkeypatch):
    monkeypatch.setattr(api_mod, "thumbnail_png", lambda h, y: b"\x89PNG-fake")
    ok = client.get(f"/imagery/{HEX}?year=2017")
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png" and "max-age" in ok.headers["cache-control"]
    assert client.get("/imagery/nothex?year=2017").status_code == 400
    assert client.get(f"/imagery/{HEX}?year=2010").status_code == 400
    assert client.get(f"/imagery/{HEX}?year=3000").status_code == 400
    assert client.get(f"/imagery/{HEX}").status_code == 422


def test_imagery_failure_is_502(monkeypatch):
    def boom(h, y):
        raise imagery_mod.ImageryError("No clear satellite scenes for 2017")

    monkeypatch.setattr(api_mod, "thumbnail_png", boom)
    r = client.get(f"/imagery/{HEX}?year=2017")
    assert r.status_code == 502 and "No clear" in r.json()["detail"]


def test_imagery_disk_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(imagery_mod.settings, "data_dir", tmp_path)
    (imagery_mod.settings.cache_dir / "imagery").mkdir(parents=True, exist_ok=True)
    (imagery_mod.settings.cache_dir / "imagery" / f"{HEX}_2017.png").write_bytes(b"cached")
    assert imagery_mod.thumbnail_png(HEX, 2017) == b"cached"  # no Earth Engine call needed


# ---- history ----

def test_history_lifecycle(stored, monkeypatch):
    def fake_compute(rid):
        history_mod._state[rid].update(state="done", data={"years": [2016], "values": {HEX: [0.3]}}, progress=1.0)

    monkeypatch.setattr(history_mod, "_compute", fake_compute)
    history_mod._state.clear()
    assert client.get(f"/results/{stored['id']}/history").json() == {"state": "idle"}
    r = client.post(f"/results/{stored['id']}/history")
    assert r.status_code == 202 and "data" not in r.json()
    for _ in range(100):
        got = client.get(f"/results/{stored['id']}/history").json()
        if got["state"] == "done":
            break
        time.sleep(0.02)
    assert got["data"]["values"][HEX] == [0.3]
    # idempotent: a second start does not recompute
    assert client.post(f"/results/{stored['id']}/history").status_code == 202


def test_history_error_can_be_retried(stored, monkeypatch):
    n = []

    def flaky(rid):
        n.append(1)
        history_mod._state[rid].update(state="error", error="nope")

    monkeypatch.setattr(history_mod, "_compute", flaky)
    history_mod._state.clear()
    client.post(f"/results/{stored['id']}/history")
    time.sleep(0.1)
    assert client.get(f"/results/{stored['id']}/history").json()["state"] == "error"
    client.post(f"/results/{stored['id']}/history")  # retry
    time.sleep(0.1)
    assert len(n) == 2


def test_history_unknown_result_404():
    assert client.post("/results/nope_nope_0000000000/history").status_code == 404


# ---- area name ----

def test_area_name(monkeypatch):
    monkeypatch.setattr(api_mod, "reverse_area", lambda lat, lon: "Koramangala")
    assert client.get("/area-name?lat=12.93&lon=77.62").json() == {"name": "Koramangala"}
    assert client.get("/area-name?lat=999&lon=0").status_code == 422
    assert client.get("/area-name?lat=0").status_code == 422
