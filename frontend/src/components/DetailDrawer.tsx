"use client";

import { useEffect, useMemo, useRef } from "react";
import { FileDown, GitCompareArrows, Loader2, RotateCcw, Sparkles, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import BeforeAfter from "@/components/BeforeAfter";
import { useBrief } from "@/hooks/useBrief";
import { scoreColor } from "@/lib/colors";
import { explain, METRIC_TITLE } from "@/lib/explain";
import { kindCounts, nearbyPlaces } from "@/lib/nearby";
import { METRICS, normaliseWeights } from "@/lib/scoring";
import type { AnalysisResult, Metric, ViewRow, Weights } from "@/lib/types";

interface Props {
  result: AnalysisResult;
  row: ViewRow;
  weights: Weights; // current (raw) slider weights
  inCompare: boolean;
  compareFull: boolean;
  onToggleCompare: () => void;
  onExport: () => void;
  onClose: () => void;
}

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-border pt-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

function BreakdownRow({ metric, row, weight, window }: { metric: Metric; row: ViewRow; weight: number; window: [number, number] }) {
  const e = explain(metric, row, window);
  const [r, g, b] = scoreColor(row.norm[metric], 255);
  const points = 100 * weight * row.norm[metric];
  return (
    <li className="py-2">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{METRIC_TITLE[metric]}</span>
        <span className="tabular-nums text-xs text-muted-foreground" title="Points this signal adds to the 0–100 score at the current weights">
          +{points.toFixed(1)} pts · weight {Math.round(weight * 100)}%
        </span>
      </div>
      <div
        role="meter"
        aria-label={`${METRIC_TITLE[metric]} percentile in this city`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(row.norm[metric] * 100)}
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full" style={{ width: `${Math.max(3, row.norm[metric] * 100)}%`, background: `rgb(${r},${g},${b})` }} />
      </div>
      <p className="mt-1 text-sm">{e.headline}</p>
      <p className="text-xs text-muted-foreground">{e.context}</p>
    </li>
  );
}

export default function DetailDrawer({ result, row, weights, inCompare, compareFull, onToggleCompare, onExport, onClose }: Props) {
  const { brief, loading, error, retry } = useBrief(result.id, row.hex);
  const closeRef = useRef<HTMLButtonElement>(null);
  const w = normaliseWeights(weights);
  const [yBefore, yAfter] = result.windows.imagery ?? [2017, 2025];

  const near = useMemo(() => nearbyPlaces(result.places, row.lat, row.lon), [result.places, row.lat, row.lon]);
  const kinds = useMemo(() => kindCounts(near.drivers), [near.drivers]);

  useEffect(() => {
    closeRef.current?.focus();
  }, [row.hex]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-label={`Details for ${row.name}`}
      className="pointer-events-auto fixed inset-x-0 bottom-0 z-30 flex h-[88dvh] border border-border bg-background shadow-2xl flex-col rounded-t-2xl md:inset-x-auto md:bottom-3 md:right-3 md:top-[124px] md:h-auto md:w-[440px] md:rounded-2xl"
    >
      <header className="flex shrink-0 items-start gap-3 p-4 pb-3">
        <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-bold text-white ring-1 ring-white/40">
          {row.rank ?? "•"}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold leading-tight">{row.name}</h2>
          <p className="text-sm text-muted-foreground">
            Score <span className="font-semibold text-foreground tabular-nums">{Math.round(row.score)}</span>/100
            {row.rank ? ` · #${row.rank} in ${result.city.name.split(",")[0]}` : " · outside the current top 10"}
          </p>
        </div>
        <Button ref={closeRef} variant="ghost" className="size-11 shrink-0" aria-label="Close details" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 pb-4">
        <BeforeAfter key={row.hex} hex={row.hex} before={yBefore} after={yAfter} />

        <Section title="Why this score">
          <ul className="divide-y divide-border">
            {METRICS.map((m) => (
              <BreakdownRow key={m} metric={m} row={row} weight={w[m]} window={result.windows.growth} />
            ))}
          </ul>
          <p className="mt-1 text-xs text-muted-foreground">
            Bars show where this area ranks among all {result.hexes.length} areas in the city. Scores are relative and rank areas; they don&rsquo;t predict revenue.
          </p>
        </Section>

        <Section
          title="Location brief"
          aside={
            brief && (
              <span className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                <Sparkles className="size-3" aria-hidden /> {brief.source === "llm" ? "AI-written from the data above" : "Summary from the data"}
              </span>
            )
          }
        >
          {loading && (
            <div role="status" className="space-y-2" aria-label="Writing brief">
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Writing a brief for this area…
              </p>
              <div className="h-3 w-full animate-pulse rounded bg-muted" />
              <div className="h-3 w-5/6 animate-pulse rounded bg-muted" />
              <div className="h-3 w-4/6 animate-pulse rounded bg-muted" />
            </div>
          )}
          {error && (
            <div role="alert" className="text-sm">
              <p className="text-muted-foreground">{error}</p>
              <Button variant="outline" className="mt-2 h-11 px-3" onClick={retry}>
                <RotateCcw aria-hidden /> Try again
              </Button>
            </div>
          )}
          {brief && (
            <dl className="space-y-3 text-sm leading-relaxed">
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Why here</dt>
                <dd>{brief.why_here}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Risks</dt>
                <dd>{brief.risks}</dd>
              </div>
              <div>
                <dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Suggested format</dt>
                <dd>{brief.suggested_format}</dd>
              </div>
            </dl>
          )}
        </Section>

        <Section title={`Nearby competitors (${near.competitors.length})`}>
          {near.competitors.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              None mapped within {near.radiusM / 1000} km. That can mean a real gap or thin OpenStreetMap data, so check on the ground.
            </p>
          ) : (
            <ul className="divide-y divide-border text-sm">
              {near.competitors.slice(0, 8).map((c, i) => (
                <li key={i} className="flex justify-between gap-2 py-1.5">
                  <span className="truncate">{c.name ?? "Unnamed place"}</span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">{c.distanceM} m</span>
                </li>
              ))}
            </ul>
          )}
          {near.competitors.length > 8 && <p className="mt-1 text-xs text-muted-foreground">Showing the 8 nearest.</p>}
        </Section>

        <Section title="Demand drivers nearby">
          {kinds.length === 0 ? (
            <p className="text-sm text-muted-foreground">None mapped within {near.radiusM / 1000} km.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {kinds.slice(0, 8).map(([kind, n]) => (
                <span key={kind} className="rounded-full border border-border px-2.5 py-1 text-xs">
                  {n} {kind}
                </span>
              ))}
            </div>
          )}
          <p className="mt-2 text-xs text-muted-foreground">Within {near.radiusM / 1000} km. From OpenStreetMap, which can be incomplete.</p>
        </Section>
      </div>

      <footer className="flex shrink-0 gap-2 border-t border-border p-3">
        <Button
          variant={inCompare ? "secondary" : "default"}
          className="h-11 flex-1"
          disabled={!inCompare && compareFull}
          onClick={onToggleCompare}
        >
          <GitCompareArrows aria-hidden />
          {inCompare ? "Remove from compare" : compareFull ? "Compare is full (3)" : "Add to compare"}
        </Button>
        <Button variant="outline" className="h-11 px-4" onClick={onExport}>
          <FileDown aria-hidden /> Export
        </Button>
      </footer>
    </aside>
  );
}
