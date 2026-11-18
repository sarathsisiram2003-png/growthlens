import pytest

from growthlens.scoring import METRICS, normalise, score_hexes, top_n, validate_weights

EQUAL = {m: 1.0 for m in METRICS}


def raw_for(**overrides):
    base = {m: {"a": 1.0, "b": 2.0, "c": 3.0} for m in METRICS}
    base.update(overrides)
    return base


def test_normalise_percentile_range():
    n = normalise({"a": 10, "b": 20, "c": 30})
    assert n == {"a": 0.0, "b": 0.5, "c": 1.0}


def test_normalise_ties_share_rank():
    n = normalise({"a": 1, "b": 1, "c": 5})
    assert n["a"] == n["b"] == 0.25
    assert n["c"] == 1.0


def test_normalise_all_equal_is_neutral():
    assert set(normalise({"a": 4, "b": 4, "c": 4}).values()) == {0.5}


def test_normalise_missing_is_neutral():
    n = normalise({"a": 1, "b": None, "c": 9})
    assert n["b"] == 0.5 and n["a"] == 0.0 and n["c"] == 1.0


def test_normalise_single_or_empty():
    assert normalise({"a": 3}) == {"a": 0.5}
    assert normalise({}) == {}


def test_outlier_does_not_squash_others():
    n = normalise({"a": 1, "b": 2, "c": 3, "d": 1_000_000})
    assert n["b"] - n["a"] > 0.2  # percentile, not min-max


def test_weights_are_normalised():
    w = validate_weights({m: 2.0 for m in METRICS})
    assert sum(w.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "bad", [{"growth": 1}, {**EQUAL, "growth": -1}, {m: 0 for m in METRICS}]
)
def test_invalid_weights_raise(bad):
    with pytest.raises(ValueError):
        validate_weights(bad)


def test_score_bounds_and_ordering():
    scored = score_hexes(raw_for(competition={"a": 3.0, "b": 3.0, "c": 3.0}), EQUAL)
    assert all(0 <= v["score"] <= 100 for v in scored.values())
    assert top_n(scored, 3) == ["c", "b", "a"]


def test_competition_is_inverted():
    # Only competition varies: the hex with most competitors must score lowest.
    flat = {m: {"a": 1, "b": 1, "c": 1} for m in METRICS}
    flat["competition"] = {"a": 0, "b": 5, "c": 10}
    scored = score_hexes(flat, {**{m: 0.0 for m in METRICS}, "competition": 1.0})
    assert scored["a"]["score"] == 100 and scored["c"]["score"] == 0


def test_weights_change_ranking():
    raw = raw_for(
        growth={"a": 9, "b": 1, "c": 5},
        demand={"a": 1, "b": 9, "c": 5},
    )
    zero = {m: 0.0 for m in METRICS}
    assert top_n(score_hexes(raw, {**zero, "growth": 1.0}), 1) == ["a"]
    assert top_n(score_hexes(raw, {**zero, "demand": 1.0}), 1) == ["b"]


def test_missing_satellite_data_does_not_crash():
    raw = raw_for(growth={"a": None, "b": None, "c": None}, activity={"a": None, "b": 1.0, "c": None})
    scored = score_hexes(raw, EQUAL)
    assert len(scored) == 3


def test_top_n_tiebreak_is_deterministic():
    scored = {"b": {"score": 50}, "a": {"score": 50}, "c": {"score": 60}}
    assert top_n(scored, 3) == ["c", "a", "b"]
