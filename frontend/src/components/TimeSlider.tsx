"use client";

import { Loader2, Pause, Play, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  years: number[]; // empty until the history has loaded
  index: number;
  playing: boolean;
  state: "idle" | "running" | "done" | "error";
  progress: number;
  error?: string;
  onIndex: (i: number) => void;
  onPlay: () => void;
  onRetry: () => void;
}

export default function TimeSlider({ years, index, playing, state, progress, error, onIndex, onPlay, onRetry }: Props) {
  if (state === "error") {
    return (
      <div role="alert" className="rounded-xl border border-border bg-background/50 p-3 text-sm">
        <p className="font-medium">Growth replay unavailable</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{error ?? "Couldn't load the satellite history."} The map still shows overall growth.</p>
        <Button variant="outline" className="mt-2 h-11 px-3" onClick={onRetry}>
          <RotateCcw aria-hidden /> Try again
        </Button>
      </div>
    );
  }

  if (state !== "done" || years.length === 0) {
    return (
      <div role="status" className="rounded-xl border border-border bg-background/50 p-3 text-sm">
        <p className="flex items-center gap-2 font-medium">
          <Loader2 className="size-4 animate-spin text-primary" aria-hidden /> Loading growth replay…
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Reading yearly satellite history for this city. The first time takes a minute or two.
        </p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.max(6, progress * 100)}%` }} />
        </div>
      </div>
    );
  }

  const first = years[0];
  const last = years[years.length - 1];
  return (
    <section aria-label="Growth replay" className="rounded-xl border border-border bg-background/50 p-3">
      <div className="flex items-center gap-2">
        <Button variant="outline" className="size-11 shrink-0" aria-label={playing ? "Pause replay" : "Play replay"} onClick={onPlay}>
          {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-medium">Built-up growth since {first}</span>
            <span className="tabular-nums font-semibold" aria-live="polite">{years[index]}</span>
          </div>
          <input
            type="range"
            min={0}
            max={years.length - 1}
            step={1}
            value={index}
            aria-label="Year"
            aria-valuetext={String(years[index])}
            onChange={(e) => onIndex(Number(e.target.value))}
            className="h-11 w-full cursor-pointer accent-[var(--primary)]"
          />
          <div className="-mt-2 flex justify-between text-[11px] text-muted-foreground">
            <span>{first}</span>
            <span>{last}{last === new Date().getFullYear() ? " (so far)" : ""}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
