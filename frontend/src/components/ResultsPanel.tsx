"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, CheckCircle2, ChevronUp, FileDown, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import RankCard from "@/components/RankCard";
import WeightsPanel from "@/components/WeightsPanel";
import { FLAG_MESSAGE, QUALITY_TITLE } from "@/lib/format";
import type { AnalysisResult, ViewRow, Weights } from "@/lib/types";

interface Props {
  result: AnalysisResult;
  top: ViewRow[]; // current top 10 (re-ranked for the active weights)
  pinned: ViewRow | null; // selected area that is outside the top 10
  expanded: boolean; // mobile bottom sheet
  onToggleExpanded: () => void;
  hoveredHex: string | null;
  selectedHex: string | null;
  onHover: (hex: string | null) => void;
  onSelect: (hex: string | null) => void;
  onDetails: (hex: string) => void;
  weights: Weights;
  weightsChanged: boolean;
  onWeights: (w: Weights) => void;
  onResetWeights: () => void;
  onExport: () => void;
  /** Extra controls under the header (e.g. the growth replay slider). */
  extra?: React.ReactNode;
}

export default function ResultsPanel({
  result, top, pinned, expanded, onToggleExpanded, hoveredHex, selectedHex, onHover, onSelect, onDetails,
  weights, weightsChanged, onWeights, onResetWeights, onExport, extra,
}: Props) {
  const cardRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  // Map click -> scroll the matching card into view
  useEffect(() => {
    if (selectedHex) cardRefs.current[selectedHex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedHex]);

  const dq = result.data_quality;
  // Results saved before the quality level existed fall back to "any flag = caution"
  const level = dq.level ?? (dq.flags.length ? "caution" : "good");
  const badgeStyle = {
    good: "text-emerald-600 dark:text-emerald-400",
    caution: "text-amber-600 dark:text-amber-400",
    limited: "text-red-600 dark:text-red-400",
  }[level];
  const Icon = level === "good" ? CheckCircle2 : level === "limited" ? ShieldAlert : AlertTriangle;
  const noteStyle = (flag: string) => {
    const sev = dq.severities?.[flag] ?? "caution";
    return sev === "info" ? "text-muted-foreground" : sev === "limited" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300";
  };
  const card = (row: ViewRow, isPinned = false) => (
    <RankCard
      key={`${isPinned ? "pin-" : ""}${row.hex}`}
      ref={(el) => void (cardRefs.current[row.hex] = el)}
      row={row}
      selected={row.hex === selectedHex}
      hovered={row.hex === hoveredHex}
      onSelect={() => onSelect(row.hex === selectedHex && !isPinned ? null : row.hex)}
      onHover={(on) => onHover(on ? row.hex : null)}
      onDetails={() => onDetails(row.hex)}
    />
  );

  return (
    <aside
      aria-label="Ranked locations"
      className={`glass pointer-events-auto absolute inset-x-0 bottom-0 z-10 flex flex-col rounded-t-2xl transition-[height] duration-300 md:inset-x-auto md:bottom-[84px] md:left-4 md:top-[76px] md:h-auto md:w-[400px] md:rounded-2xl ${
        expanded ? "h-[62vh]" : "h-[34vh]"
      }`}
    >
      <button
        type="button"
        className="flex h-11 w-full shrink-0 items-center justify-center md:hidden"
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse results" : "Expand results"}
        onClick={onToggleExpanded}
      >
        <ChevronUp className={`size-5 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden />
      </button>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pb-3 md:pt-3">
        <header className="px-1">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold leading-tight">Top 10 areas for a {result.label.toLowerCase()}</h2>
              <p className="mt-0.5 text-sm text-muted-foreground">{result.intent.summary}</p>
            </div>
            <Button variant="outline" className="h-11 shrink-0 px-3" aria-label="Export PDF report" onClick={onExport}>
              <FileDown aria-hidden /> <span className="hidden sm:inline">PDF</span>
            </Button>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={`h-6 gap-1 ${badgeStyle}`}>
              <Icon className="size-3.5" aria-hidden />
              {QUALITY_TITLE[level]}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {Math.round(result.data_quality.osm_coverage * 100)}% of areas have mapped places
            </span>
          </div>
          {dq.flags.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs">
              {dq.flags.map((f) => (
                <li key={f} className={noteStyle(f)}>
                  {FLAG_MESSAGE[f] ?? f}
                </li>
              ))}
            </ul>
          )}
        </header>

        {extra}
        <WeightsPanel weights={weights} changed={weightsChanged} onChange={onWeights} onReset={onResetWeights} />

        {pinned && (
          <div>
            <p className="mb-1.5 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Selected area</p>
            {card(pinned, true)}
          </div>
        )}
        <div className="space-y-2.5">{top.map((row) => card(row))}</div>
        <p className="px-1 pt-1 text-xs leading-relaxed text-muted-foreground">{result.disclaimer}</p>
      </div>
    </aside>
  );
}
