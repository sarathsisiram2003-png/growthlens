"use client";

import { LAYERS } from "@/lib/layers";
import type { Layer } from "@/lib/types";

interface Props {
  value: Layer;
  onChange: (l: Layer) => void;
  className?: string;
}

export default function LayerToggles({ value, onChange, className = "" }: Props) {
  return (
    <div
      role="group"
      aria-label="Map layer"
      className={`glass pointer-events-auto flex gap-1 overflow-x-auto rounded-xl p-1 ${className}`}
    >
      {LAYERS.map((l) => (
        <button
          key={l.id}
          type="button"
          aria-pressed={value === l.id}
          title={l.help}
          onClick={() => onChange(l.id)}
          className={`h-11 shrink-0 rounded-lg px-3 text-sm whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 ${
            value === l.id ? "bg-primary text-primary-foreground" : "hover:bg-muted"
          }`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
