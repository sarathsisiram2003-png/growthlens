// MapLibre GL v6 locates its web worker relative to the bundled main script, which breaks under
// Next/Turbopack chunking. We serve the worker from /public instead and call setWorkerUrl() (MapView.tsx).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "public", "maplibre");
mkdirSync(out, { recursive: true });
copyFileSync(
  join(root, "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs"),
  join(out, "maplibre-gl-worker.mjs"),
);
console.log("Copied maplibre-gl-worker.mjs -> public/maplibre/");
