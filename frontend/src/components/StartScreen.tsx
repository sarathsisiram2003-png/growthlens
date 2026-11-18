"use client";

import { useId, useState } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import CityAutocomplete from "@/components/CityAutocomplete";

const EXAMPLES = [
  { chip: "Café", text: "A specialty café for college students" },
  { chip: "Pharmacy", text: "24x7 pharmacy" },
  { chip: "Gym", text: "Budget gym" },
  { chip: "Clinic", text: "Family clinic" },
  { chip: "EV charging", text: "EV charging station" },
  { chip: "Supermarket", text: "Neighbourhood supermarket" },
];

const DEMOS = [
  { name: "Bengaluru", city: "Bengaluru, Karnataka, India" },
  { name: "Dubai", city: "Dubai, United Arab Emirates" },
  { name: "London", city: "London, England, United Kingdom" },
];
const DEMO_QUERY = "A specialty café for college students";

interface Props {
  initialCity?: string;
  initialQuery?: string;
  onSubmit: (city: string, query: string) => void;
}

export default function StartScreen({ initialCity = "", initialQuery = "", onSubmit }: Props) {
  const [city, setCity] = useState(initialCity);
  const [query, setQuery] = useState(initialQuery);
  const queryId = useId();
  const valid = city.trim().length >= 2 && query.trim().length >= 2;

  const submit = () => valid && onSubmit(city.trim(), query.trim());

  return (
    <main className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center overflow-y-auto px-4 py-20">
      <section
        aria-labelledby="start-title"
        className="glass pointer-events-auto w-full max-w-lg rounded-2xl p-5 sm:p-7"
      >
        <h1 id="start-title" className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Where should you open?
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Pick any city and describe your business. We rank the best areas <em>within</em> that city.
        </p>

        <form
          className="mt-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div>
            <div className="mb-1.5 text-sm font-medium">Where?</div>
            <CityAutocomplete value={city} onChange={(text) => setCity(text)} onEnter={() => void 0} autoFocus />
          </div>

          <div>
            <label htmlFor={queryId} className="mb-1.5 block text-sm font-medium">
              What do you want to open?
            </label>
            <Input
              id={queryId}
              value={query}
              maxLength={300}
              placeholder="e.g. a specialty café for college students"
              className="h-11 text-base"
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="mt-2 flex flex-wrap gap-2" role="group" aria-label="Example businesses">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.chip}
                  type="button"
                  onClick={() => setQuery(ex.text)}
                  className="min-h-11 rounded-full border border-border bg-background/60 px-4 text-sm transition-colors hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 sm:min-h-9 sm:px-3"
                >
                  {ex.chip}
                </button>
              ))}
            </div>
          </div>

          <Button type="submit" disabled={!valid} className="h-11 w-full text-base">
            Find locations <ArrowRight aria-hidden />
          </Button>
        </form>

        <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
          Scores are relative to the city and rank areas using satellite growth, competition and demand signals.
          They are decision support, not a guarantee of success.
        </p>
      </section>

      <div className="pointer-events-auto mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
        <span className="text-muted-foreground">Try</span>
        {DEMOS.map((d) => (
          <button
            key={d.name}
            type="button"
            onClick={() => onSubmit(d.city, DEMO_QUERY)}
            className="glass min-h-11 rounded-full px-4 transition-colors hover:bg-primary/15 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {d.name}
          </button>
        ))}
      </div>
    </main>
  );
}
