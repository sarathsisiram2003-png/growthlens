"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReportTarget } from "@/components/Report";
import { useAreaNames } from "@/hooks/useAreaNames";
import { useHistory } from "@/hooks/useHistory";
import { layerValue } from "@/lib/layers";
import { buildReason } from "@/lib/reasons";
import { METRICS, rerank, topRows, weightsEqual } from "@/lib/scoring";
import type { AnalysisResult, HexRow, Layer, ViewRow, Weights } from "@/lib/types";

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const MAX_COMPARE = 3;

/** Wait (up to a few seconds) for the report's images so the print preview isn't missing satellite views. */
async function imagesReady(timeoutMs = 8000) {
  // not requestAnimationFrame: it is paused while the tab is hidden, which would stall the export
  await new Promise((r) => setTimeout(r, 60));
  const imgs = [...document.querySelectorAll<HTMLImageElement>("#report-root img")];
  const settle = Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = () => r(null); }))));
  await Promise.race([settle, new Promise((r) => setTimeout(r, timeoutMs))]);
}

/** All state behind the results screen: weights, layers, growth replay, drawer, compare and export. */
export function useResultsState(result: AnalysisResult | null) {
  const [weightsState, setWeightsState] = useState<Weights | null>(null);
  const [layer, setLayer] = useState<Layer>("opportunity");
  const [yearIndex, setYearIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [sheetExpanded, setSheetExpanded] = useState(false); // mobile bottom sheet
  const [detailHex, setDetailHex] = useState<string | null>(null);
  const [compare, setCompare] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [exporting, setExporting] = useState<ReportTarget | null>(null);

  // ---- weights & ranking (client-side, instant) ----
  const baseWeights = useMemo<Weights | null>(
    () => (result ? (Object.fromEntries(METRICS.map((m) => [m, Math.round(result.weights[m] * 100)])) as Weights) : null),
    [result],
  );
  const weights = weightsState ?? baseWeights;
  const weightsChanged = !!(weights && baseWeights && !weightsEqual(weights, baseWeights));
  const scored = useMemo(() => (result && weights ? rerank(result.hexes, weights) : null), [result, weights]);
  const top = useMemo(() => (scored ? topRows(scored) : []), [scored]);
  const nameOf = useAreaNames(top);

  const view = useCallback(
    (r: HexRow): ViewRow => ({ ...r, name: nameOf(r), reason: r.rank ? buildReason(r) : undefined }),
    [nameOf],
  );
  const viewTop = useMemo(() => top.map(view), [top, view]);
  const viewRows = useMemo(() => (scored ? scored.map((r) => (r.rank ? view(r) : { ...r, name: "" })) : []), [scored, view]);
  const rowOf = useCallback(
    (hex: string | null): ViewRow | null => {
      const r = hex && scored ? scored.find((x) => x.hex === hex) : null;
      return r ? view(r) : null;
    },
    [scored, view],
  );
  const selectedRow = rowOf(selected);
  const pinned = selectedRow && selectedRow.rank === null ? selectedRow : null;
  const detailRow = rowOf(detailHex);
  const compareRows = compare.map((h) => rowOf(h)).filter((r): r is ViewRow => !!r);

  // ---- growth replay ----
  const history = useHistory(result?.id, layer === "growth");
  const replay = useMemo(() => {
    const d = history.data;
    if (!d || layer !== "growth") return null;
    const last = d.years.length - 1;
    const gains = Object.values(d.values)
      .map((v) => (v[last] ?? 0) - (v[0] ?? 0))
      .filter((x) => x > 0)
      .sort((a, b) => a - b);
    return { years: d.years, data: d, dmax: Math.max(gains[Math.floor(gains.length * 0.98)] ?? 0, 0.02) };
  }, [history.data, layer]);
  const lastIdx = replay ? replay.years.length - 1 : 0;
  const idx = replay ? Math.min(yearIndex ?? lastIdx, lastIdx) : 0;
  const isPlaying = playing && !!replay && idx < lastIdx;

  useEffect(() => {
    if (!isPlaying) return;
    const t = setInterval(() => setYearIndex((i) => Math.min((i ?? 0) + 1, lastIdx)), 900);
    return () => clearInterval(t);
  }, [isPlaying, lastIdx]);

  const togglePlay = () => {
    if (isPlaying) return setPlaying(false);
    if (idx >= lastIdx) setYearIndex(0);
    setPlaying(true);
  };

  // ---- colour value (0–1) per area ----
  const layerValues = useMemo(() => {
    const out = {} as Record<Layer, Map<string, number>>;
    for (const l of ["opportunity", "growth", "activity", "competitors", "demand"] as Layer[]) out[l] = new Map();
    if (!scored) return out;
    let min = Infinity;
    let max = -Infinity;
    for (const r of scored) {
      min = Math.min(min, r.score);
      max = Math.max(max, r.score);
    }
    const range = { min, span: Math.max(max - min, 1e-6) };
    for (const r of scored) for (const l of Object.keys(out) as Layer[]) out[l].set(r.hex, clamp01(layerValue(l, r, range)));
    return out;
  }, [scored]);
  const opportunityValues = layerValues.opportunity;

  // active layer, or the replay year when the growth history is loaded
  const values = useMemo(() => {
    if (!replay) return layerValues[layer];
    const m = new Map<string, number>();
    for (const [hex, v] of Object.entries(replay.data.values)) {
      const a = v[0];
      const b = v[idx];
      m.set(hex, a == null || b == null ? 0 : clamp01((b - a) / replay.dmax));
    }
    return m;
  }, [layerValues, layer, replay, idx]);
  const legendCaption = replay ? `Built-up growth ${replay.years[0]}–${replay.years[idx]}.` : undefined;

  // ---- actions ----
  const select = (hex: string | null) => {
    setSelected(hex);
    if (hex) {
      setSheetExpanded(true);
      if (detailHex) setDetailHex(hex); // an open drawer follows the selection
    }
  };
  const openDetail = (hex: string) => {
    setSelected(hex);
    setDetailHex(hex);
  };
  const toggleCompare = (hex: string) =>
    setCompare((c) => (c.includes(hex) ? c.filter((h) => h !== hex) : c.length >= MAX_COMPARE ? c : [...c, hex]));
  const resetAll = () => {
    setWeightsState(null);
    setLayer("opportunity");
    setYearIndex(null);
    setPlaying(false);
    setHovered(null);
    setSelected(null);
    setSheetExpanded(false);
    setDetailHex(null);
    setCompare([]);
    setCompareOpen(false);
    setExporting(null);
  };

  // ---- PDF export: render the print-only report, wait for images, open the print dialog ("Save as PDF") ----
  useEffect(() => {
    if (!exporting) return;
    let cancelled = false;
    const done = () => setExporting(null);
    window.addEventListener("afterprint", done, { once: true });
    void imagesReady().then(() => {
      if (!cancelled) window.print();
    });
    return () => {
      cancelled = true;
      window.removeEventListener("afterprint", done);
    };
  }, [exporting]);

  return {
    // data
    weights, baseWeights, weightsChanged, viewRows, viewTop, pinned, detailRow, compareRows, values, opportunityValues, legendCaption,
    // ui state
    layer, hovered, selected, sheetExpanded, detailHex, compare, compareOpen, exporting,
    replay: { years: replay?.years ?? [], index: idx, playing: isPlaying, active: !!replay, history },
    // actions
    setWeights: setWeightsState, resetWeights: () => setWeightsState(null),
    setLayer: (l: Layer) => { setLayer(l); setPlaying(false); },
    setYearIndex: (i: number) => { setPlaying(false); setYearIndex(i); },
    togglePlay, setHovered, select, openDetail, closeDetail: () => setDetailHex(null),
    toggleCompare, setCompareOpen, setSheetExpanded, setExporting, resetAll,
  };
}
