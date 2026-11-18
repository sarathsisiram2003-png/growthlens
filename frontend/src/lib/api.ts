import type { AnalysisResult, Brief, CityOption, HistoryStatus, JobStatus } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 20_000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}${path}`, { ...init, signal: ctrl.signal });
    if (!res.ok) {
      let detail = "";
      try {
        const body = await res.json();
        detail = typeof body.detail === "string" ? body.detail : "";
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail || `The server returned an error (${res.status}).`, res.status);
    }
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError) throw e;
    throw new ApiError("Can't reach the GrowthLens server. Please check that the backend is running and try again.");
  } finally {
    clearTimeout(timer);
  }
}

export const createJob = (city: string, query: string) =>
  request<JobStatus>("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city, query }),
  });

export const cancelJob = (id: string) => request<JobStatus>(`/jobs/${id}/cancel`, { method: "POST" }, 10_000);

export const getJob = (id: string) => request<JobStatus>(`/jobs/${id}`);

// Results are a few hundred KB; allow more time.
export const getResult = (id: string) => request<AnalysisResult>(`/jobs/${id}/result`, undefined, 60_000);

interface GeoResult {
  name: string;
  admin1?: string;
  country?: string;
  latitude: number;
  longitude: number;
  feature_code?: string;
}

/**
 * Keep populated places (cities, towns, villages) and drop regions, countries and other features: analysing a whole
 * state or country isn't supported, so we don't offer them. Duplicate labels are removed.
 */
export function placesOnly(results: GeoResult[]): CityOption[] {
  const seen = new Set<string>();
  return results
    .filter((r) => !r.feature_code || r.feature_code.startsWith("PPL"))
    .map((r) => ({
      label: [r.name, r.admin1, r.country].filter(Boolean).join(", "),
      name: r.name,
      lat: r.latitude,
      lon: r.longitude,
    }))
    .filter((o) => {
      if (seen.has(o.label)) return false;
      seen.add(o.label);
      return true;
    });
}

/** City autocomplete via Open-Meteo's geocoder (built for search-as-you-type; Nominatim forbids it). */
export async function searchCities(q: string, signal?: AbortSignal): Promise<CityOption[]> {
  const url = `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=10&language=en&format=json`;
  const res = await fetch(url, { signal });
  if (!res.ok) return [];
  const data = (await res.json()) as { results?: GeoResult[] };
  return placesOnly(data.results ?? []).slice(0, 6);
}

export const getBrief = (resultId: string, hex: string) =>
  request<Brief>(`/results/${resultId}/brief/${hex}`, undefined, 90_000); // the LLM can be slow

export const startHistory = (resultId: string) =>
  request<HistoryStatus>(`/results/${resultId}/history`, { method: "POST" });

export const getHistory = (resultId: string) => request<HistoryStatus>(`/results/${resultId}/history`, undefined, 60_000);

export const getAreaName = (lat: number, lon: number) =>
  request<{ name: string | null }>(`/area-name?lat=${lat}&lon=${lon}`, undefined, 30_000);

export const imageryUrl = (hex: string, year: number) => `${API_URL}/imagery/${hex}?year=${year}`;
