"use client";

import { useEffect, useMemo, useRef } from "react";
import { AlertTriangle, CheckCircle2, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import RankCard from "@/components/RankCard";
import { FLAG_MESSAGE } from "@/lib/format";
import type { AnalysisResult } from "@/lib/types";

interface Props {
  result: AnalysisResult;
  expanded: boolean; // mobile bottom sheet
  onToggleExpanded: () => void;
  hoveredHex: string | null;
  selectedHex: string | null;
  onHover: (hex: string | null) => void;
  onSelect: (hex: string | null) => void;
}

export default function ResultsPanel({ result, expanded, onToggleExpanded, hoveredHex, selectedHex, onHover, onSelect }: Props) {
  const cardRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const byHex = useMemo(() => new Map(result.hexes.map((h) => [h.hex, h])), [result.hexes]);
  const top = useMemo(
    () => result.top10.map((h) => byHex.get(h)).filter((h): h is NonNullable<typeof h> => !!h),
    [result.top10, byHex],
  );
  const selectedRow = selectedHex ? byHex.get(selectedHex) : undefined;
  const pinned = selectedRow && selectedRow.rank === null ? selectedRow : null; // selected area outside the top 10

  // Map click -> scroll the matching card into view
  useEffect(() => {
    if (!selectedHex) return;
    cardRefs.current[selectedHex]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedHex]);

  const flags = result.data_quality.flags;
  const good = flags.length === 0;

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

      <header className="shrink-0 px-4 pb-3 md:pt-4">
        <h2 className="text-lg font-semibold leading-tight">Top 10 areas for a {result.label.toLowerCase()}</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">{result.intent.summary}</p>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <Badge
            variant="outline"
            className={`h-6 gap-1 ${good ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}`}
          >
            {good ? <CheckCircle2 className="size-3.5" aria-hidden /> : <AlertTriangle className="size-3.5" aria-hidden />}
            {good ? "Data quality: good" : "Data quality: check notes"}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {Math.round(result.data_quality.osm_coverage * 100)}% of areas have mapped places
          </span>
        </div>
        {!good && (
          <ul className="mt-2 space-y-1 text-xs text-amber-700 dark:text-amber-300">
            {flags.map((f) => (
              <li key={f}>{FLAG_MESSAGE[f] ?? f}</li>
            ))}
          </ul>
        )}
      </header>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 pb-3">
        {pinned && (
          <div>
            <p className="mb-1.5 px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Selected area</p>
            <RankCard
              ref={(el) => void (cardRefs.current[pinned.hex] = el)}
              row={pinned}
              selected
              hovered={false}
              onSelect={() => onSelect(null)}
              onHover={() => void 0}
            />
          </div>
        )}
        {top.map((row) => (
          <RankCard
            key={row.hex}
            ref={(el) => void (cardRefs.current[row.hex] = el)}
            row={row}
            selected={row.hex === selectedHex}
            hovered={row.hex === hoveredHex}
            onSelect={() => onSelect(row.hex === selectedHex ? null : row.hex)}
            onHover={(on) => onHover(on ? row.hex : null)}
          />
        ))}
        <p className="px-1 pt-1 text-xs leading-relaxed text-muted-foreground">{result.disclaimer}</p>
      </div>
    </aside>
  );
}
