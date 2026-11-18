"""Backtest: do the satellite signals available in 2020 anticipate where building happened afterwards?

Question: if GrowthLens had been run at the end of 2020, using only satellite data up to then, would the areas it
flagged have grown more over the next five years than the rest of the city?

- Signals (all from years <= t0): past built-up change and past night-light trend, weighted in the same ratio the
  product uses for its growth and night-light components.
- Outcome (all from years > t0): change in built-up probability from t0 to the end year.
- "Grew" = the area is in the top quartile of built-up gain in its city (scores are city-relative, so is this).
- Flagged = the top 5% / 10% of areas by score. Lift = share of flagged areas that grew / share of all areas that grew.
- Baselines: random (lift 1 by definition), growth only, night lights only, and "room to grow" (low built-up share).
- Uncertainty: cluster bootstrap over coarser H3 cells, because neighbouring areas are not independent.

What this does NOT test: OpenStreetMap competition, demand and access. Historical OSM is not available to us, so only the
satellite part of the score is validated, and "areas that grew" is not the same as "places where a business succeeds".
"""
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import h3
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Config:
    past_start: int = 2017  # first year of the "past" window (Sentinel-era, full Dynamic World coverage)
    t0: int = 2020  # the "as of" year: nothing after it feeds the score
    future_end: int = 2025
    outcome_start: int | None = None  # None = t0. Set later than t0 to leave a gap year (sensitivity analysis)
    w_growth: float = 0.25  # product weights (café profile): growth and night lights, renormalised below
    w_light: float = 0.15
    grew_quantile: float = 0.75  # "grew" = top quartile of built-up gain within the city
    min_gain: float = 0.05  # secondary, absolute criterion: at least +5 points of built-up probability
    top_fracs: tuple[float, ...] = (0.05, 0.10)
    bootstrap: int = 1000
    cluster_drop: int = 2  # bootstrap clusters are H3 parents this many resolutions coarser
    seed: int = 7

    @property
    def outcome_from(self) -> int:
        return self.t0 if self.outcome_start is None else self.outcome_start

    @property
    def years(self) -> list[int]:
        return list(range(self.past_start, self.future_end + 1))


STRATEGIES = ("product", "growth_only", "light_only", "room_to_grow")
DEFAULT_CITIES = [
    "Bengaluru, Karnataka, India",
    "Pune, Maharashtra, India",
    "Delhi, India",
    "Dubai, United Arab Emirates",
    "Nairobi, Kenya",
    "Lagos, Nigeria",
    "London, England, United Kingdom",
    "Los Angeles, United States",
]


# ------------------------------------------------------------------ data preparation

def _pct(s: pd.Series) -> pd.Series:
    """Percentile in [0, 1] within the city (average rank for ties), as the product's scoring does."""
    n = len(s)
    return (s.rank(method="average") - 1) / (n - 1) if n > 1 else s * 0 + 0.5


def prepare(
    built: dict[str, list[float | None]], viirs: dict[str, list[float | None]], cfg: Config = Config()
) -> pd.DataFrame:
    """One row per area with past features and future outcomes. Areas missing any needed value are dropped.

    `built`/`viirs` map hex -> one value per year in cfg.years.
    """
    yi = {y: i for i, y in enumerate(cfg.years)}
    rows = []
    for hex_id, b in built.items():
        v = viirs.get(hex_id)
        if v is None:
            continue
        try:
            vals = (
                b[yi[cfg.past_start]], b[yi[cfg.t0]], b[yi[cfg.future_end]], v[yi[cfg.past_start]], v[yi[cfg.t0]],
                v[yi[cfg.future_end]], b[yi[cfg.outcome_from]], v[yi[cfg.outcome_from]],
            )
        except (IndexError, KeyError):
            continue
        if any(x is None or (isinstance(x, float) and math.isnan(x)) for x in vals):
            continue
        b0, bt, bf, l0, lt, lf, bo, lo = vals
        rows.append(
            {"hex": hex_id, "level": bt, "g_past": bt - b0, "n_past": lt - l0, "d_built": bf - bo, "d_light": lf - lo}
        )
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No areas with complete data for the backtest window")
    return df.sort_values("hex").reset_index(drop=True)


def scores(df: pd.DataFrame, cfg: Config = Config()) -> dict[str, pd.Series]:
    """Per-strategy scores using ONLY past features (columns g_past, n_past, level, all from years <= t0)."""
    wg, wl = cfg.w_growth, cfg.w_light
    g, n = _pct(df["g_past"]), _pct(df["n_past"])
    return {
        "product": (wg * g + wl * n) / (wg + wl),
        "growth_only": g,
        "light_only": n,
        "room_to_grow": 1 - _pct(df["level"]),  # low existing built-up share = more land left to develop
    }


# ------------------------------------------------------------------ metrics

def _top_k_mask(score: np.ndarray, frac: float) -> np.ndarray:
    k = max(1, math.ceil(frac * len(score)))
    order = np.argsort(-score, kind="stable")  # ties keep input (hex-sorted) order: deterministic
    mask = np.zeros(len(score), dtype=bool)
    mask[order[:k]] = True
    return mask


def _lift(score: np.ndarray, grew: np.ndarray, frac: float) -> float:
    base = grew.mean()
    if base == 0:
        return float("nan")
    return float(grew[_top_k_mask(score, frac)].mean() / base)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = pd.Series(a).rank(method="average")
    rb = pd.Series(b).rank(method="average")
    c = ra.corr(rb)
    return float(c) if c == c else float("nan")


def outcome_flags(df: pd.DataFrame, cfg: Config = Config()) -> tuple[np.ndarray, np.ndarray]:
    """(grew_relative, grew_absolute) booleans per area."""
    thresh = df["d_built"].quantile(cfg.grew_quantile)
    rel = (df["d_built"] >= thresh).to_numpy() if thresh > df["d_built"].min() else (df["d_built"] > thresh).to_numpy()
    return rel, (df["d_built"] >= cfg.min_gain).to_numpy()


def _clusters(df: pd.DataFrame, resolution: int, drop: int) -> list[np.ndarray]:
    parent_res = max(0, resolution - drop)
    groups: dict[str, list[int]] = {}
    for i, hx in enumerate(df["hex"]):
        groups.setdefault(h3.cell_to_parent(hx, parent_res), []).append(i)
    return [np.array(v) for v in groups.values()]


def evaluate_city(df: pd.DataFrame, resolution: int, cfg: Config = Config(), keep_boot: bool = False) -> dict:
    sc = {k: v.to_numpy() for k, v in scores(df, cfg).items()}
    grew, grew_abs = outcome_flags(df, cfg)
    gain = df["d_built"].to_numpy()
    base_rate, base_abs = float(grew.mean()), float(grew_abs.mean())

    clusters = _clusters(df, resolution, cfg.cluster_drop)
    rng = np.random.default_rng(cfg.seed)
    draws = [np.concatenate([clusters[j] for j in rng.integers(0, len(clusters), len(clusters))]) for _ in range(cfg.bootstrap)]

    out: dict = {"strategies": {}}
    boot: dict = {}
    for name, s in sc.items():
        entry: dict = {}
        for frac in cfg.top_fracs:
            mask = _top_k_mask(s, frac)
            lifts = np.array([_lift(s[ix], grew[ix], frac) for ix in draws])
            boot[(name, f"top{int(frac * 100)}")] = lifts
            entry[f"top{int(frac * 100)}"] = {
                "n_flagged": int(mask.sum()),
                "share_grew": float(grew[mask].mean()),
                "lift": _lift(s, grew, frac),
                "lift_ci95": [float(np.nanpercentile(lifts, 2.5)), float(np.nanpercentile(lifts, 97.5))],
                "mean_gain_flagged": float(gain[mask].mean()),
                "share_gained_5pts_flagged": float(grew_abs[mask].mean()),
            }
        rho = _spearman(s, gain)
        rhos = np.array([_spearman(s[ix], gain[ix]) for ix in draws[: min(300, len(draws))]])
        entry["spearman"] = rho
        entry["spearman_ci95"] = [float(np.nanpercentile(rhos, 2.5)), float(np.nanpercentile(rhos, 97.5))]
        out["strategies"][name] = entry
    out.update(
        n_areas=len(df), resolution=resolution, n_clusters=len(clusters), base_rate_grew=base_rate,
        base_rate_gained_5pts=base_abs, mean_gain_all=float(gain.mean()),
    )
    if keep_boot:
        out["_boot"] = boot
    return out


def pool(cities: list[dict], cfg: Config = Config()) -> dict:
    """Macro-average across cities (each city counts equally) with a CI from replicate-wise averaging."""
    pooled: dict = {"n_cities": len(cities), "strategies": {}}
    for name in STRATEGIES:
        entry: dict = {}
        for frac in cfg.top_fracs:
            key = f"top{int(frac * 100)}"
            lifts = [c["strategies"][name][key]["lift"] for c in cities]
            boots = np.vstack([c["_boot"][(name, key)] for c in cities])  # cities x replicates
            means = np.nanmean(boots, axis=0)
            entry[key] = {
                "mean_lift": float(np.nanmean(lifts)),
                "mean_lift_ci95": [float(np.nanpercentile(means, 2.5)), float(np.nanpercentile(means, 97.5))],
                "cities_with_lift_above_1": int(sum(1 for x in lifts if x > 1)),
                "mean_share_grew": float(np.mean([c["strategies"][name][key]["share_grew"] for c in cities])),
            }
        entry["mean_spearman"] = float(np.nanmean([c["strategies"][name]["spearman"] for c in cities]))
        pooled["strategies"][name] = entry
    pooled["mean_base_rate_grew"] = float(np.mean([c["base_rate_grew"] for c in cities]))
    return pooled


# ------------------------------------------------------------------ running it on real cities

def run_city(name: str, cfg: Config = Config(), say=print) -> dict:
    """Fetch yearly satellite series for a city (cached) and evaluate. Needs Earth Engine + Nominatim."""
    from .config import settings
    from .geocode import geocode_city
    from .grid import choose_resolution
    from .satellite import yearly_stats

    city = geocode_city(name)
    res, cells = choose_resolution(city.boundary, settings.h3_resolution, settings.min_hexes, settings.max_hexes, settings.max_area_km2)
    minx, miny, maxx, maxy = city.boundary.bounds
    bbox = (miny, minx, maxy, maxx)
    say(f"{name}: {len(cells)} areas at resolution {res}" + (" (approximate boundary)" if city.approximate else ""))
    built = yearly_stats("built", cells, bbox, cfg.years, say)
    viirs = yearly_stats("viirs", cells, bbox, cfg.years, say)
    df = prepare(built, viirs, cfg)
    result = evaluate_city(df, res, cfg, keep_boot=True)
    result.update(city=name, approximate_boundary=city.approximate, dropped_areas=len(cells) - len(df))
    return result


def run(
    cities: list[str] | None = None, cfg: Config = Config(), out: Path | None = None, say=print,
    sensitivity: Config | None = None,
) -> dict:
    """Primary backtest, optionally followed by a sensitivity analysis (same data, different design) in the same report."""
    results = []
    for name in cities or DEFAULT_CITIES:
        try:
            results.append(run_city(name, cfg, say))
        except Exception as e:  # noqa: BLE001 - one failing city must not lose the others
            say(f"  ! {name} skipped: {type(e).__name__}: {e}")
    if not results:
        raise RuntimeError("Backtest produced no results")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": asdict(cfg),
        "pooled": pool(results, cfg),
        "cities": [{k: v for k, v in r.items() if k != "_boot"} for r in results],
        "notes": [
            "Only the satellite part of the score (built-up growth, night-light trend) is tested; OpenStreetMap signals have no historical data here.",
            f"All features use years up to {cfg.t0}; outcomes use {cfg.t0} to {cfg.future_end}.",
            "'Grew' means top-quartile built-up gain within the city. A lift of 1.0 means no better than choosing areas at random.",
            "Confidence intervals come from a cluster bootstrap over coarser H3 cells; they are approximate.",
            "Areas that grew are not the same as places where a business succeeds.",
        ],
    }
    if sensitivity is not None:
        say(f"\nSensitivity analysis: past {sensitivity.past_start}-{sensitivity.t0}, outcome {sensitivity.outcome_from}-{sensitivity.future_end}")
        sens = run(cities, sensitivity, None, say)  # satellite series are cached: no new Earth Engine calls
        report["sensitivity"] = {
            "description": (
                f"Same method with a gap year so the signal and the outcome share no data: scored on {sensitivity.past_start}-{sensitivity.t0}, "
                f"outcome measured {sensitivity.outcome_from}-{sensitivity.future_end}. Guards against noise in the as-of year pushing the signal and "
                "the outcome in opposite directions (regression to the mean)."
            ),
            "config": sens["config"], "pooled": sens["pooled"], "cities": sens["cities"],
        }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def markdown_table(report: dict) -> str:
    """README-ready summary of the report (primary design), with the gap-year check's top-10% lift when present."""
    sens = {c["city"]: c for c in report.get("sensitivity", {}).get("cities", [])}
    head = "| City | Areas | Base rate | Top 5% lift | **Top 10% lift** | Growth-only | Light-only | Room-to-grow | Rank corr. |"
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    if sens:
        head += " Gap-year check, top 10% |"
        sep += "---:|"
    lines = [head, sep]
    for c in report["cities"]:
        s = c["strategies"]
        row = (
            f"| {c['city'].split(',')[0]} | {c['n_areas']} | {c['base_rate_grew']:.0%} | "
            f"{s['product']['top5']['lift']:.2f} | **{s['product']['top10']['lift']:.2f}** | "
            f"{s['growth_only']['top10']['lift']:.2f} | {s['light_only']['top10']['lift']:.2f} | "
            f"{s['room_to_grow']['top10']['lift']:.2f} | {s['product']['spearman']:.2f} |"
        )
        if sens:
            sc = sens.get(c["city"])
            row += f" {sc['strategies']['product']['top10']['lift']:.2f} |" if sc else " - |"
        lines.append(row)
    pool = report["pooled"]
    p = pool["strategies"]["product"]
    avg = (
        f"| **Average ({pool['n_cities']} cities)** | | {pool['mean_base_rate_grew']:.0%} | "
        f"{p['top5']['mean_lift']:.2f} | **{p['top10']['mean_lift']:.2f}** | "
        f"{pool['strategies']['growth_only']['top10']['mean_lift']:.2f} | "
        f"{pool['strategies']['light_only']['top10']['mean_lift']:.2f} | "
        f"{pool['strategies']['room_to_grow']['top10']['mean_lift']:.2f} | {p['mean_spearman']:.2f} |"
    )
    if sens:
        avg += f" **{report['sensitivity']['pooled']['strategies']['product']['top10']['mean_lift']:.2f}** |"
    lines.append(avg)
    return "\n".join(lines)
