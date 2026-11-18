"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, cancelJob, createJob, getJob, getResult } from "@/lib/api";
import type { AnalysisResult, JobStatus } from "@/lib/types";

export type Phase = "start" | "analysing" | "results" | "error";

const POLL_MS = 1200;
const MAX_POLL_FAILURES = 8; // with backoff below this rides out a server restart (~40 s)
const MAX_BACKOFF_MS = 6000;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useAnalysis() {
  const [phase, setPhase] = useState<Phase>("start");
  const [job, setJob] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const runId = useRef(0); // invalidates in-flight polling when the user starts over
  const jobId = useRef<string | null>(null); // the server-side job we are waiting on, if any

  /** Tell the server we no longer need the running analysis (it only stops if nobody else shares it). */
  const abandonJob = useCallback(() => {
    const id = jobId.current;
    jobId.current = null;
    if (id) void cancelJob(id).catch(() => undefined); // best effort: the job also expires on its own
  }, []);

  useEffect(
    () => () => {
      runId.current += 1;
    },
    [],
  );

  const start = useCallback(async (city: string, query: string) => {
    abandonJob(); // a previous search that is still running is no longer wanted
    const mine = ++runId.current;
    const live = () => runId.current === mine;
    setPhase("analysing");
    setError(null);
    setResult(null);
    setJob(null);
    try {
      let status = await createJob(city, query);
      jobId.current = status.id;
      if (!live()) return abandonJob();
      setJob(status);
      let failures = 0;
      while (status.status === "queued" || status.status === "running") {
        await sleep(failures ? Math.min(POLL_MS * 2 ** failures, MAX_BACKOFF_MS) : POLL_MS);
        if (!live()) return;
        try {
          status = await getJob(status.id);
          failures = 0;
        } catch (e) {
          // 404 = the job expired; otherwise tolerate network blips and restarts (jobs resume after a restart)
          if ((e instanceof ApiError && e.status === 404) || ++failures >= MAX_POLL_FAILURES) throw e;
          continue;
        }
        if (!live()) return;
        setJob(status);
      }
      jobId.current = null; // finished: nothing left to cancel
      if (status.status === "error") throw new ApiError(status.error ?? "The analysis failed.");
      if (status.status === "cancelled") throw new ApiError("This search was cancelled. Please try again.");
      const data = await getResult(status.id);
      if (!live()) return;
      setResult(data);
      setPhase("results");
    } catch (e) {
      if (!live()) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      setPhase("error");
    }
  }, [abandonJob]);

  const reset = useCallback(() => {
    abandonJob();
    runId.current += 1;
    setPhase("start");
    setJob(null);
    setResult(null);
    setError(null);
  }, [abandonJob]);

  return { phase, job, result, error, start, reset };
}
