"""Opportunity scoring: percentile-normalise each metric within the city, then weight.

Scores are RELATIVE to the city. They rank areas; they do not predict success.
"""
import numpy as np

METRICS = ("growth", "activity", "demand", "competition", "access")


def normalise(values: dict[str, float | None]) -> dict[str, float]:
    """Percentile rank in [0, 1]. Missing (None/NaN) -> neutral 0.5. Ties share the mean rank.
    If every present value is identical there is no signal -> 0.5 for all."""
    keys = list(values)
    arr = np.array([np.nan if v is None else float(v) for v in values.values()])
    present = ~np.isnan(arr)
    out = np.full(len(arr), 0.5)
    if present.sum() >= 2 and np.nanmax(arr) > np.nanmin(arr):
        x = arr[present]
        # average-rank percentile handles ties
        less = (x[:, None] > x[None, :]).sum(axis=1)
        equal = (x[:, None] == x[None, :]).sum(axis=1)
        out[present] = (less + (equal - 1) / 2) / (len(x) - 1)
    return dict(zip(keys, out.tolist()))


def validate_weights(weights: dict[str, float]) -> dict[str, float]:
    missing = set(METRICS) - set(weights)
    if missing:
        raise ValueError(f"Missing weights: {sorted(missing)}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("Weights must be non-negative")
    total = sum(weights[m] for m in METRICS)
    if total <= 0:
        raise ValueError("Weights must not all be zero")
    return {m: weights[m] / total for m in METRICS}


def score_hexes(raw: dict[str, dict[str, float | None]], weights: dict[str, float]) -> dict[str, dict]:
    """raw[metric][hex] -> raw value. Returns per-hex {score (0-100), norm{metric}}.
    Competition is inverted: fewer competitors -> higher contribution."""
    w = validate_weights(weights)
    norm = {m: normalise(raw[m]) for m in METRICS}
    hexes = list(raw["growth"])
    result = {}
    for h in hexes:
        n = {m: norm[m][h] for m in METRICS}
        n["competition"] = 1 - n["competition"]  # inverted: higher = less competition
        score = 100 * sum(w[m] * n[m] for m in METRICS)
        result[h] = {"score": round(score, 2), "norm": {m: round(v, 4) for m, v in n.items()}}
    return result


def top_n(scored: dict[str, dict], n: int = 10) -> list[str]:
    return sorted(scored, key=lambda h: (-scored[h]["score"], h))[:n]
