"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getHistory, startHistory } from "@/lib/api";
import type { HistoryStatus } from "@/lib/types";

type HistoryData = NonNullable<HistoryStatus["data"]>;
const cache = new Map<string, HistoryData>(); // per result id, for the session

const POLL_MS = 2500;
const msg = (e: unknown) => (e instanceof ApiError ? e.message : "Growth history is unavailable right now.");

/**
 * Yearly built-up history for the time slider. Starts the backend computation the first time it is enabled
 * (it can take a minute for a new city) and polls until done. Data is cached per result.
 */
export function useHistory(resultId: string | null | undefined, enabled: boolean) {
  const [status, setStatus] = useState<HistoryStatus | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled || !resultId || cache.has(resultId)) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const s = await getHistory(resultId);
        if (!live) return;
        if (s.state === "done" && s.data) cache.set(resultId, s.data);
        setStatus(s);
        if (s.state === "running" || s.state === "idle") timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (live) setStatus({ state: "error", error: msg(e) });
      }
    };

    (async () => {
      try {
        await startHistory(resultId);
        if (live) void poll();
      } catch (e) {
        if (live) setStatus({ state: "error", error: msg(e) });
      }
    })();

    return () => {
      live = false;
      if (timer) clearTimeout(timer);
    };
  }, [enabled, resultId, attempt]);

  const retry = useCallback(() => {
    setStatus(null);
    setAttempt((n) => n + 1);
  }, []);

  const data = resultId ? cache.get(resultId) : undefined;
  return {
    data,
    state: data ? ("done" as const) : (status?.state ?? (enabled ? ("running" as const) : ("idle" as const))),
    progress: status?.progress ?? 0,
    error: status?.state === "error" ? status.error : undefined,
    retry,
  };
}
