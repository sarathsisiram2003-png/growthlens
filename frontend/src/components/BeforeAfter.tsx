"use client";

import { useMemo, useState } from "react";
import { cellToBoundary } from "h3-js";
import { imageryUrl } from "@/lib/api";

const PAD_DEG = 0.004; // must match backend/growthlens/imagery.py

interface Props {
  hex: string;
  before: number;
  after: number;
}

/** Earliest vs latest satellite image of an area with a draggable divider and the area's outline. */
/** How many years later than requested we will accept for the "before" image when that year has no usable scenes. */
export const MAX_BEFORE_FALLBACK = 2;

export default function BeforeAfter({ hex, before: requestedBefore, after }: Props) {
  const [before, setBefore] = useState(requestedBefore); // shown year; moves later if the earliest year has no usable imagery
  const [split, setSplit] = useState(50); // % of the width showing the "before" image
  const [loaded, setLoaded] = useState({ before: false, after: false });
  const [failed, setFailed] = useState(false);

  // Hex outline in image-percent coordinates (the thumbnail covers the hex bounds plus PAD_DEG on every side).
  const outline = useMemo(() => {
    const pts = cellToBoundary(hex);
    const lats = pts.map((p) => p[0]);
    const lngs = pts.map((p) => p[1]);
    const w = Math.max(...lngs) - Math.min(...lngs) + 2 * PAD_DEG;
    const h = Math.max(...lats) - Math.min(...lats) + 2 * PAD_DEG;
    const x0 = Math.min(...lngs) - PAD_DEG;
    const y0 = Math.max(...lats) + PAD_DEG;
    const points = pts.map(([lat, lng]) => `${(((lng - x0) / w) * 100).toFixed(2)},${(((y0 - lat) / h) * 100).toFixed(2)}`);
    return { points: points.join(" "), aspect: w / h };
  }, [hex]);

  if (failed) {
    return (
      <div role="alert" className="flex aspect-square items-center justify-center rounded-xl border border-border bg-muted/50 p-4 text-center text-sm text-muted-foreground">
        Satellite imagery isn&rsquo;t available for this area right now.
      </div>
    );
  }

  const ready = loaded.before && loaded.after;
  return (
    <figure>
      <div
        className="relative w-full select-none overflow-hidden rounded-xl border border-border bg-muted focus-within:ring-3 focus-within:ring-ring/50"
        style={{ aspectRatio: outline.aspect }}
      >
        {!ready && <div className="absolute inset-0 animate-pulse bg-muted" aria-hidden />}
        {/* eslint-disable @next/next/no-img-element -- remote, dynamically generated PNGs */}
        <img
          src={imageryUrl(hex, after)}
          alt={`Satellite view of the area in ${after}`}
          className="absolute inset-0 size-full object-cover"
          onLoad={() => setLoaded((l) => ({ ...l, after: true }))}
          onError={() => setFailed(true)}
        />
        <img
          src={imageryUrl(hex, before)}
          alt={`Satellite view of the area in ${before}`}
          className="absolute inset-0 size-full object-cover"
          style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          onLoad={() => setLoaded((l) => ({ ...l, before: true }))}
          onError={() => (before < requestedBefore + MAX_BEFORE_FALLBACK ? setBefore((y) => y + 1) : setFailed(true))}
        />
        {/* eslint-enable @next/next/no-img-element */}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full" aria-hidden>
          <polygon points={outline.points} fill="none" stroke="white" strokeWidth="0.8" strokeDasharray="2 1.5" vectorEffect="non-scaling-stroke" />
        </svg>
        {ready && (
          <>
            <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white shadow" style={{ left: `${split}%` }} aria-hidden />
            <span className="pointer-events-none absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white">{before}</span>
            <span className="pointer-events-none absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-xs font-medium text-white">{after}</span>
          </>
        )}
        <input
          type="range"
          min={0}
          max={100}
          value={split}
          aria-label={`Compare satellite images: ${before} on the left, ${after} on the right`}
          onChange={(e) => setSplit(Number(e.target.value))}
          className="absolute inset-0 size-full cursor-ew-resize opacity-0"
          disabled={!ready}
        />
      </div>
      <figcaption className="mt-1.5 text-xs text-muted-foreground">
        Sentinel-2 yearly composites ({before} vs {after}).{before !== requestedBefore ? ` (${requestedBefore} had no usable imagery here.)` : ""} Drag to compare. Dashed line: this area.
      </figcaption>
    </figure>
  );
}
