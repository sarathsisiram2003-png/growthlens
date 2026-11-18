import type { HexRow, Metric } from "./types";

// Mirrors backend/growthlens/reasons.py so reasons stay correct after the user re-weights and new areas enter the top 10.
// `competition` norms are inverted: high = few competitors.
const PHRASES: Record<Metric, string> = {
  growth: "fast-growing built-up area",
  demand: "strong demand drivers nearby",
  activity: "rising night-time activity",
  competition: "few direct competitors",
  access: "good transit access",
};
const STRONG = 0.7;

export function buildReason(row: Pick<HexRow, "norm" | "raw">): string {
  const strong = (Object.keys(PHRASES) as Metric[])
    .filter((m) => (row.norm[m] ?? 0.5) >= STRONG)
    .sort((a, b) => row.norm[b] - row.norm[a])
    .slice(0, 3);
  const phrases = strong.map((m) => (m === "competition" && row.raw.competition === 0 ? "no mapped competitors" : PHRASES[m]));
  let text = phrases.length ? phrases.join(", ") : "Balanced profile across all signals";
  text = text.charAt(0).toUpperCase() + text.slice(1);
  const cautions: string[] = [];
  if ((row.norm.competition ?? 0.5) <= 0.3) cautions.push("crowded with competitors");
  if ((row.norm.demand ?? 0.5) <= 0.3) cautions.push("few demand drivers");
  if (cautions.length) text += `; watch out: ${cautions.join(" and ")}`;
  return `${text}.`;
}
