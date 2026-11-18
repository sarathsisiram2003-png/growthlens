"use client";

import { useCallback, useEffect, useReducer } from "react";
import { ApiError, getBrief } from "@/lib/api";
import type { Brief } from "@/lib/types";

// Briefs are cached for the session: re-opening an area (or the report/compare views) is instant.
const cache = new Map<string, Brief>();
const errors = new Map<string, string>();
const inflight = new Map<string, Promise<void>>();

const keyOf = (resultId: string, hex: string) => `${resultId}:${hex}`;

export const getCachedBrief = (resultId: string, hex: string) => cache.get(keyOf(resultId, hex));

function load(resultId: string, hex: string): Promise<void> {
  const key = keyOf(resultId, hex);
  let p = inflight.get(key);
  if (!p) {
    p = getBrief(resultId, hex)
      .then((b) => void cache.set(key, b))
      .catch((e) => void errors.set(key, e instanceof ApiError ? e.message : "Couldn't load the brief."))
      .finally(() => void inflight.delete(key));
    inflight.set(key, p);
  }
  return p;
}

export function useBrief(resultId: string | null | undefined, hex: string | null | undefined) {
  const [, bump] = useReducer((n: number) => n + 1, 0);
  const key = resultId && hex ? keyOf(resultId, hex) : null;

  useEffect(() => {
    if (!resultId || !hex || !key || cache.has(key) || errors.has(key)) return;
    let live = true;
    void load(resultId, hex).then(() => live && bump());
    return () => {
      live = false;
    };
  }, [resultId, hex, key]);

  const retry = useCallback(() => {
    if (!key || !resultId || !hex) return;
    errors.delete(key);
    bump();
    void load(resultId, hex).then(bump);
  }, [key, resultId, hex]);

  const brief = key ? cache.get(key) : undefined;
  const error = key ? errors.get(key) : undefined;
  return { brief, error, loading: !!key && !brief && !error, retry };
}
