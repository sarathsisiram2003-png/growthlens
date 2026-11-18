# GrowthLens — AI site selection from satellite growth data

## What we are building
A web app where a user types ANY city in the world and describes the business they want to open
(e.g. "a specialty café for college students", "24x7 pharmacy", "budget gym"). The app finds and
ranks the best areas in that city to open it, shown on an interactive heatmap, with an AI-written
reason for each recommended location.

Positioning: AI decision support that ranks the best areas WITHIN a city using satellite growth,
competition and demand signals. Scores are relative to the city, not a guarantee of success.
Never claim otherwise in the UI.

Owner: Sarath (MBA, Operations). This is a portfolio project for placements, so: clean code,
a strong README with an architecture diagram, measurable results (backtest), and a demo that never fails.

## Core user flow
1. User enters a city (autocomplete, worldwide) + a free-text description of the business.
2. AI parses the intent into: business category, OSM competitor tags, demand-driver tags
   (colleges, offices, homes, transit, hospitals…) and scoring weights.
3. Backend splits the city into H3 hexagons (resolution 8 by default, ~0.7 km²).
4. For each hex compute:
   - Growth: change in built-up probability (Google Dynamic World, 10 m) over the last 1–3 years
   - Activity: night-light trend (NASA/NOAA VIIRS monthly composites)
   - Competition: count of same-category places (OpenStreetMap / Overpass)
   - Demand drivers: weighted count of relevant amenities (OpenStreetMap)
   - Access: roads / transit stops nearby
5. Opportunity score = weighted, normalised combination (weights come from step 2, user can adjust).
6. Return top 10 hexes; LLM writes a short location brief for each.
7. Results are cached per (city, intent) so repeat searches are instant.

## Architecture
- frontend/  Next.js (App Router) + TypeScript + Tailwind + shadcn/ui
             Map: MapLibre GL JS (free, no token) + deck.gl H3HexagonLayer for the heatmap
- backend/   Python FastAPI
             earthengine-api (Dynamic World, VIIRS), h3, geopandas/shapely,
             Overpass API for OSM, Nominatim for geocoding (respect usage policy + User-Agent),
             LLM API for intent parsing and briefs (structured JSON output)
- cache:     SQLite locally, Postgres/Supabase in production
- jobs:      analysis of a new city runs as a background job; frontend polls job status
- demo:      3–4 PRE-COMPUTED demo cities (Bengaluru, Dubai, London, + one more) stored as JSON
             so the demo works instantly and offline from external APIs
- secrets in .env only (EE service account, LLM key). Never commit them.

## UI / UX spec (this matters — aim for a product that looks shipped, not a student demo)
Feel: a calm, premium mapping tool. Map is the hero; UI floats over it.

Screen 1 — Start
- Full-screen map of the world, slowly drifting, subtle dark/neutral basemap.
- One centred floating search card: "Where?" (city autocomplete) and
  "What do you want to open?" (free text, with example chips: Café, Pharmacy, Gym, Clinic,
  EV charging, Supermarket). One primary button: "Find locations".
- Demo-city chips below: "Try Bengaluru · Dubai · London".

Screen 2 — Analysing (never a blank spinner)
- Map flies to the city and draws its boundary.
- Step-by-step progress list that ticks off live: Understanding your business → Mapping the city
  → Reading satellite history → Counting competitors → Scoring areas → Writing briefs.
- Show what the AI understood ("Category: café · Competitors: cafés, coffee shops ·
  Demand: colleges, offices, co-working") with an Edit link.

Screen 3 — Results (main screen)
- Map: H3 hexagon heatmap of opportunity score, sequential colour scale, legend bottom-left.
  Top 10 hexes outlined and numbered.
- Left panel (desktop) / bottom sheet (mobile): ranked list of the top 10 as cards —
  rank, area name (reverse-geocoded), score /100, 3 mini bars (Growth, Demand, Competition),
  one-line reason. Hover a card ⇄ highlight its hex; click a hex ⇄ open its card.
- Top bar: city + intent summary, "Edit search", layer toggles
  (Opportunity · Growth · Night lights · Competitors · Demand drivers),
  and a time slider (2016 → today) to replay growth.
- Data-quality badge: warns when OSM coverage in the city looks thin.

Screen 4 — Location detail (drawer)
- Before/after satellite slider for that hex (earliest vs latest year).
- Score breakdown with plain-language explanations and the raw numbers.
- AI location brief (why here, risks, suggested format).
- Nearby competitors list. Buttons: "Add to compare", "Export".

Screen 5 — Compare
- 2–3 locations side by side: scores, metrics, briefs, mini maps.

Also
- Weight sliders ("What matters more to you?") that re-rank instantly, client-side.
- Export a PDF report of the results.
- Keyboard accessible, visible focus, 44px targets, works at 360px width.
- Light and dark mode. Loading skeletons. Friendly empty and error states.
- Methodology page explaining data sources, scoring and limitations honestly.

## Build phases (do them in order; stop for review at the end of each)
1. Backend pipeline for ONE city (Bengaluru): geocode → H3 grid → OSM counts → Dynamic World
   growth → VIIRS trend → score → JSON. CLI script first, then FastAPI endpoint.
2. Intent parsing with the LLM (structured output) + configurable weights per business type.
3. Frontend: start screen, analysing screen, results map + ranked list, wired to the API.
4. Detail drawer, compare view, weight sliders, time slider, layer toggles, PDF export.
5. Background jobs + caching + any-city support + data-quality checks.
6. Backtest: run on 2019–20 data, check whether flagged hexes grew by 2024–25; report results
   in the README. Pre-compute demo cities. Deploy (frontend Vercel, backend Render/Railway).

## Rules
- Prefer small, reviewable steps; explain what you changed after each step.
- Write tests for the scoring logic.
- Handle API failures gracefully (timeouts, rate limits, missing data) — never crash the UI.
- Respect OSM/Nominatim/Overpass usage policies (rate limiting, caching, User-Agent).
- Earth Engine is used under non-commercial terms for this portfolio project.
