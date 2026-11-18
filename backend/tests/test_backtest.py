import json

import h3
import numpy as np
import pytest

from growthlens import backtest as bt
from growthlens.backtest import Config

CFG = Config(bootstrap=200)  # faster than the default; enough for these tests
CELLS = sorted(h3.grid_disk(h3.latlng_to_cell(13.0, 77.6, 8), 20))  # ~1,200 areas


def series(rng, past_growth, future_gain, level=None):
    """Year-by-year values per area (2017..2025): builds up by past_growth to 2020, then future_gain to 2025."""
    years = CFG.years
    out = {}
    for i, c in enumerate(CELLS):
        base = 0.2 if level is None else level[i]
        vals = []
        for y in years:
            if y <= CFG.t0:
                vals.append(base + past_growth[i] * (y - CFG.past_start) / (CFG.t0 - CFG.past_start))
            else:
                vals.append(base + past_growth[i] + future_gain[i] * (y - CFG.t0) / (CFG.future_end - CFG.t0))
        out[c] = vals
    return out


@pytest.fixture
def rng():
    return np.random.default_rng(0)


def make(rng, signal: float):
    """Future gain = signal * past growth + noise. signal=0 means the past tells you nothing about the future."""
    n = len(CELLS)
    past = rng.uniform(0, 0.3, n)
    future = signal * past + rng.normal(0, 0.05, n) + (1 - signal) * rng.uniform(0, 0.3, n)
    built = series(rng, past, future)
    light = series(rng, past * 3 + rng.normal(0, 0.05, n), future * 3)
    return built, light


def test_a_real_signal_gives_lift_well_above_one(rng):
    built, light = make(rng, signal=1.0)
    df = bt.prepare(built, light, CFG)
    r = bt.evaluate_city(df, 8, CFG)
    top10 = r["strategies"]["product"]["top10"]
    assert top10["lift"] > 2.0 and top10["lift_ci95"][0] > 1.0
    assert r["strategies"]["product"]["spearman"] > 0.5


def test_no_signal_gives_lift_near_one_and_ci_covers_one(rng):
    built, light = make(rng, signal=0.0)
    r = bt.evaluate_city(bt.prepare(built, light, CFG), 8, CFG)
    top10 = r["strategies"]["product"]["top10"]
    assert 0.5 < top10["lift"] < 1.8
    assert top10["lift_ci95"][0] <= 1.0 <= top10["lift_ci95"][1] or abs(top10["lift"] - 1) < 0.5
    assert abs(r["strategies"]["product"]["spearman"]) < 0.2


def test_future_data_cannot_change_the_scores(rng):
    """No leakage: rewrite everything after t0; the features and scores must be identical."""
    built, light = make(rng, signal=1.0)
    df1 = bt.prepare(built, light, CFG)
    built2 = {c: v[: CFG.t0 - CFG.past_start + 1] + [rng.uniform(0, 1) for _ in v[CFG.t0 - CFG.past_start + 1 :]] for c, v in built.items()}
    light2 = {c: v[: CFG.t0 - CFG.past_start + 1] + [rng.uniform(0, 9) for _ in v[CFG.t0 - CFG.past_start + 1 :]] for c, v in light.items()}
    df2 = bt.prepare(built2, light2, CFG)
    for k in ("product", "growth_only", "light_only", "room_to_grow"):
        assert bt.scores(df1, CFG)[k].equals(bt.scores(df2, CFG)[k])
    assert not df1["d_built"].equals(df2["d_built"])  # outcomes did change, scores did not


def test_scores_only_read_past_columns(rng):
    built, light = make(rng, 1.0)
    df = bt.prepare(built, light, CFG)
    s = bt.scores(df.drop(columns=["d_built", "d_light"]), CFG)  # works without any outcome column
    assert set(s) == set(bt.STRATEGIES)


def test_areas_with_missing_data_are_dropped(rng):
    built, light = make(rng, 1.0)
    first, second = CELLS[0], CELLS[1]
    built[first][bt.Config().years.index(2020)] = None
    light[second][-1] = float("nan")
    df = bt.prepare(built, light, CFG)
    assert len(df) == len(CELLS) - 2 and first not in set(df["hex"]) and second not in set(df["hex"])


def test_no_usable_areas_raises():
    with pytest.raises(ValueError, match="No areas"):
        bt.prepare({CELLS[0]: [None] * 9}, {CELLS[0]: [None] * 9}, CFG)


def test_room_to_grow_prefers_low_built_up_areas():
    import pandas as pd

    df = pd.DataFrame({"hex": ["a", "b", "c"], "level": [0.9, 0.5, 0.1], "g_past": [0, 0, 0], "n_past": [0, 0, 0]})
    s = bt.scores(df, CFG)["room_to_grow"]
    assert s[2] > s[1] > s[0]  # lowest built-up share (0.1) scores highest


def test_grew_flag_is_top_quartile_and_handles_ties():
    import pandas as pd

    df = pd.DataFrame({"d_built": list(np.linspace(0, 1, 100))})
    rel, _ = bt.outcome_flags(df, CFG)
    assert 24 <= rel.sum() <= 26
    flat = pd.DataFrame({"d_built": [0.1] * 50})
    rel, _ = bt.outcome_flags(flat, CFG)
    assert rel.sum() == 0  # no area "stands out" when everything is equal


def test_top_k_selection_is_deterministic_with_ties():
    s = np.array([1.0, 1.0, 1.0, 1.0, 0.0])
    assert list(bt._top_k_mask(s, 0.4)) == [True, True, False, False, False]  # first two, stable


def test_lift_arithmetic():
    grew = np.array([True, True, False, False, False, False, False, False, False, False])
    score = np.arange(10)[::-1].astype(float)  # first two have the highest scores
    assert bt._lift(score, grew, 0.2) == pytest.approx(1.0 / 0.2)  # all flagged grew; base rate 20%


def test_spearman_sign_and_bounds():
    a = np.arange(50.0)
    assert bt._spearman(a, a) == pytest.approx(1.0)
    assert bt._spearman(a, -a) == pytest.approx(-1.0)
    assert np.isnan(bt._spearman(np.array([1.0, 2.0]), np.array([1.0, 2.0])))


def test_evaluation_is_reproducible(rng):
    built, light = make(rng, 1.0)
    df = bt.prepare(built, light, CFG)
    assert bt.evaluate_city(df, 8, CFG) == bt.evaluate_city(df, 8, CFG)


def test_pooling_averages_cities_equally(rng):
    cities = []
    for sig in (1.0, 0.0, 1.0):
        built, light = make(np.random.default_rng(int(sig * 10) + len(cities)), sig)
        cities.append({**bt.evaluate_city(bt.prepare(built, light, CFG), 8, CFG, keep_boot=True), "city": f"C{len(cities)}"})
    pooled = bt.pool(cities, CFG)
    lifts = [c["strategies"]["product"]["top10"]["lift"] for c in cities]
    assert pooled["strategies"]["product"]["top10"]["mean_lift"] == pytest.approx(np.mean(lifts))
    assert pooled["strategies"]["product"]["top10"]["cities_with_lift_above_1"] == sum(x > 1 for x in lifts)
    lo, hi = pooled["strategies"]["product"]["top10"]["mean_lift_ci95"]
    assert lo <= hi


def test_report_is_json_serialisable_and_table_renders(rng, tmp_path, monkeypatch):
    built, light = make(rng, 1.0)

    def fake_city(name, cfg=CFG, say=print):
        r = bt.evaluate_city(bt.prepare(built, light, cfg), 8, cfg, keep_boot=True)
        r.update(city=name, approximate_boundary=False, dropped_areas=0)
        return r

    monkeypatch.setattr(bt, "run_city", fake_city)
    out = tmp_path / "bt.json"
    report = bt.run(["Alpha, X", "Beta, Y"], CFG, out, say=lambda *_: None)
    assert json.loads(out.read_text())["pooled"]["n_cities"] == 2
    table = bt.markdown_table(report)
    assert "| Alpha |" in table and "Average (2 cities)" in table
    assert "_boot" not in json.dumps(report)


def test_one_failing_city_does_not_lose_the_others(rng, monkeypatch):
    built, light = make(rng, 1.0)

    def flaky(name, cfg=CFG, say=print):
        if name.startswith("Bad"):
            raise RuntimeError("EE down")
        r = bt.evaluate_city(bt.prepare(built, light, cfg), 8, cfg, keep_boot=True)
        r.update(city=name, approximate_boundary=False, dropped_areas=0)
        return r

    monkeypatch.setattr(bt, "run_city", flaky)
    report = bt.run(["Bad City", "Good City"], CFG, None, say=lambda *_: None)
    assert [c["city"] for c in report["cities"]] == ["Good City"]
    monkeypatch.setattr(bt, "run_city", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("all down")))
    with pytest.raises(RuntimeError, match="no results"):
        bt.run(["Bad City"], CFG, None, say=lambda *_: None)


# ======================================================================= gap-year sensitivity design

def test_outcome_start_changes_only_the_outcome():
    cfg_gap = Config(t0=2019, outcome_start=2021, bootstrap=50)
    cfg_plain = Config(t0=2019, bootstrap=50)
    rng = np.random.default_rng(3)
    built, light = make(rng, 1.0)
    a, b = bt.prepare(built, light, cfg_plain), bt.prepare(built, light, cfg_gap)
    assert a["g_past"].equals(b["g_past"]) and a["n_past"].equals(b["n_past"]) and a["level"].equals(b["level"])
    assert not a["d_built"].equals(b["d_built"])
    yi = {y: i for i, y in enumerate(cfg_gap.years)}
    c0 = a["hex"].iloc[0]
    assert b.loc[b["hex"] == c0, "d_built"].iloc[0] == pytest.approx(built[c0][yi[2025]] - built[c0][yi[2021]])
    assert cfg_plain.outcome_from == 2019 and cfg_gap.outcome_from == 2021


def test_gap_design_removes_the_shared_noise_artifact():
    """Pure measurement noise, no real trend. Using the as-of year for BOTH signal and outcome makes the signal look
    anti-predictive (regression to the mean); leaving a gap year removes that."""
    rng = np.random.default_rng(11)
    n = len(CELLS)
    noise = rng.normal(0, 0.05, (n, 9))  # one value per year, independent across years
    built = {c: list(0.3 + noise[i]) for i, c in enumerate(CELLS)}
    light = {c: list(1.0 + rng.normal(0, 0.1, 9)) for c in CELLS}
    primary = Config(bootstrap=50)  # signal 2017-2020, outcome 2020-2025 (shares 2020)
    gap = Config(t0=2019, outcome_start=2021, bootstrap=50)  # signal 2017-2019, outcome 2021-2025
    rho_primary = bt.evaluate_city(bt.prepare(built, light, primary), 8, primary)["strategies"]["growth_only"]["spearman"]
    rho_gap = bt.evaluate_city(bt.prepare(built, light, gap), 8, gap)["strategies"]["growth_only"]["spearman"]
    assert rho_primary < -0.2  # the artifact: spuriously negative with no real signal
    assert abs(rho_gap) < 0.1  # no artifact once signal and outcome share no year


def test_gap_design_has_no_leakage(rng):
    cfg = Config(t0=2019, outcome_start=2021, bootstrap=50)
    built, light = make(rng, 1.0)
    df1 = bt.prepare(built, light, cfg)
    cut = cfg.t0 - cfg.past_start + 1
    built2 = {c: v[:cut] + [rng.uniform(0, 1) for _ in v[cut:]] for c, v in built.items()}
    light2 = {c: v[:cut] + [rng.uniform(0, 9) for _ in v[cut:]] for c, v in light.items()}
    df2 = bt.prepare(built2, light2, cfg)
    for k in bt.STRATEGIES:
        assert bt.scores(df1, cfg)[k].equals(bt.scores(df2, cfg)[k])


def test_report_includes_the_sensitivity_block_and_table_column(rng, monkeypatch):
    built, light = make(rng, 1.0)

    def fake_city(name, cfg=CFG, say=print):
        r = bt.evaluate_city(bt.prepare(built, light, cfg), 8, cfg, keep_boot=True)
        r.update(city=name, approximate_boundary=False, dropped_areas=0)
        return r

    monkeypatch.setattr(bt, "run_city", fake_city)
    report = bt.run(["Alpha, X"], CFG, None, say=lambda *_: None, sensitivity=Config(t0=2019, outcome_start=2021, bootstrap=50))
    assert report["sensitivity"]["config"]["outcome_start"] == 2021 and "gap year" in report["sensitivity"]["description"]
    assert "Gap-year check" in bt.markdown_table(report)
    assert "_boot" not in json.dumps(report)
