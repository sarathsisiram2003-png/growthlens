import type { Geometry } from "geojson";

export type Metric = "growth" | "activity" | "demand" | "competition" | "access";

export interface HexRow {
  hex: string;
  lat: number;
  lon: number;
  score: number;
  rank: number | null;
  raw: Record<Metric, number | null>;
  /** Percentile within the city, 0–1. `competition` is inverted: higher = fewer competitors. */
  norm: Record<Metric, number>;
  name?: string;
  reason?: string;
}

export interface Tag {
  key: string;
  value: string;
}

export interface Intent {
  category_key: string;
  label: string;
  summary: string;
  competitors: Tag[];
  demand_drivers: (Tag & { weight: number })[];
  access: Tag[];
  weights: Record<Metric, number>;
  source: "llm" | "preset";
}

export interface AnalysisResult {
  city: {
    name: string;
    display_name: string;
    lat: number;
    lon: number;
    bbox: [number, number, number, number]; // minLon, minLat, maxLon, maxLat
    boundary: Geometry;
  };
  category: string;
  label: string;
  intent: Intent;
  weights: Record<Metric, number>;
  data_quality: { osm_coverage: number; n_competitors: number; flags: string[] };
  windows: { growth: [number, number]; viirs: [string, string] };
  disclaimer: string;
  generated_at: string;
  top10: string[];
  hexes: HexRow[];
}

export type StepState = "pending" | "active" | "done" | "error" | "skipped";

export interface JobStep {
  id: string;
  label: string;
  state: StepState;
}

export interface JobStatus {
  id: string;
  city: string;
  query: string;
  status: "queued" | "running" | "done" | "error";
  steps: JobStep[];
  message: string;
  intent: Intent | null;
  warning: string | null;
  meta: { boundary?: Geometry; center?: [number, number] };
  error: string | null;
}

export interface CityOption {
  label: string; // "Bengaluru, Karnataka, India" – sent to the backend as the search string
  name: string;
  lat: number;
  lon: number;
}
