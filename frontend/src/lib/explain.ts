import type { HexRow, Metric } from "./types";

export const METRIC_TITLE: Record<Metric, string> = {
  growth: "Growth",
  activity: "Night lights",
  demand: "Demand drivers",
  competition: "Competition",
  access: "Access",
};

/** Short label for weight sliders / compact UI. */
export const METRIC_SHORT: Record<Metric, string> = {
  growth: "Growth",
  activity: "Night lights",
  demand: "Demand",
  competition: "Few competitors",
  access: "Access",
};

const pct = (n: number) => Math.round(n * 100);
/** "more than 91% of areas", or "every other area" at the very top (never "more than 100%"). */
const ahead = (p: number, everyOther: string, partial: (n: number) => string) => (p >= 0.995 ? everyOther : partial(pct(p)));
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export interface Explanation {
  /** The raw number in plain words, e.g. "+7.7 points of built-up area (2021–2024)". */
  headline: string;
  /** Where that sits relative to the rest of the city. */
  context: string;
  /** City-relative percentile 0–100 (for competition: higher = fewer competitors). */
  percentile: number | null;
}

export function explain(
  metric: Metric,
  row: Pick<HexRow, "raw" | "norm">,
  growthWindow: [number, number] = [2021, 2024],
): Explanation {
  const raw = row.raw[metric];
  const p = row.norm[metric];
  switch (metric) {
    case "growth":
      if (raw === null) return { headline: "No satellite growth data for this area.", context: "Scored as average.", percentile: null };
      return {
        headline: `${raw >= 0 ? "+" : "−"}${Math.abs(raw * 100).toFixed(1)} points of built-up area (${growthWindow[0]}–${growthWindow[1]})`,
        context: ahead(p, "Grew faster than every other area in this city.", (n) => `Grew more than ${n}% of areas in this city.`),
        percentile: pct(p),
      };
    case "activity":
      if (raw === null) return { headline: "No night-light data for this area.", context: "Scored as average.", percentile: null };
      return {
        headline: `Night-light trend ${raw >= 0 ? "+" : "−"}${Math.abs(raw).toFixed(1)} nW/cm²/sr per year`,
        context: ahead(p, `${raw >= 0 ? "Brightening" : "Dimming"} faster than every other area.`, (n) => `${raw >= 0 ? "Brightening" : "Dimming"} faster than ${n}% of areas.`),
        percentile: pct(p),
      };
    case "demand":
      return {
        headline: `${raw === 0 ? "No" : raw} weighted demand-driver ${raw === 1 ? "point" : "points"} mapped here`,
        context: ahead(p, "More demand drivers than any other area (colleges, offices and similar count more).", (n) => `More than ${n}% of areas (colleges, offices and similar count more).`),
        percentile: pct(p),
      };
    case "competition":
      return {
        headline: raw === 0 ? "No competitors mapped in this area" : `${plural(raw ?? 0, "competitor")} mapped in this area`,
        context: ahead(p, "Among the areas with the fewest competitors. Zero can also mean thin map data.", (n) => `Fewer competitors than ${n}% of areas. Zero can also mean thin map data.`),
        percentile: pct(p),
      };
    case "access":
      return {
        headline: `${plural(raw ?? 0, "transit stop")} mapped in this area`,
        context: ahead(p, "Better connected than every other area.", (n) => `Better connected than ${n}% of areas.`),
        percentile: pct(p),
      };
  }
}
