import type { Places } from "./types";

export interface NearbyPlace {
  name: string | null;
  kind?: string;
  distanceM: number;
}

export interface Nearby {
  competitors: NearbyPlace[];
  drivers: NearbyPlace[];
  radiusM: number;
}

export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dp = toRad(lat2 - lat1);
  const dl = toRad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/** Places within `radiusM` of a point, nearest first. Same radius as the backend's brief facts. */
export function nearbyPlaces(places: Places, lat: number, lon: number, radiusM = 1200): Nearby {
  const near = <T extends [number, number, ...unknown[]]>(items: T[], map: (p: T, d: number) => NearbyPlace) =>
    items
      .map((p) => map(p, Math.round(distanceM(lat, lon, p[0], p[1]))))
      .filter((p) => p.distanceM <= radiusM)
      .sort((a, b) => a.distanceM - b.distanceM);
  return {
    competitors: near(places.competitors, (p, d) => ({ name: p[2], distanceM: d })),
    drivers: near(places.drivers, (p, d) => ({ name: p[2], kind: p[3], distanceM: d })),
    radiusM,
  };
}

export function kindCounts(drivers: NearbyPlace[]): [string, number][] {
  const m = new Map<string, number>();
  for (const d of drivers) m.set(d.kind ?? "other", (m.get(d.kind ?? "other") ?? 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}
