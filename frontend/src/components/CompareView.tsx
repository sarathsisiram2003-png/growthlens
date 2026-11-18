"use client";

import { useEffect, useMemo, useRef } from "react";
import { Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useBrief } from "@/hooks/useBrief";
import { scoreColor } from "@/lib/colors";
import { explain, METRIC_TITLE } from "@/lib/explain";
import { neighbourhood, svgMap } from "@/lib/hexgeo";
import { METRICS, normaliseWeights } from "@/lib/scoring";
import type { AnalysisResult, ViewRow, Weights } from "@/lib/types";

function MiniMap({ hex, scores }: { hex: string; scores: Map<string, number> }) {
  const { cells, path } = useMemo(() => {
    const cells = neighbourhood(hex, 2);
    return { cells, path: svgMap(cells, 220, 170).path };
  }, [hex]);
  return (
    <svg viewBox="0 0 220 170" className="w-full rounded-lg bg-muted/60" role="img" aria-label="Neighbourhood map: the chosen area outlined, nearby areas coloured by score">
      {cells.map((c) => {
        const s = scores.get(c);
        const [r, g, b] = s === undefined ? [128, 128, 128] : scoreColor(s, 255);
        return <path key={c} d={path(c)} fill={`rgb(${r},${g},${b})`} fillOpacity={s === undefined ? 0.25 : 0.85} stroke="rgba(0,0,0,0.25)" strokeWidth={0.6} />;
      })}
      <path d={path(hex)} fill="none" stroke="white" strokeWidth={2.5} />
      <path d={path(hex)} fill="none" stroke="#0f172a" strokeWidth={1} />
    </svg>
  );
}

function BriefCell({ resultId, hex }: { resultId: string; hex: string }) {
  const { brief, loading, error, retry } = useBrief(resultId, hex);
  if (loading)
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden /> Writing brief…
      </p>
    );
  if (error)
    return (
      <p role="alert" className="text-sm text-muted-foreground">
        {error}{" "}
        <button className="min-h-11 text-primary underline" onClick={retry}>
          Try again
        </button>
      </p>
    );
  if (!brief) return null;
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      <p><span className="font-semibold">Why here. </span>{brief.why_here}</p>
      <p><span className="font-semibold">Risks. </span>{brief.risks}</p>
      <p><span className="font-semibold">Format. </span>{brief.suggested_format}</p>
    </div>
  );
}

interface Props {
  result: AnalysisResult;
  rows: ViewRow[]; // 2–3 areas
  weights: Weights;
  allScores: Map<string, number>; // hex -> 0..1 colour value for the mini maps
  onRemove: (hex: string) => void;
  onClose: () => void;
}

export default function CompareView({ result, rows, weights, allScores, onRemove, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const w = normaliseWeights(weights);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const bestScore = Math.max(...rows.map((r) => r.score));

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-0 md:items-center md:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Compare locations"
        className="glass flex max-h-[94dvh] w-full max-w-5xl flex-col rounded-t-2xl bg-background md:max-h-[88dvh] md:rounded-2xl"
        style={{ backdropFilter: "none", background: "var(--background)" }}
      >
        <header className="flex items-center justify-between gap-3 p-4 pb-2">
          <div>
            <h2 className="text-lg font-semibold">Compare {rows.length} locations</h2>
            <p className="text-sm text-muted-foreground">
              {result.label} in {result.city.name.split(",")[0]}. Percentiles are relative to this city; bold marks the strongest in each row.
            </p>
          </div>
          <Button ref={closeRef} variant="ghost" className="size-11 shrink-0" aria-label="Close comparison" onClick={onClose}>
            <X aria-hidden />
          </Button>
        </header>

        <div className="overflow-auto px-4 pb-4">
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(230px, 1fr))` }}>
            {rows.map((r) => (
              <article key={r.hex} aria-label={r.name} className="min-w-0 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="truncate font-semibold">{r.name}</h3>
                    <p className="text-sm text-muted-foreground">{r.rank ? `Rank #${r.rank}` : "Outside top 10"}</p>
                  </div>
                  <Button variant="ghost" className="size-11 shrink-0" aria-label={`Remove ${r.name} from comparison`} onClick={() => onRemove(r.hex)}>
                    <X aria-hidden />
                  </Button>
                </div>
                <MiniMap hex={r.hex} scores={allScores} />
                <p className={`text-3xl font-semibold tabular-nums ${r.score === bestScore ? "text-primary" : ""}`}>
                  {Math.round(r.score)}
                  <span className="text-base font-normal text-muted-foreground"> /100</span>
                </p>

                <dl className="divide-y divide-border text-sm">
                  {METRICS.map((m) => {
                    const e = explain(m, r, result.windows.growth);
                    const best = Math.max(...rows.map((x) => x.norm[m]));
                    const isBest = r.norm[m] === best && rows.length > 1 && rows.some((x) => x.norm[m] !== best);
                    return (
                      <div key={m} className={`py-2 ${isBest ? "font-semibold" : ""}`}>
                        <dt className="flex justify-between text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          <span>{METRIC_TITLE[m]}</span>
                          <span className="tabular-nums normal-case">weight {Math.round(w[m] * 100)}%</span>
                        </dt>
                        <dd className="mt-0.5">
                          {e.percentile !== null ? `${e.percentile}th percentile` : "No data"}
                          <span className="block text-xs font-normal text-muted-foreground">{e.headline}</span>
                        </dd>
                      </div>
                    );
                  })}
                </dl>

                <BriefCell resultId={result.id} hex={r.hex} />
              </article>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
