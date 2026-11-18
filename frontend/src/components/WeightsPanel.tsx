"use client";

import { useId, useState } from "react";
import { ChevronDown, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { METRIC_SHORT } from "@/lib/explain";
import { METRICS, normaliseWeights } from "@/lib/scoring";
import type { Weights } from "@/lib/types";

interface Props {
  weights: Weights; // raw slider values, 0–100
  changed: boolean;
  onChange: (w: Weights) => void;
  onReset: () => void;
}

export default function WeightsPanel({ weights, changed, onChange, onReset }: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const share = normaliseWeights(weights);

  return (
    <section aria-label="Adjust what matters" className="rounded-xl border border-border bg-background/50">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex h-11 w-full items-center justify-between rounded-xl px-3 text-sm font-medium focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span>
          What matters more to you?
          {changed && <span className="ml-2 rounded-full bg-primary/15 px-2 py-0.5 text-xs text-primary">adjusted</span>}
        </span>
        <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      </button>

      {open && (
        <div id={panelId} className="px-3 pb-3">
          {METRICS.map((m) => (
            <label key={m} className="block">
              <span className="flex justify-between text-xs">
                <span>{METRIC_SHORT[m]}</span>
                <span className="tabular-nums text-muted-foreground">{Math.round(share[m] * 100)}%</span>
              </span>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={weights[m]}
                onChange={(e) => onChange({ ...weights, [m]: Number(e.target.value) })}
                className="h-11 w-full cursor-pointer accent-[var(--primary)]"
              />
            </label>
          ))}
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs leading-snug text-muted-foreground">
              Re-ranks instantly. Scores stay relative to this city.
            </p>
            <Button variant="ghost" className="h-11 shrink-0 px-3" disabled={!changed} onClick={onReset}>
              <RotateCcw aria-hidden /> Reset
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
