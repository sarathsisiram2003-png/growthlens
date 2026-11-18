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

export type Weights = Record<Metric, number>;
export type Layer = "opportunity" | "growth" | "activity" | "competitors" | "demand";

/** Compact place lists: [lat, lon, name] for competitors, [lat, lon, name, kind] for demand drivers. */
export interface Places {
  competitors: [number, number, string | null][];
  drivers: [number, number, string | null, string][];
}

export interface AnalysisResult {
  id: string;
  schema: number;
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
  windows: { growth: [number, number]; viirs: [string, string]; imagery?: [number, number] };
  disclaimer: string;
  generated_at: string;
  top10: string[];
  places: Places;
  hexes: HexRow[];
}

export interface Brief {
  why_here: string;
  risks: string;
  suggested_format: string;
  source: "llm" | "template";
}

export interface HistoryStatus {
  state: "idle" | "running" | "done" | "error";
  progress?: number;
  error?: string;
  data?: { years: number[]; values: Record<string, (number | null)[]> };
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
  result_id: string | null;
}

export interface CityOption {
  label: string; // "Bengaluru, Karnataka, India" – sent to the backend as the search string
  name: string;
  lat: number;
  lon: number;
}

/** An area as shown in the UI: re-scored for the current weights, always with a display name. */
export type ViewRow = HexRow & { name: string; reason?: string };
