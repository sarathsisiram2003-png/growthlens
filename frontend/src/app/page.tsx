"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import AnalysingPanel from "@/components/AnalysingPanel";
import Legend from "@/components/Legend";
import ResultsPanel from "@/components/ResultsPanel";
import StartScreen from "@/components/StartScreen";
import TopBar from "@/components/TopBar";
import { useAnalysis } from "@/hooks/useAnalysis";
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
  const [form, setForm] = useState({ city: "", query: "" });
  const [formKey, setFormKey] = useState(0); // re-mounts the start form when returning to edit
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [sheetExpanded, setSheetExpanded] = useState(false); // mobile bottom sheet
  const desktop = useIsDesktop();

  const run = (city: string, query: string) => {
    setForm({ city, query });
    setHovered(null);
    setSelected(null);
    setSheetExpanded(false);
    void start(city, query);
  };
  // Selecting an area (card or map) opens the mobile sheet so its card is visible.
  const select = (hex: string | null) => {
    setSelected(hex);
    if (hex) setSheetExpanded(true);
  };
  const edit = () => {
    reset();
    setFormKey((k) => k + 1);
  };

  const padding: MapPadding = useMemo(() => {
    if (desktop) return { top: 72, bottom: 24, left: phase === "start" ? 24 : 432, right: 24 };
    const h = typeof window === "undefined" ? 800 : window.innerHeight;
    const sheet = phase === "results" ? (sheetExpanded ? 0.62 : 0.34) : 0.45; // matches ResultsPanel heights
    // on phones the legend sits under the top bar, so leave room for it
    return { top: phase === "results" ? 168 : 72, bottom: Math.round(h * sheet) + 12, left: 16, right: 16 };
  }, [desktop, phase, sheetExpanded]);

  const mapMode = phase === "results" ? "results" : phase === "start" ? "start" : "analysing";
  const boundary = result?.city.boundary ?? job?.meta.boundary ?? null;
  const center = job?.meta.center ?? (result ? ([result.city.lat, result.city.lon] as [number, number]) : null);

  return (
    <div className="relative h-dvh w-full overflow-hidden bg-background">
      <MapView
        mode={mapMode}
        boundary={boundary}
        center={center}
        hexes={result?.hexes}
        hoveredHex={hovered}
        selectedHex={selected}
        padding={padding}
        onHover={setHovered}
        onSelect={select}
      />

      <TopBar
        onHome={edit}
        onEdit={phase === "start" ? undefined : edit}
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

      {phase === "results" && result && (
        <>
          <ResultsPanel
            result={result}
            expanded={sheetExpanded}
            onToggleExpanded={() => setSheetExpanded((e) => !e)}
            hoveredHex={hovered}
            selectedHex={selected}
            onHover={setHovered}
            onSelect={select}
          />
          <Legend />
        </>
      )}
    </div>
  );
}
