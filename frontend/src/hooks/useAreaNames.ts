"use client";

import { useCallback, useEffect, useReducer } from "react";
import { getAreaName } from "@/lib/api";
import type { HexRow } from "@/lib/types";

// Only the original top 10 arrive named. When re-weighting surfaces other areas we look their names up
// lazily (one at a time: the backend/Nominatim allow ~1 request per second).
const names = new Map<string, string>();
const failed = new Set<string>();

export const fallbackName = (r: Pick<HexRow, "lat" | "lon">) => `Area near ${r.lat.toFixed(3)}, ${r.lon.toFixed(3)}`;

/**
 * Returns `nameOf(row)`. Its identity changes only when a new name arrives, so it is safe in memo dependencies.
 */
export function useAreaNames(top: HexRow[]) {
  const [version, bump] = useReducer((n: number) => n + 1, 0);
  const missing = top.filter((r) => !r.name && !names.has(r.hex) && !failed.has(r.hex));
  const sig = missing.map((r) => `${r.hex}|${r.lat}|${r.lon}`).join(",");

  useEffect(() => {
    if (!sig) return;
    let live = true;
    (async () => {
      for (const item of sig.split(",")) {
        if (!live) return;
        const [hex, lat, lon] = item.split("|");
        try {
          const { name } = await getAreaName(Number(lat), Number(lon));
          if (name) names.set(hex, name);
          else failed.add(hex);
        } catch {
          failed.add(hex); // keep the coordinate-based fallback; don't retry in a loop
        }
        if (live) bump();
      }
    })();
    return () => {
      live = false;
    };
  }, [sig]);

  // `version` is the intentional trigger: the lookup tables above are module-level, not React state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useCallback((r: HexRow) => r.name ?? names.get(r.hex) ?? fallbackName(r), [version]);
}
