import { LEGEND_GRADIENT } from "@/lib/colors";
import { LAYERS } from "@/lib/layers";
import type { Layer } from "@/lib/types";

interface Props {
  layer: Layer;
  /** e.g. "Built-up growth since 2016, up to 2024" when the time slider is driving the map */
  caption?: string;
}

export default function Legend({ layer, caption }: Props) {
  const l = LAYERS.find((x) => x.id === layer)!;
  const title = layer === "opportunity" ? "Opportunity score" : l.label;
  return (
    <div
      className="glass pointer-events-auto absolute left-3 top-[116px] z-10 w-[200px] rounded-xl p-3 md:bottom-4 md:left-4 md:top-auto md:w-[260px]"
      role="img"
      aria-label={`Legend: ${title}, from ${l.legend[0].toLowerCase()} to ${l.legend[1].toLowerCase()}, relative to this city`}
    >
      <p className="text-xs font-medium">{title}</p>
      <div className="mt-1.5 h-2.5 rounded-full" style={{ background: LEGEND_GRADIENT }} />
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{l.legend[0]}</span>
        <span>{l.legend[1]}</span>
      </div>
      <p className="mt-1 hidden text-[11px] leading-snug text-muted-foreground md:block">
        {caption ?? "Relative to this city."} Outlined, numbered hexagons are the top 10.
      </p>
    </div>
  );
}
