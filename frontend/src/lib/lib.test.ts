import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { latLngToCell } from "h3-js";
import { distanceM, kindCounts, nearbyPlaces } from "./nearby";
import { buildReason } from "./reasons";
import { METRICS, normaliseWeights, rerank, scoreOf, topRows, weightsEqual } from "./scoring";
import { svgMap, neighbourhood } from "./hexgeo";
import type { HexRow, Weights } from "./types";

const W = (o: Partial<Weights> = {}): Weights => ({ growth: 1, activity: 1, demand: 1, competition: 1, access: 1, ...o });
const row = (hex: string, norm: Partial<HexRow["norm"]> = {}): HexRow => ({
  hex, lat: 0, lon: 0, score: 0, rank: null,
  raw: { growth: 0, activity: 0, demand: 0, competition: 0, access: 0 },
  norm: { growth: 0.5, activity: 0.5, demand: 0.5, competition: 0.5, access: 0.5, ...norm },
});

describe("scoring", () => {
  it("normalises weights to sum to 1", () => {
    const n = normaliseWeights(W({ growth: 3, demand: 1, activity: 0, competition: 0, access: 0 }));
    expect(METRICS.reduce((a, m) => a + n[m], 0)).toBeCloseTo(1);
    expect(n.growth).toBeCloseTo(0.75);
  });

  it("falls back to equal weights when all zero or invalid", () => {
    const zero = normaliseWeights(W({ growth: 0, activity: 0, demand: 0, competition: 0, access: 0 }));
    expect(zero.growth).toBeCloseTo(0.2);
    expect(normaliseWeights(W({ growth: NaN, activity: -5 })).demand).toBeGreaterThan(0);
  });

  it("score is bounded 0-100", () => {
    expect(scoreOf(row("a", { growth: 0, activity: 0, demand: 0, competition: 0, access: 0 }), W())).toBe(0);
    expect(scoreOf(row("a", { growth: 1, activity: 1, demand: 1, competition: 1, access: 1 }), W())).toBe(100);
  });

  it("changing weights changes the ranking", () => {
    const rows = [row("a", { growth: 0.9, demand: 0.1 }), row("b", { growth: 0.1, demand: 0.9 })];
    const only = (m: keyof Weights): Weights => ({ growth: 0, activity: 0, demand: 0, competition: 0, access: 0, [m]: 1 });
    expect(topRows(rerank(rows, only("growth"), 1))[0].hex).toBe("a");
    expect(topRows(rerank(rows, only("demand"), 1))[0].hex).toBe("b");
  });

  it("ranks exactly topN and breaks ties by hex id", () => {
    const rows = ["c", "a", "b", "d"].map((h) => row(h));
    const out = rerank(rows, W(), 3);
    expect(out.filter((r) => r.rank !== null)).toHaveLength(3);
    expect(topRows(out).map((r) => r.hex)).toEqual(["a", "b", "c"]);
  });

  it("does not mutate its input", () => {
    const rows = [row("a")];
    rerank(rows, W({ growth: 5 }));
    expect(rows[0].score).toBe(0);
  });

  it("weightsEqual ignores scale", () => {
    expect(weightsEqual(W(), W({ growth: 7, activity: 7, demand: 7, competition: 7, access: 7 }))).toBe(true);
    expect(weightsEqual(W(), W({ growth: 2 }))).toBe(false);
  });

  // Parity with the Python pipeline: re-scoring the saved Bengaluru result with its own weights must
  // reproduce the backend's scores and top 10 (this file is committed from Phase 1).
  it("matches the backend's scores and ranking on real Bengaluru data", () => {
    const file = path.resolve(__dirname, "../../../backend/data/output/bengaluru_cafe.json");
    const data = JSON.parse(readFileSync(file, "utf8")) as { weights: Weights; hexes: HexRow[]; top10: string[] };
    const out = rerank(data.hexes, data.weights);
    expect(out.length).toBeGreaterThan(500);
    const maxDiff = Math.max(...out.map((r, i) => Math.abs(r.score - data.hexes[i].score)));
    expect(maxDiff).toBeLessThanOrEqual(0.011); // rounding-mode difference only
    expect(topRows(out).map((r) => r.hex)).toEqual(data.top10);
  });
});

describe("reasons", () => {
  it("lists the strongest signals, capitalised", () => {
    const r = buildReason({ norm: { growth: 0.95, demand: 0.9, activity: 0.4, competition: 0.8, access: 0.5 }, raw: { growth: 0, activity: 0, demand: 0, competition: 3, access: 0 } });
    expect(r.startsWith("Fast-growing built-up area, strong demand drivers nearby")).toBe(true);
    expect(r.endsWith(".")).toBe(true);
  });
  it("says 'no mapped competitors' for zero", () => {
    const r = buildReason({ norm: row("x", { competition: 1 }).norm, raw: { ...row("x").raw, competition: 0 } });
    expect(r.toLowerCase()).toContain("no mapped competitors");
  });
  it("balanced and cautions", () => {
    expect(buildReason(row("x"))).toBe("Balanced profile across all signals.");
    expect(buildReason(row("x", { competition: 0.1, growth: 0.9 }))).toContain("crowded with competitors");
  });
});

describe("nearby", () => {
  it("haversine is about right (1 degree latitude ~ 111 km)", () => {
    expect(distanceM(0, 0, 1, 0)).toBeGreaterThan(110000);
    expect(distanceM(0, 0, 1, 0)).toBeLessThan(112000);
  });
  it("filters by radius, sorts nearest first, labels kinds", () => {
    const places = {
      competitors: [[13.001, 77.5, "Near"], [13.0, 77.5, "Nearest"], [14, 78, "Far"]] as [number, number, string | null][],
      drivers: [[13.0005, 77.5, null, "college"], [13.0006, 77.5, "X", "college"], [13.0007, 77.5, null, "office"]] as [number, number, string | null, string][],
    };
    const n = nearbyPlaces(places, 13.0, 77.5);
    expect(n.competitors.map((c) => c.name)).toEqual(["Nearest", "Near"]);
    expect(kindCounts(n.drivers)).toEqual([["college", 2], ["office", 1]]);
  });
});

describe("hexgeo", () => {
  it("builds closed SVG paths inside the viewport", () => {
    const c = latLngToCell(13, 77.5, 8);
    const cells = neighbourhood(c, 2);
    expect(cells).toHaveLength(19);
    const { path, project } = svgMap(cells, 200, 160);
    expect(path(c)).toMatch(/^M[\d. ]+(L[\d. ]+){5}Z$/); // hexagon: M + 5 L + Z
    const [x, y] = project(13, 77.5);
    expect(x).toBeGreaterThan(0); expect(x).toBeLessThan(200);
    expect(y).toBeGreaterThan(0); expect(y).toBeLessThan(160);
  });
});

import { explain } from "./explain";

describe("explain", () => {
  const base = (raw: Partial<HexRow["raw"]>, norm: Partial<HexRow["norm"]> = {}) => ({
    raw: { growth: 0.077, activity: 4.44, demand: 26, competition: 0, access: 2, ...raw },
    norm: { growth: 0.91, activity: 0.62, demand: 0.8, competition: 0.95, access: 0.5, ...norm },
  });
  it("describes growth in percentage points with the window", () => {
    const e = explain("growth", base({}), [2021, 2024]);
    expect(e.headline).toBe("+7.7 points of built-up area (2021–2024)");
    expect(e.percentile).toBe(91);
  });
  it("handles negative growth and missing satellite data", () => {
    expect(explain("growth", base({ growth: -0.031 })).headline).toContain("−3.1");
    const m = explain("growth", base({ growth: null }));
    expect(m.percentile).toBeNull();
    expect(m.headline).toMatch(/No satellite/);
    expect(explain("activity", base({ activity: null })).percentile).toBeNull();
  });
  it("never says 'more than 100%' for the top area", () => {
    expect(explain("growth", base({}, { growth: 1 })).context).toBe("Grew faster than every other area in this city.");
    expect(explain("demand", base({}, { demand: 1 })).context).toContain("than any other area");
    for (const m of ["growth", "activity", "demand", "competition", "access"] as const)
      expect(explain(m, base({}, { [m]: 1 })).context).not.toMatch(/100%/);
  });
  it("labels dimming night lights", () => {
    expect(explain("activity", base({ activity: -2 })).context).toContain("Dimming");
  });
  it("warns that zero competitors may be thin data, and pluralises", () => {
    expect(explain("competition", base({ competition: 0 })).context).toContain("thin map data");
    expect(explain("competition", base({ competition: 1 })).headline).toBe("1 competitor mapped in this area");
    expect(explain("access", base({ access: 3 })).headline).toBe("3 transit stops mapped in this area");
  });
});
