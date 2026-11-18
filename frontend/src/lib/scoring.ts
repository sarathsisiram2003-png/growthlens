import type { HexRow, Metric, Weights } from "./types";

export const METRICS: Metric[] = ["growth", "activity", "demand", "competition", "access"];

const EQUAL: Weights = { growth: 0.2, activity: 0.2, demand: 0.2, competition: 0.2, access: 0.2 };

/** Weights scaled to sum to 1. Negative values count as 0; all-zero falls back to equal weights. */
export function normaliseWeights(w: Weights): Weights {
  const clean = Object.fromEntries(METRICS.map((m) => [m, Math.max(0, Number.isFinite(w[m]) ? w[m] : 0)])) as Weights;
  const total = METRICS.reduce((a, m) => a + clean[m], 0);
  if (total <= 0) return { ...EQUAL };
  return Object.fromEntries(METRICS.map((m) => [m, clean[m] / total])) as Weights;
}

/**
 * Opportunity score 0–100. Mirrors backend/growthlens/scoring.py: weighted sum of city-relative percentile norms,
 * where `norm.competition` is already inverted (high = few competitors).
 */
export function scoreOf(row: Pick<HexRow, "norm">, weights: Weights): number {
  const w = normaliseWeights(weights);
  const s = 100 * METRICS.reduce((a, m) => a + w[m] * row.norm[m], 0);
  return Math.round(s * 100) / 100;
}

/** Re-score every area and recompute the top-N ranks (ties broken by hex id, like the backend). */
export function rerank(rows: HexRow[], weights: Weights, topN = 10): HexRow[] {
  const scored = rows.map((r) => ({ ...r, score: scoreOf(r, weights) }));
  const order = [...scored].sort((a, b) => b.score - a.score || (a.hex < b.hex ? -1 : 1));
  const rank = new Map(order.slice(0, topN).map((r, i) => [r.hex, i + 1]));
  return scored.map((r) => ({ ...r, rank: rank.get(r.hex) ?? null }));
}

export function topRows(rows: HexRow[]): HexRow[] {
  return rows.filter((r) => r.rank !== null).sort((a, b) => a.rank! - b.rank!);
}

export function weightsEqual(a: Weights, b: Weights): boolean {
  const x = normaliseWeights(a);
  const y = normaliseWeights(b);
  return METRICS.every((m) => Math.abs(x[m] - y[m]) < 1e-6);
}
