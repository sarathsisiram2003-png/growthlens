import { LEGEND_GRADIENT } from "@/lib/colors";

export default function Legend() {
  return (
    <div
      className="glass pointer-events-auto absolute left-3 top-[68px] z-10 w-[200px] rounded-xl p-3 md:bottom-4 md:left-4 md:top-auto md:w-[260px]"
      role="img"
      aria-label="Legend: opportunity score from low to high, relative to this city"
    >
      <p className="text-xs font-medium">Opportunity score</p>
      <div className="mt-1.5 h-2.5 rounded-full" style={{ background: LEGEND_GRADIENT }} />
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>Lower</span>
        <span>Higher</span>
      </div>
      <p className="mt-1 hidden text-[11px] leading-snug text-muted-foreground md:block">Relative to this city. Outlined, numbered hexagons are the top 10.</p>
    </div>
  );
}
