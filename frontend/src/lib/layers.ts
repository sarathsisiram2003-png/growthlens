import type { HexRow, Layer } from "./types";

export const LAYERS: { id: Layer; label: string; legend: [string, string]; help: string }[] = [
  { id: "opportunity", label: "Opportunity", legend: ["Lower", "Higher"], help: "Overall score for your business, relative to this city." },
  { id: "growth", label: "Growth", legend: ["Less growth", "More growth"], help: "Change in built-up area from satellite data (Dynamic World)." },
  { id: "activity", label: "Night lights", legend: ["Dimming", "Brightening"], help: "Trend in night-time light (NASA/NOAA VIIRS), a proxy for activity." },
  { id: "competitors", label: "Competitors", legend: ["Fewer", "More"], help: "Where same-category places are concentrated (OpenStreetMap)." },
  { id: "demand", label: "Demand drivers", legend: ["Fewer", "More"], help: "Where places that bring customers are concentrated (OpenStreetMap)." },
];

/**
 * 0–1 value used to colour an area on the given layer. Non-opportunity layers use the city-relative percentile
 * already computed by the backend (`competitors` flips the inverted competition norm back).
 */
export function layerValue(layer: Layer, row: HexRow, score: { min: number; span: number }): number {
  switch (layer) {
    case "opportunity":
      return (row.score - score.min) / score.span;
    case "growth":
      return row.norm.growth;
    case "activity":
      return row.norm.activity;
    case "competitors":
      return 1 - row.norm.competition;
    case "demand":
      return row.norm.demand;
  }
}
