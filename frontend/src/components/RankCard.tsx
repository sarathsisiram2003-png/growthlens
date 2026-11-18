"use client";

import { forwardRef, useId } from "react";
import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { scoreColor } from "@/lib/colors";
import { METRIC_LABEL } from "@/lib/format";
import type { Metric, ViewRow } from "@/lib/types";

const BARS: Metric[] = ["growth", "demand", "competition"];

function MiniBar({ metric, value }: { metric: Metric; value: number }) {
  const [r, g, b] = scoreColor(value, 255);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-[104px] shrink-0 whitespace-nowrap text-muted-foreground">{METRIC_LABEL[metric]}</span>
      <div
        role="meter"
        aria-label={METRIC_LABEL[metric]}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(value * 100)}
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full" style={{ width: `${Math.max(4, value * 100)}%`, background: `rgb(${r},${g},${b})` }} />
      </div>
    </div>
  );
}

interface Props {
  row: ViewRow;
  selected: boolean;
  hovered: boolean;
  onSelect: () => void;
  onHover: (on: boolean) => void;
  onDetails: () => void;
}

const RankCard = forwardRef<HTMLButtonElement, Props>(function RankCard(
  { row, selected, hovered, onSelect, onHover, onDetails },
  ref,
) {
  const reasonId = useId();
  return (
    <div
      className={`rounded-xl border transition-colors ${
        selected
          ? "border-primary bg-primary/10"
          : hovered
            ? "border-orange-400/70 bg-muted/60"
            : "border-border bg-background/50 hover:bg-muted/50"
      }`}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <button
        ref={ref}
        type="button"
        aria-pressed={selected}
        aria-label={`${row.rank ? `Rank ${row.rank}: ` : "Selected area: "}${row.name}, score ${Math.round(row.score)} out of 100`}
        aria-describedby={row.reason ? reasonId : undefined}
        onClick={onSelect}
        onFocus={() => onHover(true)}
        onBlur={() => onHover(false)}
        className="w-full rounded-t-xl p-3 pb-1 text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-bold text-white ring-1 ring-white/40"
          >
            {row.rank ?? "•"}
          </span>
          <span className="min-w-0 flex-1 truncate font-medium">{row.name}</span>
          <span className="shrink-0 text-right">
            <span className="text-lg font-semibold tabular-nums">{Math.round(row.score)}</span>
            <span className="text-xs text-muted-foreground">/100</span>
          </span>
        </div>
        <div className="mt-2.5 space-y-1.5">
          {BARS.map((m) => (
            <MiniBar key={m} metric={m} value={row.norm[m]} />
          ))}
        </div>
        {row.reason && (
          <p id={reasonId} className="mt-2.5 text-sm leading-snug text-muted-foreground">
            {row.reason}
          </p>
        )}
      </button>
      <div className="flex justify-end px-2 pb-1">
        <Button variant="ghost" className="h-11 px-3" aria-label={`Details for ${row.name}`} onClick={onDetails}>
          Details <ChevronRight aria-hidden />
        </Button>
      </div>
    </div>
  );
});

export default RankCard;
