import { cellToBoundary, gridDisk } from "h3-js";

/** Equirectangular SVG projection fitted to a set of hexes (good enough at city scale). */
export function svgMap(cells: string[], width: number, height: number, pad = 6) {
  const polys = cells.map((c) => cellToBoundary(c)); // [lat, lng][]
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const p of polys) for (const [lat, lng] of p) {
    minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
    minLng = Math.min(minLng, lng); maxLng = Math.max(maxLng, lng);
  }
  const k = Math.cos((((minLat + maxLat) / 2) * Math.PI) / 180); // shrink longitude with latitude
  const w = (maxLng - minLng) * k || 1e-9;
  const h = maxLat - minLat || 1e-9;
  const scale = Math.min((width - 2 * pad) / w, (height - 2 * pad) / h);
  const ox = (width - w * scale) / 2;
  const oy = (height - h * scale) / 2;
  const project = (lat: number, lng: number): [number, number] => [
    ox + (lng - minLng) * k * scale,
    oy + (maxLat - lat) * scale,
  ];
  const path = (cell: string) =>
    cellToBoundary(cell)
      .map(([lat, lng]) => project(lat, lng))
      .map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`)
      .join("") + "Z";
  return { path, project };
}

/** The hex and its neighbours within k rings (for compare-view mini maps). */
export const neighbourhood = (cell: string, k = 2): string[] => gridDisk(cell, k);
