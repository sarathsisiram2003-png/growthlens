"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Circle, Loader2, Minus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Intent, JobStatus, StepState } from "@/lib/types";

const human = (t: { key: string; value: string }) => (t.value || t.key).replace(/_/g, " ");
const list = (items: { key: string; value: string }[], n = 4) =>
  [...new Set(items.map(human))].slice(0, n).join(", ");

function Understood({ intent }: { intent: Intent }) {
  const demand = list([...intent.demand_drivers].sort((a, b) => b.weight - a.weight));
  return (
    <div className="mt-4 rounded-xl border border-border bg-background/50 p-3 text-sm">
      <p className="font-medium">What we understood</p>
      <p className="mt-1 leading-relaxed text-muted-foreground">
        <span className="text-foreground">Category:</span> {intent.label.toLowerCase()} ·{" "}
        <span className="text-foreground">Competitors:</span> {list(intent.competitors)} ·{" "}
        <span className="text-foreground">Demand:</span> {demand}
      </p>
    </div>
  );
}

function StepIcon({ state }: { state: StepState }) {
  const cls = "size-5 shrink-0";
  switch (state) {
    case "done":
      return <Check className={`${cls} text-primary`} aria-hidden />;
    case "active":
      return <Loader2 className={`${cls} animate-spin text-primary`} aria-hidden />;
    case "error":
      return <X className={`${cls} text-destructive`} aria-hidden />;
    case "skipped":
      return <Minus className={`${cls} text-muted-foreground`} aria-hidden />;
    default:
      return <Circle className={`${cls} text-muted-foreground/40`} aria-hidden />;
  }
}

const STATE_TEXT: Record<StepState, string> = {
  done: "done",
  active: "in progress",
  error: "failed",
  skipped: "skipped",
  pending: "waiting",
};

/** Appears when one step runs long, so a busy public data server doesn't look like a frozen app. */
function SlowHint() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 40_000);
    return () => clearTimeout(t);
  }, []);
  if (!slow) return null;
  return (
    <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
      This step is taking longer than usual. Public map data servers can be busy, so we&rsquo;ll keep trying.
    </p>
  );
}

interface Props {
  job: JobStatus | null;
  city: string;
  onEdit: () => void;
}

export default function AnalysingPanel({ job, city, onEdit }: Props) {
  const steps = job?.steps ?? [];
  return (
    <aside
      aria-label="Analysis progress"
      className="glass pointer-events-auto absolute inset-x-3 bottom-3 z-10 rounded-2xl p-4 sm:p-5 md:inset-x-auto md:bottom-auto md:left-4 md:top-[76px] md:w-[400px]"
    >
      <h2 className="text-lg font-semibold">Analysing {city.split(",")[0]}…</h2>
      <p className="text-sm text-muted-foreground">A new city can take a minute or two. Repeat searches are instant.</p>

      <ol className="mt-4 space-y-2.5" role="status" aria-live="polite">
        {(steps.length ? steps : placeholderSteps()).map((s) => (
          <li key={s.id} className="flex items-center gap-3 text-sm">
            <StepIcon state={s.state} />
            <span className={s.state === "pending" ? "text-muted-foreground" : "font-medium"}>{s.label}</span>
            <span className="sr-only">{STATE_TEXT[s.state]}</span>
          </li>
        ))}
      </ol>
      {job?.status === "queued" && (
        <p role="status" className="mt-3 text-xs text-muted-foreground">
          {job.queue_position
            ? `Waiting for a free worker. You are number ${job.queue_position} in line.`
            : "Waiting for a free worker…"}
        </p>
      )}
      {job?.message && job.status !== "queued" && <p className="mt-3 truncate text-xs text-muted-foreground">{job.message}</p>}
      <SlowHint key={steps.find((s) => s.state === "active")?.id ?? "none"} />

      {job?.intent && <Understood intent={job.intent} />}
      {job?.warning && (
        <p className="mt-3 flex items-start gap-2 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {job.warning}
        </p>
      )}

      <Button variant="ghost" className="mt-4 h-11 px-3" onClick={onEdit}>
        Cancel and edit search
      </Button>
    </aside>
  );
}

function placeholderSteps() {
  return [
    "Understanding your business",
    "Mapping the city",
    "Reading satellite history",
    "Counting competitors",
    "Scoring areas",
    "Writing briefs",
  ].map((label, i) => ({ id: label, label, state: (i === 0 ? "active" : "pending") as StepState }));
}
