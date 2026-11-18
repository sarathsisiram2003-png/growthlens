import type { Geometry, Position } from "geojson";

export type Bounds = [[number, number], [number, number]]; // [[west, south], [east, north]]

function walk(coords: unknown, visit: (p: Position) => void): void {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === "number") visit(coords as Position);
  else for (const c of coords) walk(c, visit);
}

/** Bounding box of any GeoJSON geometry, or null when it has no coordinates. */
export function geometryBounds(geom: Geometry | undefined | null): Bounds | null {
  if (!geom || geom.type === "GeometryCollection") return null;
  let w = Infinity;
  let s = Infinity;
  let e = -Infinity;
  let n = -Infinity;
  walk(geom.coordinates, ([x, y]) => {
    w = Math.min(w, x);
    e = Math.max(e, x);
    s = Math.min(s, y);
    n = Math.max(n, y);
  });
  return Number.isFinite(w) ? [[w, s], [e, n]] : null;
}
