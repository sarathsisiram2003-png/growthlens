import time

import pytest
from fastapi.testclient import TestClient

from growthlens import jobs as jobs_mod
from growthlens.api import app
from growthlens.geocode import GeocodeError
from growthlens.intent import intent_from_preset
from growthlens.pipeline import SCHEMA_VERSION
from growthlens.reasons import build_reason

client = TestClient(app)


# ---- reasons ----

def test_reason_lists_strongest_signals():
    norm = {"growth": 0.95, "demand": 0.9, "activity": 0.4, "competition": 0.8, "access": 0.5}
    r = build_reason(norm, {"competition": 3})
    assert r.startswith("Fast-growing built-up area, strong demand drivers nearby")
    assert r.endswith(".")


def test_reason_zero_competitors_wording():
    r = build_reason({"competition": 1.0, "growth": 0.5, "demand": 0.5, "activity": 0.5, "access": 0.5}, {"competition": 0})
    assert "no mapped competitors" in r.lower()


def test_reason_balanced_and_cautions():
    flat = {m: 0.5 for m in ("growth", "demand", "activity", "competition", "access")}
    assert build_reason(flat, {}) == "Balanced profile across all signals."
    r = build_reason({**flat, "competition": 0.1, "growth": 0.9}, {})
    assert "crowded with competitors" in r


# ---- jobs ----

@pytest.fixture
def fake_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(jobs_mod, "parse_intent", lambda q: (intent_from_preset("cafe"), None))
    calls = []

    def fake_run(city, intent, progress=None, **_):
        calls.append(city)
        for step in ("map", "satellite", "competitors", "scoring", "briefs"):
            progress(step, f"doing {step}", {"boundary": {"type": "Polygon", "coordinates": []}, "center": [1, 2]} if step == "map" else None)
        return {"schema": SCHEMA_VERSION, "city": {"name": city, "lat": 1, "lon": 2, "boundary": {}}, "category": "cafe", "data_quality": {"flags": []}, "hexes": []}

    monkeypatch.setattr(jobs_mod, "run_pipeline", fake_run)
    return calls


def wait_done(job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        st = client.get(f"/jobs/{job_id}").json()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_runs_and_serves_result(fake_pipeline):
    r = client.post("/jobs", json={"city": "Testville", "query": "cafe"})
    assert r.status_code == 202
    st = wait_done(r.json()["id"])
    assert st["status"] == "done"
    assert [s["state"] for s in st["steps"]] == ["done"] * 6
    assert st["meta"]["center"] == [1, 2]
    assert st["intent"]["category_key"] == "cafe"
    res = client.get(f"/jobs/{r.json()['id']}/result")
    assert res.status_code == 200 and res.json()["city"]["name"] == "Testville"


def test_repeat_search_is_served_from_cache(fake_pipeline):
    for _ in range(2):
        st = wait_done(client.post("/jobs", json={"city": "Cacheton", "query": "cafe"}).json()["id"])
        assert st["status"] == "done"
    assert fake_pipeline == ["Cacheton"]  # pipeline ran once; second job hit the file cache


def test_error_is_friendly_and_marks_step(fake_pipeline, monkeypatch):
    def boom(*_a, **_k):
        raise GeocodeError("No city boundary found for 'Nowhere'")

    monkeypatch.setattr(jobs_mod, "run_pipeline", boom)
    st = wait_done(client.post("/jobs", json={"city": "Nowhere", "query": "cafe"}).json()["id"])
    assert st["status"] == "error" and "couldn't find that city" in st["error"]
    assert client.get(f"/jobs/{st['id']}/result").status_code == 409


def test_unexpected_error_hides_internals(fake_pipeline, monkeypatch):
    monkeypatch.setattr(jobs_mod, "run_pipeline", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret path C:\\x")))
    st = wait_done(client.post("/jobs", json={"city": "Boom", "query": "cafe"}).json()["id"])
    assert st["status"] == "error" and "secret" not in st["error"]


def test_unknown_job_404():
    assert client.get("/jobs/nope").status_code == 404
    assert client.get("/jobs/nope/result").status_code == 404


def test_validation_rejects_short_input():
    assert client.post("/jobs", json={"city": "x", "query": "cafe"}).status_code == 422
    assert client.post("/jobs", json={"city": "Paris", "query": "a" * 301}).status_code == 422


def test_cors_allows_frontend_origin():
    r = client.options("/jobs", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_outdated_cached_result_is_recomputed(fake_pipeline):
    st = wait_done(client.post("/jobs", json={"city": "Oldville", "query": "cafe"}).json()["id"])
    path = jobs_mod.get_job(st["id"]).result_path
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    data["schema"] = SCHEMA_VERSION - 1  # simulate a file written by an older version
    path.write_text(json.dumps(data), encoding="utf-8")
    wait_done(client.post("/jobs", json={"city": "Oldville", "query": "cafe"}).json()["id"])
    assert fake_pipeline.count("Oldville") == 2


def test_done_job_exposes_result_id(fake_pipeline):
    st = wait_done(client.post("/jobs", json={"city": "Idtown", "query": "cafe"}).json()["id"])
    assert st["result_id"] and st["result_id"].startswith("idtown_cafe_")
