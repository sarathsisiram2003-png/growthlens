"use client";

import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import ThemeToggle from "@/components/ThemeToggle";

interface Props {
  title?: string; // e.g. "Bengaluru · specialty café"
  onHome: () => void;
  onEdit?: () => void;
}

export default function TopBar({ title, onHome, onEdit }: Props) {
  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-center gap-2 p-3">
      <button
        type="button"
        onClick={onHome}
        className="glass pointer-events-auto flex h-11 items-center rounded-xl px-4 text-base font-semibold tracking-tight focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        aria-label="GrowthLens – back to start"
      >
        Growth<span className="text-primary">Lens</span>
      </button>
      {title && (
        <div className="glass pointer-events-auto hidden h-11 min-w-0 items-center truncate rounded-xl px-4 text-sm sm:flex">
          {title}
        </div>
      )}
      <div className="pointer-events-auto ml-auto flex items-center gap-2">
        {onEdit && (
          <Button variant="outline" className="glass h-11 px-4" aria-label="Edit search" onClick={onEdit}>
            <Pencil aria-hidden /> <span className="hidden sm:inline">Edit search</span>
            <span className="sm:hidden">Edit</span>
          </Button>
        )}
        <ThemeToggle />
      </div>
    </header>
  );
}
