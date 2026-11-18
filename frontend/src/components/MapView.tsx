"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { Layer, Map, Source, useControl, type MapRef } from "react-map-gl/maplibre";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { TextLayer } from "@deck.gl/layers";
import type { Geometry } from "geojson";
import { useTheme } from "next-themes";
import { scoreColor } from "@/lib/colors";
import { geometryBounds } from "@/lib/geo";
import type { HexRow } from "@/lib/types";

// The worker is copied to /public by scripts/copy-maplibre.mjs (see the note there).
maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const STYLES = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

const HOVER_COLOR: [number, number, number, number] = [255, 140, 0, 255];
const SELECT_COLOR: [number, number, number, number] = [255, 255, 255, 255];

function DeckGLOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

export interface MapPadding {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

interface Props {
  mode: "start" | "analysing" | "results";
  boundary?: Geometry | null;
  center?: [number, number] | null; // [lat, lon]
  hexes?: HexRow[];
  /** 0–1 colour value per hex for the active layer / year */
  values?: Map<string, number>;
  hoveredHex?: string | null;
  selectedHex?: string | null;
  padding: MapPadding;
  onHover?: (hex: string | null) => void;
  onSelect?: (hex: string | null) => void;
}

export default function MapView({
  mode,
  boundary,
  center,
  hexes,
  values,
  hoveredHex,
  selectedHex,
  padding,
  onHover,
  onSelect,
}: Props) {
  const mapRef = useRef<MapRef>(null);
  const [ready, setReady] = useState(false);
  const { resolvedTheme } = useTheme();
  // Latest padding for camera moves, without making every padding change re-fly the camera.
  const paddingRef = useRef(padding);
  useEffect(() => {
    paddingRef.current = padding;
  });
  const style = resolvedTheme === "light" ? STYLES.light : STYLES.dark;

  // ---- Start screen: slow drift around the globe (skipped for reduced-motion users) ----
  useEffect(() => {
    if (mode !== "start" || !ready) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    let raf = 0;
    let last = performance.now();
    let lng = map.getCenter().lng;
    const tick = (now: number) => {
      lng = ((lng + ((now - last) / 1000) * 1.2 + 540) % 360) - 180; // ~1.2°/s
      last = now;
      map.jumpTo({ center: [lng, 22] });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [mode, ready]);

  // ---- Fly to the city once its boundary is known ----
  const bounds = useMemo(() => geometryBounds(boundary), [boundary]);
  useEffect(() => {
    if (!ready || mode === "start") return;
    const map = mapRef.current;
    if (!map) return;
    if (bounds) map.fitBounds(bounds, { padding: paddingRef.current, duration: 1800, maxZoom: 13 });
    else if (center) map.flyTo({ center: [center[1], center[0]], zoom: 10, duration: 1800 });
  }, [ready, mode, bounds, center]);

  // ---- Keep a selected area visible (not hidden behind the side panel) ----
  useEffect(() => {
    if (!ready || !selectedHex || !hexes) return;
    const row = hexes.find((h) => h.hex === selectedHex);
    if (row) mapRef.current?.easeTo({ center: [row.lon, row.lat], padding: paddingRef.current, duration: 500 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to selection changes
  }, [selectedHex]);

  const top = useMemo(() => (hexes ?? []).filter((h) => h.rank !== null).sort((a, b) => a.rank! - b.rank!), [hexes]);
  const emphasised = useMemo(
    () =>
      (hexes ?? []).filter((h) => h.hex === hoveredHex || h.hex === selectedHex).map((h) => ({
        hex: h.hex,
        hovered: h.hex === hoveredHex,
      })),
    [hexes, hoveredHex, selectedHex],
  );

  const layers = useMemo(() => {
    if (mode !== "results" || !hexes) return [];
    return [
      new H3HexagonLayer<HexRow>({
        id: "heat",
        data: hexes,
        getHexagon: (d) => d.hex,
        getFillColor: (d) => scoreColor(values?.get(d.hex) ?? 0, 175),
        extruded: false,
        stroked: false,
        pickable: true,
        onHover: (info) => onHover?.(info.object ? (info.object as HexRow).hex : null),
        onClick: (info) => onSelect?.(info.object ? (info.object as HexRow).hex : null),
        updateTriggers: { getFillColor: [values] },
      }),
      new H3HexagonLayer<HexRow>({
        id: "top-outline",
        data: top,
        getHexagon: (d) => d.hex,
        filled: false,
        stroked: true,
        extruded: false,
        getLineColor: [255, 255, 255, 235],
        lineWidthMinPixels: 2,
        pickable: false,
      }),
      new H3HexagonLayer<{ hex: string; hovered: boolean }>({
        id: "emphasis",
        data: emphasised,
        getHexagon: (d) => d.hex,
        filled: false,
        stroked: true,
        extruded: false,
        getLineColor: (d) => (d.hovered ? HOVER_COLOR : SELECT_COLOR),
        lineWidthMinPixels: 4,
        pickable: false,
        updateTriggers: { getLineColor: [hoveredHex, selectedHex] },
      }),
      new TextLayer<HexRow>({
        id: "rank-labels",
        data: top,
        getPosition: (d) => [d.lon, d.lat],
        getText: (d) => String(d.rank),
        getSize: 13,
        getColor: [255, 255, 255, 255],
        fontWeight: 700,
        background: true,
        getBackgroundColor: [15, 23, 42, 215],
        backgroundPadding: [6, 3],
        pickable: true,
        onHover: (info) => onHover?.(info.object ? (info.object as HexRow).hex : null),
        onClick: (info) => onSelect?.(info.object ? (info.object as HexRow).hex : null),
      }),
    ];
  }, [mode, hexes, values, top, emphasised, hoveredHex, selectedHex, onHover, onSelect]);

  const getTooltip = useCallback(
    ({ object }: { object?: unknown }) => {
      const h = object as HexRow | undefined;
      if (!h || typeof h.score !== "number") return null;
      return {
        text: `${h.rank ? `#${h.rank} · ` : ""}${h.name ?? "Area"}\nScore ${Math.round(h.score)}/100`,
        style: { fontSize: "12px", borderRadius: "8px", padding: "6px 10px", whiteSpace: "pre" },
      };
    },
    [],
  );

  return (
    <Map
      ref={mapRef}
      mapLib={maplibregl}
      mapStyle={style}
      initialViewState={{ longitude: 20, latitude: 22, zoom: 1.4 }}
      interactive={mode === "results"}
      attributionControl={{ compact: true }}
      onLoad={() => setReady(true)}
      style={{ position: "absolute", inset: 0 }}
    >
      {boundary && mode !== "start" && (
        <Source id="boundary" type="geojson" data={{ type: "Feature", properties: {}, geometry: boundary }}>
          <Layer id="boundary-fill" type="fill" paint={{ "fill-color": "#2dd4bf", "fill-opacity": 0.05 }} />
          <Layer
            id="boundary-line"
            type="line"
            paint={{ "line-color": "#2dd4bf", "line-width": 2, "line-opacity": 0.9 }}
          />
        </Source>
      )}
      <DeckGLOverlay layers={layers} getTooltip={getTooltip} />
    </Map>
  );
}
