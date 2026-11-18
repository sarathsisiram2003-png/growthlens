"""Pre-computed demo cities: a demo that works instantly and never depends on live data services.

Each demo is a folder in backend/demo/<slug>/ (committed to the repo):
  result.json           the full analysis (same file the live pipeline writes)
  history.json          yearly built-up history for the growth replay slider
  briefs.json           location briefs for the top areas
  imagery/<hex>_<year>.png   before/after satellite images for the top areas
plus backend/demo/index.json listing them. On startup `install()` copies each pack into the places the rest of the app
already reads from (results folder, caches), so every existing endpoint serves demo data with no special cases.
"""
import json
import shutil
from pathlib import Path

from .config import BASE_DIR, settings

DEMO_DIR = BASE_DIR / "demo"
_briefs: dict[str, dict] = {}  # f"{result_id}:{hex}" -> brief dict


def index() -> list[dict]:
    f = DEMO_DIR / "index.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def get_entry(slug: str) -> dict | None:
    return next((e for e in index() if e["slug"] == slug), None)


def load_result(slug: str) -> dict | None:
    e = get_entry(slug)
    f = DEMO_DIR / slug / "result.json" if e else None
    return json.loads(f.read_text(encoding="utf-8")) if f and f.exists() else None


def get_brief(result_id: str, hex_id: str) -> dict | None:
    """A pre-written brief, if this result is a demo and the area was pre-computed."""
    return _briefs.get(f"{result_id}:{hex_id}")


def install() -> int:
    """Copy every demo pack into the app's data folders. Cheap and safe to run on every start."""
    n = 0
    for e in index():
        pack = DEMO_DIR / e["slug"]
        res = pack / "result.json"
        if not res.exists():
            continue
        rid = e["result_id"]
        out = settings.output_dir / f"{rid}.json"
        if not out.exists() or out.stat().st_size != res.stat().st_size:
            shutil.copyfile(res, out)
        hist = pack / "history.json"
        if hist.exists():
            dst = settings.cache_dir / "history" / f"{rid}.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copyfile(hist, dst)
        img_dir = pack / "imagery"
        if img_dir.exists():
            dst_dir = settings.cache_dir / "imagery"
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in [*img_dir.glob("*.png"), *img_dir.glob("*.none")]:  # .none = no usable imagery for that year
                if not (dst_dir / f.name).exists():
                    shutil.copyfile(f, dst_dir / f.name)
        briefs = pack / "briefs.json"
        if briefs.exists():
            for hex_id, b in json.loads(briefs.read_text(encoding="utf-8")).items():
                _briefs[f"{rid}:{hex_id}"] = b
        n += 1
    return n


def write_index(entries: list[dict]) -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "index.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")


def pack_dir(slug: str) -> Path:
    d = DEMO_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d
