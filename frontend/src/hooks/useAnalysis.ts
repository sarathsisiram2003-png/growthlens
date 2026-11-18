"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createJob, getJob, getResult } from "@/lib/api";
import type { AnalysisResult, JobStatus } from "@/lib/types";

export type Phase = "start" | "analysing" | "results" | "error";

const POLL_MS = 1200;
const MAX_POLL_FAILURES = 5;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useAnalysis() {
  const [phase, setPhase] = useState<Phase>("start");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const runId = useRef(0); // invalidates in-flight polling when the user starts over

  useEffect(
    () => () => {
      runId.current += 1;
    },
    [],
  );

  const start = useCallback(async (city: string, query: string) => {
    const mine = ++runId.current;
    const live = () => runId.current === mine;
    setPhase("analysing");
    setError(null);
    setResult(null);
    setJob(null);
    try {
      let status = await createJob(city, query);
      if (!live()) return;
      setJob(status);
      let failures = 0;
      while (status.status === "queued" || status.status === "running") {
        await sleep(POLL_MS);
        if (!live()) return;
        try {
          status = await getJob(status.id);
          failures = 0;
        } catch (e) {
          // 404 = server restarted and forgot the job; otherwise tolerate brief network blips
          if ((e instanceof ApiError && e.status === 404) || ++failures >= MAX_POLL_FAILURES) throw e;
          continue;
        }
        if (!live()) return;
        setJob(status);
      }
      if (status.status === "error") throw new ApiError(status.error ?? "The analysis failed.");
      const data = await getResult(status.id);
      if (!live()) return;
      setResult(data);
      setPhase("results");
    } catch (e) {
      if (!live()) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setPhase("error");
    }
  }, []);

  const reset = useCallback(() => {
    runId.current += 1;
    setPhase("start");
    setJob(null);
    setResult(null);
    setError(null);
  }, []);

  return { phase, job, result, error, start, reset };
}
