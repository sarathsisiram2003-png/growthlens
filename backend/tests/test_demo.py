import json

import pytest
from fastapi.testclient import TestClient

from growthlens import api as api_mod
from growthlens import brief as brief_mod
from growthlens import demo
from growthlens.config import settings

client = TestClient(api_mod.app)
HEX = "8860145949fffff"
RID = "democity_cafe_0123456789"


def result():
    norm = {"growth": 0.9, "activity": 0.6, "demand": 0.8, "competition": 0.95, "access": 0.5}
    return {
        "id": RID, "schema": 3, "label": "Specialty café", "city": {"name": "Democity", "bbox": [0, 0, 1, 1]},
        "intent": {"summary": "x"}, "data_quality": {"flags": [], "osm_coverage": 0.9, "level": "good"},
        "places": {"competitors": [], "drivers": []}, "top10": [HEX],
        "hexes": [{"hex": HEX, "lat": 13.0, "lon": 77.5, "score": 80.0, "rank": 1, "name": "Testpura", "norm": norm,
                   "raw": {"growth": 0.07, "activity": 4.0, "demand": 20.0, "competition": 0.0, "access": 2.0}}],
    }


@pytest.fixture
def pack(monkeypatch, tmp_path):
    """A demo pack in a temporary demo dir and an empty data dir."""
    demo_dir = tmp_path / "demo"
    data_dir = tmp_path / "data"
    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(brief_mod.settings, "gemini_api_key", "")
    demo._briefs.clear()
    d = demo.pack_dir("democity")
    (d / "result.json").write_text(json.dumps(result()), encoding="utf-8")
    (d / "history.json").write_text(json.dumps({"years": [2016], "values": {HEX: [0.3]}}), encoding="utf-8")
    (d / "briefs.json").write_text(json.dumps({HEX: {"why_here": "W", "risks": "R", "suggested_format": "F", "source": "llm"}}), encoding="utf-8")
    (d / "imagery").mkdir()
    (d / "imagery" / f"{HEX}_2017.png").write_bytes(b"png17")
    demo.write_index([{"slug": "democity", "city": "Democity, X", "label": "Democity", "result_id": RID, "query": "cafe"}])
    yield d
    demo._briefs.clear()


def test_install_copies_everything_to_where_the_app_reads_it(pack):
    assert demo.install() == 1
    assert (settings.output_dir / f"{RID}.json").exists()
    assert (settings.cache_dir / "history" / f"{RID}.json").exists()
    assert (settings.cache_dir / "imagery" / f"{HEX}_2017.png").read_bytes() == b"png17"


def test_install_is_idempotent_and_does_not_overwrite_newer_cache(pack):
    demo.install()
    cached = settings.cache_dir / "imagery" / f"{HEX}_2017.png"
    cached.write_bytes(b"newer")
    demo.install()
    assert cached.read_bytes() == b"newer"


def test_install_with_no_demos_is_a_no_op(monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "DEMO_DIR", tmp_path / "nothing")
    assert demo.install() == 0 and demo.index() == []


def test_pack_missing_its_result_is_skipped(pack):
    (pack / "result.json").unlink()
    assert demo.install() == 0


def test_demo_list_and_result_endpoints(pack):
    demo.install()
    lst = client.get("/demo").json()
    assert lst == [{"slug": "democity", "city": "Democity, X", "label": "Democity", "result_id": RID}]
    r = client.get("/demo/democity")
    assert r.status_code == 200 and r.json()["id"] == RID


@pytest.mark.parametrize("slug", ["nope", "..%2F..%2Fsecret", "democity%2F..%2Fx"])
def test_unknown_or_malicious_slugs_are_404(pack, slug):
    assert client.get(f"/demo/{slug}").status_code in (404, 422)


def test_demo_briefs_are_served_without_any_llm(pack, monkeypatch):
    demo.install()

    def boom(*a, **k):
        raise AssertionError("the LLM must not be called for a demo area")

    monkeypatch.setattr(brief_mod, "generate_json", boom)
    monkeypatch.setattr(brief_mod.settings, "gemini_api_key", "set-but-unused")
    b = client.get(f"/results/{RID}/brief/{HEX}").json()
    assert b == {"why_here": "W", "risks": "R", "suggested_format": "F", "source": "llm"}


def test_demo_result_works_with_the_normal_results_endpoints(pack):
    demo.install()
    assert client.get(f"/results/{RID}").json()["label"] == "Specialty café"
    hist = client.get(f"/results/{RID}/history").json()  # served from the installed cache, no Earth Engine
    assert hist["state"] == "done" and hist["data"]["values"][HEX] == [0.3]


def test_the_committed_demo_index_is_valid():
    """Whatever demo packs are committed must be complete and self-consistent."""
    real = demo.BASE_DIR / "demo"
    index = json.loads((real / "index.json").read_text(encoding="utf-8")) if (real / "index.json").exists() else []
    for e in index:
        res = json.loads((real / e["slug"] / "result.json").read_text(encoding="utf-8"))
        assert res["id"] == e["result_id"] and len(res["top10"]) == 10 and res["data_quality"].get("level")
        briefs = json.loads((real / e["slug"] / "briefs.json").read_text(encoding="utf-8"))
        assert set(briefs) == set(res["top10"])


def test_install_copies_no_data_markers_so_the_drawer_can_fall_back_instantly(pack):
    (pack / "imagery" / f"{HEX}_2017.none").write_text("", encoding="utf-8")
    demo.install()
    assert (settings.cache_dir / "imagery" / f"{HEX}_2017.none").exists()
