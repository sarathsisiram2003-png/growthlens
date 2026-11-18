"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import AnalysingPanel from "@/components/AnalysingPanel";
import CompareView from "@/components/CompareView";
import DetailDrawer from "@/components/DetailDrawer";
import LayerToggles from "@/components/LayerToggles";
import Legend from "@/components/Legend";
import Report from "@/components/Report";
import ResultsPanel from "@/components/ResultsPanel";
import StartScreen from "@/components/StartScreen";
import TimeSlider from "@/components/TimeSlider";
import TopBar from "@/components/TopBar";
import { useAnalysis } from "@/hooks/useAnalysis";
import { MAX_COMPARE, useResultsState } from "@/hooks/useResultsState";
import type { MapPadding } from "@/components/MapView";

// MapLibre / deck.gl need the browser, so the map is client-only.
const MapView = dynamic(() => import("@/components/MapView"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-muted" aria-hidden />,
});

function useIsDesktop() {
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const update = () => setDesktop(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

export default function Home() {
  const { phase, job, result, error, start, reset } = useAnalysis();
  const rs = useResultsState(result);
  const [form, setForm] = useState({ city: "", query: "" });
  const [formKey, setFormKey] = useState(0); // re-mounts the start form when returning to edit
  const desktop = useIsDesktop();

  const run = (city: string, query: string) => {
    setForm({ city, query });
    rs.resetAll();
    void start(city, query);
  };
  const edit = () => {
    reset();
    rs.resetAll();
    setFormKey((k) => k + 1);
  };

  const results = phase === "results" && result && rs.weights ? { result, weights: rs.weights } : null;
  const drawerOpen = !!(results && rs.detailRow);
  const compareOpen = !!(results && rs.compareOpen && rs.compareRows.length >= 2);

  const padding: MapPadding = useMemo(() => {
    if (desktop) {
      return { top: phase === "results" ? 130 : 72, bottom: 24, left: phase === "start" ? 24 : 432, right: drawerOpen ? 472 : 24 };
    }
    const h = typeof window === "undefined" ? 800 : window.innerHeight;
    const sheet = phase === "results" ? (rs.sheetExpanded ? 0.62 : 0.34) : 0.45; // matches ResultsPanel heights
    // on phones the layer chips and legend sit under the top bar, so leave room for them
    return { top: phase === "results" ? 220 : 72, bottom: Math.round(h * sheet) + 12, left: 16, right: 16 };
  }, [desktop, phase, rs.sheetExpanded, drawerOpen]);

  const mapMode = phase === "results" ? "results" : phase === "start" ? "start" : "analysing";
  const boundary = result?.city.boundary ?? job?.meta.boundary ?? null;
  const center = job?.meta.center ?? (result ? ([result.city.lat, result.city.lon] as [number, number]) : null);

  const slider = rs.layer === "growth" && (
    <TimeSlider
      years={rs.replay.history.data?.years ?? []}
      index={rs.replay.index}
      playing={rs.replay.playing}
      state={rs.replay.history.state}
      progress={rs.replay.history.progress}
      error={rs.replay.history.error}
      onIndex={rs.setYearIndex}
      onPlay={rs.togglePlay}
      onRetry={rs.replay.history.retry}
    />
  );

  return (
    <>
      <div className="no-print relative h-dvh w-full overflow-hidden bg-background">
        <MapView
          mode={mapMode}
          boundary={boundary}
          center={center}
          hexes={phase === "results" ? rs.viewRows : undefined}
          values={rs.values}
          hoveredHex={rs.hovered}
          selectedHex={rs.selected}
          padding={padding}
          onHover={rs.setHovered}
          onSelect={rs.select}
        />

        <TopBar
          onHome={edit}
          onEdit={phase === "start" ? undefined : edit}
          compareCount={results ? rs.compare.length : 0}
          onCompare={() => rs.setCompareOpen(true)}
          title={
            phase === "results" && result
              ? `${result.city.name.split(",")[0]} · ${result.label.toLowerCase()}`
              : phase === "analysing"
                ? form.city.split(",")[0]
                : undefined
          }
        />

        {phase === "start" && (
          <StartScreen key={formKey} initialCity={form.city} initialQuery={form.query} onSubmit={run} />
        )}

        {phase === "analysing" && <AnalysingPanel job={job} city={form.city} onEdit={edit} />}

        {phase === "error" && (
          <main className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center px-4">
            <section role="alert" className="glass pointer-events-auto w-full max-w-md rounded-2xl p-6">
              <h1 className="text-xl font-semibold">We couldn&rsquo;t finish that search</h1>
              <p className="mt-2 text-sm text-muted-foreground">{error}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Button className="h-11 px-5" onClick={() => run(form.city, form.query)}>
                  Try again
                </Button>
                <Button variant="outline" className="h-11 px-5" onClick={edit}>
                  Edit search
                </Button>
              </div>
            </section>
          </main>
        )}

        {results && (
          <>
            <div className="absolute inset-x-3 top-[60px] z-20 md:inset-x-auto md:left-[424px] md:top-[68px] md:max-w-[calc(100%-448px)]">
              <LayerToggles value={rs.layer} onChange={rs.setLayer} />
            </div>
            <ResultsPanel
              result={results.result}
              top={rs.viewTop}
              pinned={rs.pinned}
              expanded={rs.sheetExpanded}
              onToggleExpanded={() => rs.setSheetExpanded(!rs.sheetExpanded)}
              hoveredHex={rs.hovered}
              selectedHex={rs.selected}
              onHover={rs.setHovered}
              onSelect={rs.select}
              onDetails={rs.openDetail}
              weights={results.weights}
              weightsChanged={rs.weightsChanged}
              onWeights={rs.setWeights}
              onResetWeights={rs.resetWeights}
              onExport={() => rs.setExporting({ type: "city" })}
              extra={slider}
            />
            <Legend layer={rs.layer} caption={rs.legendCaption} />

            {rs.detailRow && (
              <DetailDrawer
                result={results.result}
                row={rs.detailRow}
                weights={results.weights}
                inCompare={rs.compare.includes(rs.detailRow.hex)}
                compareFull={rs.compare.length >= MAX_COMPARE}
                onToggleCompare={() => rs.toggleCompare(rs.detailRow!.hex)}
                onExport={() => rs.setExporting({ type: "location", hex: rs.detailRow!.hex })}
                onClose={rs.closeDetail}
              />
            )}

            {compareOpen && (
              <CompareView
                result={results.result}
                rows={rs.compareRows}
                weights={results.weights}
                allScores={rs.opportunityValues}
                onRemove={rs.toggleCompare}
                onClose={() => rs.setCompareOpen(false)}
              />
            )}
          </>
        )}
      </div>

      {results && rs.exporting && (
        <div id="report-root">
          <Report result={results.result} rows={rs.viewRows} top={rs.viewTop} weights={results.weights} target={rs.exporting} />
        </div>
      )}
    </>
  );
}
