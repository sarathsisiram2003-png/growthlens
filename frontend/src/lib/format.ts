import type { Metric } from "./types";

export const METRIC_LABEL: Record<Metric, string> = {
  growth: "Growth",
  activity: "Night lights",
  demand: "Demand",
  competition: "Low competition",
  access: "Access",
};

export const FLAG_MESSAGE: Record<string, string> = {
  thin_osm_coverage: "OpenStreetMap coverage looks thin for this city, so competitor and demand counts may be incomplete.",
  satellite_unavailable: "Satellite data was unavailable, so this ranking uses map data only.",
  satellite_skipped: "Satellite data was skipped, so this ranking uses map data only.",
  growth_data_missing: "Satellite growth data is missing for many areas.",
  activity_data_missing: "Night-light data is missing for many areas.",
  intent_fallback_preset: "AI parsing was unavailable, so a standard profile for this business type was used.",
};
