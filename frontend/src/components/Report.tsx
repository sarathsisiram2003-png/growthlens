"use client";

import { useMemo } from "react";
import { imageryUrl } from "@/lib/api";
import { scoreColor } from "@/lib/colors";
import { explain, METRIC_SHORT, METRIC_TITLE } from "@/lib/explain";
import { svgMap } from "@/lib/hexgeo";
import { nearbyPlaces } from "@/lib/nearby";
import { METRICS, normaliseWeights } from "@/lib/scoring";
import { getCachedBrief } from "@/hooks/useBrief";
import type { AnalysisResult, ViewRow, Weights } from "@/lib/types";

export type ReportTarget = { type: "city" } | { type: "location"; hex: string };

interface Props {
  result: AnalysisResult;
  rows: ViewRow[]; // every area, scored with the current weights
  top: ViewRow[];
  weights: Weights;
  target: ReportTarget;
}

/** Print-only report. The page shows it only under @media print; "Save as PDF" in the print dialog makes the file. */
export default function Report({ result, rows, top, weights, target }: Props) {
  const w = normaliseWeights(weights);
  const city = result.city.name.split(",")[0];
  const date = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  const [yBefore, yAfter] = result.windows.imagery ?? [2017, 2025];

  const map = useMemo(() => {
    const cells = rows.map((r) => r.hex);
    const { path, project } = svgMap(cells, 560, 440);
    let lo = Infinity, hi = -Infinity;
    for (const r of rows) { lo = Math.min(lo, r.score); hi = Math.max(hi, r.score); }
    const span = Math.max(hi - lo, 1e-6);
    return { path, project, lo, span };
  }, [rows]);

  const location = target.type === "location" ? rows.find((r) => r.hex === target.hex) : undefined;

  return (
    <div className="mx-auto max-w-[780px] bg-white p-8 font-sans text-[13px] leading-relaxed text-slate-900">
      <header className="border-b border-slate-300 pb-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">GrowthLens report</p>
        <h1 className="mt-1 text-2xl font-semibold">
          {location ? location.name : `Best areas for a ${result.label.toLowerCase()}`}
          {location ? <span className="text-slate-500"> · {city}</span> : <span className="text-slate-500"> · {city}</span>}
        </h1>
        <p className="mt-1 text-slate-600">{result.intent.summary}</p>
        <p className="text-xs text-slate-500">Generated {date}</p>
      </header>

      <p className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">
        {result.disclaimer} Rankings combine satellite growth, night-light trend and OpenStreetMap places; OpenStreetMap coverage varies by city.
      </p>

      {!location && (
        <>
          <section className="mt-4 break-inside-avoid">
            <h2 className="mb-2 text-base font-semibold">Opportunity map</h2>
            <svg viewBox="0 0 560 440" className="w-full rounded border border-slate-200 bg-slate-50" role="img" aria-label="Map of opportunity scores with the top 10 numbered">
              {rows.map((r) => {
                const [cr, cg, cb] = scoreColor((r.score - map.lo) / map.span, 255);
                return <path key={r.hex} d={map.path(r.hex)} fill={`rgb(${cr},${cg},${cb})`} stroke="rgba(255,255,255,0.5)" strokeWidth={0.3} />;
              })}
              {top.map((r) => {
                const [x, y] = map.project(r.lat, r.lon);
                return (
                  <g key={r.hex}>
                    <circle cx={x} cy={y} r={9} fill="#0f172a" stroke="white" strokeWidth={1.5} />
                    <text x={x} y={y + 3.5} textAnchor="middle" fontSize={10} fontWeight={700} fill="white">{r.rank}</text>
                  </g>
                );
              })}
            </svg>
            <p className="mt-1 text-xs text-slate-500">Darker = lower score, yellow = higher, relative to {city}. Numbered circles are the top 10.</p>
          </section>

          <section className="mt-4">
            <h2 className="mb-2 text-base font-semibold">Top 10 areas</h2>
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-400 text-slate-600">
                  <th className="py-1 pr-2">#</th>
                  <th className="pr-2">Area</th>
                  <th className="pr-2">Score</th>
                  <th className="pr-2">Growth</th>
                  <th className="pr-2">Demand</th>
                  <th className="pr-2">Few competitors</th>
                  <th>Why</th>
                </tr>
              </thead>
              <tbody>
                {top.map((r) => (
                  <tr key={r.hex} className="break-inside-avoid border-b border-slate-200 align-top">
                    <td className="py-1.5 pr-2 font-semibold">{r.rank}</td>
                    <td className="pr-2 font-medium">{r.name}</td>
                    <td className="pr-2 tabular-nums">{Math.round(r.score)}</td>
                    <td className="pr-2 tabular-nums">{Math.round(r.norm.growth * 100)}</td>
                    <td className="pr-2 tabular-nums">{Math.round(r.norm.demand * 100)}</td>
                    <td className="pr-2 tabular-nums">{Math.round(r.norm.competition * 100)}</td>
                    <td className="text-slate-700">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-slate-500">Growth, demand and competition columns are percentiles within the city (0–100).</p>
          </section>
        </>
      )}

      {location && <LocationBody result={result} row={location} weights={w} before={yBefore} after={yAfter} />}

      <section className="mt-4 break-inside-avoid border-t border-slate-300 pt-3 text-xs text-slate-600">
        <h2 className="mb-1 text-sm font-semibold text-slate-900">How scores are made</h2>
        <p>
          Each area (an H3 hexagon, about 0.7 km²) gets a 0–100 score: a weighted blend of five signals, each converted to a percentile within {city}.
          Weights used:{" "}
          {METRICS.map((m) => `${METRIC_SHORT[m]} ${Math.round(w[m] * 100)}%`).join(", ")}.
          Growth = change in built-up probability {result.windows.growth[0]}–{result.windows.growth[1]} (Google Dynamic World, 10 m).
          Night lights = VIIRS radiance trend. Competition, demand and access come from OpenStreetMap.
        </p>
        <p className="mt-1">Satellite data: Google Earth Engine (non-commercial). Map data © OpenStreetMap contributors.</p>
      </section>
    </div>
  );
}

function LocationBody({ result, row, weights, before, after }: { result: AnalysisResult; row: ViewRow; weights: Weights; before: number; after: number }) {
  const brief = getCachedBrief(result.id, row.hex);
  const near = nearbyPlaces(result.places, row.lat, row.lon);
  return (
    <>
      <section className="mt-4 flex items-baseline gap-3">
        <p className="text-4xl font-semibold tabular-nums">{Math.round(row.score)}<span className="text-lg font-normal text-slate-500"> /100</span></p>
        <p className="text-slate-600">{row.rank ? `Rank #${row.rank} of ${result.hexes.length} areas` : `Outside the top 10 of ${result.hexes.length} areas`}</p>
      </section>

      <section className="mt-3 grid grid-cols-2 gap-3 break-inside-avoid">
        {[before, after].map((y) => (
          <figure key={y}>
            {/* eslint-disable-next-line @next/next/no-img-element -- generated PNG from our API */}
            <img src={imageryUrl(row.hex, y)} alt={`Satellite view in ${y}`} className="w-full rounded border border-slate-200" />
            <figcaption className="text-center text-xs text-slate-500">{y}</figcaption>
          </figure>
        ))}
      </section>

      <section className="mt-4 break-inside-avoid">
        <h2 className="mb-1 text-base font-semibold">Why this score</h2>
        <ul className="divide-y divide-slate-200">
          {METRICS.map((m) => {
            const e = explain(m, row, result.windows.growth);
            return (
              <li key={m} className="py-1.5">
                <span className="font-medium">{METRIC_TITLE[m]}</span>
                <span className="text-slate-500"> · {e.percentile !== null ? `${e.percentile}th percentile` : "no data"} · weight {Math.round(weights[m] * 100)}%</span>
                <br />
                <span>{e.headline}.</span> <span className="text-slate-500">{e.context}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="mt-4 break-inside-avoid">
        <h2 className="mb-1 text-base font-semibold">Location brief</h2>
        {brief ? (
          <div className="space-y-1">
            <p><b>Why here.</b> {brief.why_here}</p>
            <p><b>Risks.</b> {brief.risks}</p>
            <p><b>Suggested format.</b> {brief.suggested_format}</p>
            <p className="text-xs text-slate-500">{brief.source === "llm" ? "Written by AI from the data in this report; verify before acting." : "Summary generated from the data in this report."}</p>
          </div>
        ) : (
          <p className="text-slate-500">{row.reason} (Open the area&rsquo;s details before exporting to include the written brief.)</p>
        )}
      </section>

      <section className="mt-4 break-inside-avoid">
        <h2 className="mb-1 text-base font-semibold">Nearby competitors (within {near.radiusM / 1000} km)</h2>
        {near.competitors.length === 0 ? (
          <p className="text-slate-500">None mapped (this can also mean thin OpenStreetMap data).</p>
        ) : (
          <ul className="columns-2 text-xs">
            {near.competitors.slice(0, 12).map((c, i) => (
              <li key={i}>{c.name ?? "Unnamed place"} · {c.distanceM} m</li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
