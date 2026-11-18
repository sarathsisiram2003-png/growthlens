"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Loader2, MapPin } from "lucide-react";
import { Input } from "@/components/ui/input";
import { searchCities } from "@/lib/api";
import type { CityOption } from "@/lib/types";

interface Props {
  value: string;
  onChange: (text: string, option: CityOption | null) => void;
  onEnter?: () => void;
  autoFocus?: boolean;
}

export default function CityAutocomplete({ value, onChange, onEnter, autoFocus }: Props) {
  const [options, setOptions] = useState<CityOption[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const picked = useRef<string | null>(null); // label just chosen; don't re-search for it
  const listId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);

  // Debounced search-as-you-type; a failed lookup just means "no suggestions" – typing still works.
  useEffect(() => {
    const q = value.trim();
    if (q.length < 2 || q === picked.current) {
      setOptions([]);
      setLoading(false);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await searchCities(q, ctrl.signal);
        setOptions(res);
        setActive(-1);
        setOpen(res.length > 0);
      } catch {
        if (!ctrl.signal.aborted) setOptions([]);
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [value]);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const choose = (o: CityOption) => {
    picked.current = o.label;
    onChange(o.label, o);
    setOpen(false);
    setOptions([]);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && options.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp" && options.length) {
      e.preventDefault();
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === "Enter") {
      if (open && active >= 0) {
        e.preventDefault();
        choose(options[active]);
      } else {
        onEnter?.();
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  return (
    <div ref={wrapRef} className="relative">
      <MapPin className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        aria-label="Where? Enter a city"
        autoComplete="off"
        autoFocus={autoFocus}
        placeholder="e.g. Bengaluru, Dubai, London…"
        value={value}
        maxLength={120}
        className="h-11 pl-9 pr-9 text-base"
        onChange={(e) => {
          picked.current = null;
          onChange(e.target.value, null);
        }}
        onFocus={() => options.length && setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {loading && (
        <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" aria-hidden />
      )}
      {open && options.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          aria-label="City suggestions"
          className="glass absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-xl py-1"
        >
          {options.map((o, i) => (
            <li
              key={o.label}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(o)}
              onMouseEnter={() => setActive(i)}
              className={`flex min-h-11 cursor-pointer items-center gap-2 px-3 py-2 text-sm ${
                i === active ? "bg-primary/15" : ""
              }`}
            >
              <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span>{o.label}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
