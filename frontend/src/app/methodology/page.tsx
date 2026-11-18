import type { Metadata } from "next";
import Link from "next/link";
import { readFileSync } from "node:fs";
import path from "node:path";

export const metadata: Metadata = {
  title: "Methodology – GrowthLens",
  description: "How GrowthLens ranks areas within a city: data sources, scoring, a backtest with its failures, and honest limitations.",
};

interface Pooled {
  n_cities: number;
  mean_base_rate_grew: number;
  strategies: Record<
    string,
    { top10: { mean_lift: number; mean_lift_ci95: [number, number]; cities_with_lift_above_1: number; mean_share_grew: number }; mean_spearman: number }
  >;
}
interface CityStats {
  city: string;
  n_areas: number;
  strategies: Record<string, { top5: { lift: number }; top10: { lift: number; lift_ci95: [number, number] }; spearman: number }>;
}
interface Backtest {
  generated_at: string;
  config: { past_start: number; t0: number; future_end: number };
  pooled: Pooled;
  cities: CityStats[];
  notes: string[];
  sensitivity?: { description: string; config: { past_start: number; t0: number; outcome_start: number; future_end: number }; pooled: Pooled; cities: CityStats[] };
}

/** The committed backtest report (src/data/backtest.json). Missing file = the section explains that. */
function loadBacktest(): Backtest | null {
  try {
    return JSON.parse(readFileSync(path.join(process.cwd(), "src", "data", "backtest.json"), "utf8")) as Backtest;
  } catch {
    return null;
  }
}

const fx = (n: number) => `${n.toFixed(2)}×`;
const name = (c: string) => c.split(",")[0];

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-10 text-xl font-semibold tracking-tight">{children}</h2>;
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 leading-relaxed text-muted-foreground">{children}</p>;
}

export default function Methodology() {
  const bt = loadBacktest();
  const prod = bt?.pooled.strategies.product.top10;
  const sens = bt?.sensitivity;
  const sensByCity = new Map(sens?.cities.map((c) => [c.city, c]));
  // "Clearly better" = the 95% interval sits entirely above chance; "weak" = above 1.0 but the interval reaches it
  const clear = bt?.cities.filter((c) => c.strategies.product.top10.lift_ci95[0] > 1) ?? [];
  const weak = bt?.cities.filter((c) => c.strategies.product.top10.lift > 1 && c.strategies.product.top10.lift_ci95[0] <= 1) ?? [];
  const losers = bt?.cities.filter((c) => c.strategies.product.top10.lift <= 1) ?? [];

  return (
    <div className="h-dvh overflow-y-auto bg-background text-foreground">
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <Link href="/" className="inline-flex min-h-11 items-center text-sm text-primary underline-offset-4 hover:underline">
          ← Back to GrowthLens
        </Link>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">How GrowthLens works</h1>
        <P>
          GrowthLens is decision support. It ranks the best areas <em>within</em> a city for a business you describe, using satellite growth,
          competition and demand signals. Scores are relative to that city. They are not a forecast of revenue and not a guarantee of success.
        </P>

        <H2>What goes in</H2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-muted-foreground">
          <li>
            <strong className="text-foreground">Built-up growth:</strong> change in the probability that land is built up, from Google Dynamic World
            (10 m resolution, from Sentinel-2), comparing two years. This shows where cities are actually expanding.
          </li>
          <li>
            <strong className="text-foreground">Night-light trend:</strong> the slope of monthly night-time light (NASA/NOAA VIIRS) as a rough proxy for
            economic activity. It is coarse (about 500 m), so it is the weakest signal.
          </li>
          <li>
            <strong className="text-foreground">Competition, demand drivers and access:</strong> places mapped in OpenStreetMap (via Overpass): same-category
            businesses, places that bring customers (colleges, offices, hospitals and so on) and transit stops.
          </li>
          <li>
            <strong className="text-foreground">Your description:</strong> an AI model (Google Gemini) turns text like &ldquo;a specialty café for college
            students&rdquo; into OpenStreetMap tags and signal weights. If it is unavailable, a standard profile for that business type is used and the app says so.
          </li>
        </ul>

        <H2>How areas and scores work</H2>
        <P>
          The city is split into hexagons (H3 cells, about 0.7 km² by default; finer for small towns, coarser for very large cities). For each hexagon every
          signal is converted to a <strong className="text-foreground">percentile within the city</strong>, so one very busy area can&rsquo;t squash the rest.
          Competition is inverted (fewer competitors scores higher). The score is a weighted blend of the five percentiles, scaled 0 to 100. The weight sliders
          re-rank instantly in your browser using the same formula. Missing data counts as average rather than being guessed.
        </P>
        <P>
          Area names come from reverse geocoding (Nominatim). The location briefs are written by an AI model from the computed facts only, with instructions
          not to invent numbers or place names; if it is unavailable, a plain template is used and labelled as such.
        </P>

        <H2>Data quality, stated openly</H2>
        <P>
          Every result carries a data-quality level. <em>Good</em> means no notable gaps. <em>Check notes</em> means something is weaker than usual, for example thin
          OpenStreetMap coverage, few mapped competitors, a part of the city that could not be loaded, little detected construction (so the growth signal is weak), or
          satellite data that was unavailable. <em>Limited</em> means treat the ranking as a rough guide only. When a place has no official boundary, a circle around it is
          used and flagged.
        </P>

        <H2>Backtest: does the satellite signal look ahead?</H2>
        {bt && prod ? (
          <>
            <P>
              We asked: if GrowthLens had run at the end of {bt.config.t0}, using only satellite data up to then, would the areas it flagged have grown more over
              the next five years than the rest of the city? The design was fixed before running: features used only {bt.config.past_start}–{bt.config.t0}; the outcome
              is the change in built-up area from {bt.config.t0} to {bt.config.future_end}; &ldquo;grew&rdquo; means a top-quartile gain within the city, so a random pick
              would be right about {Math.round(bt.pooled.mean_base_rate_grew * 100)}% of the time. A lift of 1.00× means no better than chance.
            </P>

            <div className="mt-4 rounded-xl border border-border p-4">
              <p className="text-sm text-muted-foreground">Flagging the top 10% of areas by the {bt.config.t0} signal, across {bt.pooled.n_cities} cities</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">{fx(prod.mean_lift)} lift on average</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Clearly better than chance in {clear.length} of {bt.pooled.n_cities} cities ({fx(Math.min(...clear.map((c) => c.strategies.product.top10.lift)))} to{" "}
                {fx(Math.max(...clear.map((c) => c.strategies.product.top10.lift)))})
                {weak.length ? `, weaker in ${weak.map((c) => `${name(c.city)} (${fx(c.strategies.product.top10.lift)}, interval reaches 1.0×)`).join(" and ")}` : ""}.{" "}
                <strong className="text-foreground">
                  Worse than chance in {losers.map((c) => name(c.city)).join(" and ")}
                </strong>
                {losers.length ? ` (${losers.map((c) => fx(c.strategies.product.top10.lift)).join(", ")})` : ""}. The average hides a large difference between cities; its interval only
                reflects sampling within each city, not that difference.
              </p>
            </div>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <caption className="sr-only">Backtest lift by city</caption>
                <thead>
                  <tr className="border-b border-border text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">City</th>
                    <th className="pr-3 font-medium">Areas</th>
                    <th className="pr-3 font-medium">Top 5% lift</th>
                    <th className="pr-3 font-medium">Top 10% lift</th>
                    <th className="pr-3 font-medium">95% interval</th>
                    <th className="pr-3 font-medium">Growth only</th>
                    <th className="pr-3 font-medium">Night lights only</th>
                    {sens && <th className="font-medium">Gap-year check</th>}
                  </tr>
                </thead>
                <tbody>
                  {bt.cities.map((c) => {
                    const p = c.strategies.product;
                    const worse = p.top10.lift <= 1;
                    return (
                      <tr key={c.city} className="border-b border-border/60">
                        <td className="py-2 pr-3">{name(c.city)}</td>
                        <td className="pr-3 tabular-nums">{c.n_areas}</td>
                        <td className="pr-3 tabular-nums">{fx(p.top5.lift)}</td>
                        <td className={`pr-3 tabular-nums font-semibold ${worse ? "text-red-600 dark:text-red-400" : ""}`}>{fx(p.top10.lift)}</td>
                        <td className="pr-3 tabular-nums text-muted-foreground">
                          {p.top10.lift_ci95[0].toFixed(2)}–{p.top10.lift_ci95[1].toFixed(2)}
                        </td>
                        <td className="pr-3 tabular-nums">{fx(c.strategies.growth_only.top10.lift)}</td>
                        <td className="pr-3 tabular-nums">{fx(c.strategies.light_only.top10.lift)}</td>
                        {sens && <td className="tabular-nums">{sensByCity.get(c.city) ? fx(sensByCity.get(c.city)!.strategies.product.top10.lift) : "–"}</td>}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <P>
              <strong className="text-foreground">What this says.</strong> In cities that were really expanding (Bengaluru, Pune, Dubai, Nairobi, Lagos), the areas flagged from
              2020 satellite data were roughly 1.8 to 2.8 times as likely to be top-quartile growers as a random pick; Delhi is weaker, with an interval that touches 1.0×. In long-established
              cities (London, Los Angeles) the signal did not work and, in London, pointed the wrong way. Past growth alone does about as well as the blend on average
              ({fx(bt.pooled.strategies.growth_only.top10.mean_lift)}), and night lights alone are less consistent. A simple &ldquo;room to grow&rdquo; baseline (low existing
              built-up share) averages {fx(bt.pooled.strategies.room_to_grow.top10.mean_lift)}: it wins in London but fails in most other cities.
            </P>
            {sens && (
              <P>
                <strong className="text-foreground">A check on why.</strong> Annual built-up estimates are noisy. Using the same year ({bt.config.t0}) for both the signal and the
                outcome can make a signal look backwards (regression to the mean), and a test on pure noise confirms this happens. So we reran with a gap year so that the signal and
                outcome share no data ({sens.config.past_start}–{sens.config.t0} to score, {sens.config.outcome_start}–{sens.config.future_end} to measure). The average barely moves (
                {fx(sens.pooled.strategies.product.top10.mean_lift)}); London improves to {fx(sensByCity.get(bt.cities.find((c) => name(c.city) === "London")?.city ?? "")?.strategies.product.top10.lift ?? 0)} and
                Los Angeles to about chance, but London stays below 1.0×. The noise artefact explains part of the failure, not all of it, and the headline above is the design we fixed in advance.
              </P>
            )}
            <P>
              <strong className="text-foreground">What it means for you.</strong> Treat the growth signal as informative mainly where a city is visibly expanding. When built-up estimates fall across a whole city on
              average (as in London) the app flags the growth signal as unreliable. That check is simple and does not catch every weak case: Los Angeles, for example, would not be flagged.
            </P>
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
              {bt.notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </>
        ) : (
          <P>The backtest report is not bundled in this build. See the repository README for the results and how to reproduce them.</P>
        )}

        <H2>Limitations</H2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-muted-foreground">
          <li>Scores rank areas inside one city. They can&rsquo;t compare cities, and they don&rsquo;t include rent, regulations, footfall or your own costs.</li>
          <li>OpenStreetMap is volunteer-built. Coverage varies a lot between cities; a zero count can mean a real gap or missing data.</li>
          <li>The backtest tests only the satellite part of the score, in eight cities. We have no historical OpenStreetMap data to test competition and demand the same way.</li>
          <li>&ldquo;Areas that grew&rdquo; is not the same as &ldquo;places where a business succeeds&rdquo;. Growth also continues partly by momentum.</li>
          <li>Night lights are coarse and can be affected by lighting changes unrelated to activity. Cloud cover can leave gaps in satellite data.</li>
          <li>AI-written text can be wrong. Briefs are built only from computed facts, but check anything important on the ground.</li>
        </ul>

        <H2>Credits and terms</H2>
        <P>
          Map data © OpenStreetMap contributors. Basemap © CARTO. Satellite data via Google Earth Engine (used here under non-commercial terms for a portfolio
          project): Dynamic World, Sentinel-2 (Copernicus) and VIIRS (NASA/NOAA).
        </P>
        <p className="mt-10 border-t border-border pt-4 text-xs text-muted-foreground">
          {bt ? `Backtest generated ${new Date(bt.generated_at).toLocaleDateString("en", { year: "numeric", month: "long", day: "numeric" })}. ` : ""}
          GrowthLens is a portfolio project by Sarath.
        </p>
      </main>
    </div>
  );
}
