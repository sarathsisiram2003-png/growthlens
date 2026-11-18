import type { Metric } from "./types";

export const METRIC_LABEL: Record<Metric, string> = {
  growth: "Growth",
  activity: "Night lights",
  demand: "Demand",
  competition: "Low competition",
  access: "Access",
};

export const FLAG_MESSAGE: Record<string, string> = {
  very_thin_osm: "OpenStreetMap has very little mapped data for this city, so treat this ranking as a rough guide only.",
  no_competitors_mapped: "No competitors are mapped in this city, so competition could not be compared. Check on the ground.",
  few_competitors: "Very few competitors are mapped, so the competition signal is weak.",
  osm_partial: "Part of this city's OpenStreetMap data could not be loaded, so some areas may be under-counted.",
  approximate_boundary: "No official boundary was found, so a circle around the place was used instead.",
  few_areas: "This area is small, so there are few areas to compare.",
  finer_grid: "A finer grid (smaller areas) was used because this place is small.",
  coarser_grid: "A coarser grid (larger areas) was used because this city is very large.",
  thin_osm_coverage: "OpenStreetMap coverage looks thin for this city, so competitor and demand counts may be incomplete.",
  satellite_unavailable: "Satellite data was unavailable, so this ranking uses map data only.",
  satellite_skipped: "Satellite data was skipped, so this ranking uses map data only.",
  growth_data_missing: "Satellite growth data is missing for many areas.",
  activity_data_missing: "Night-light data is missing for many areas.",
  intent_fallback_preset: "AI parsing was unavailable, so a standard profile for this business type was used.",
};

export const QUALITY_TITLE = { good: "Data quality: good", caution: "Data quality: check notes", limited: "Data quality: limited" } as const;
