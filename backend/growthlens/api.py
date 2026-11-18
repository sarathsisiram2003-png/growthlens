"""FastAPI wrapper. Phase 2: free-text intent. Phase 5 moves analysis to background jobs."""
import hashlib
import json

from fastapi import FastAPI, HTTPException, Query

from .config import settings
from .geocode import GeocodeError
from .intent import parse_intent
from .osm import OverpassError
from .pipeline import run_pipeline, save_result, slug
from .satellite import EarthEngineError

app = FastAPI(title="GrowthLens API", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _parse(query: str):
    try:
        return parse_intent(query)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/intent")
def intent(query: str = Query(..., max_length=300)) -> dict:
    """Preview what the AI understood (shown on the Analysing screen, editable by the user)."""
    parsed, warning = _parse(query)
    return {"intent": parsed.model_dump(), "warning": warning}


@app.get("/analyze")
def analyze(city: str = Query("Bengaluru"), query: str = Query("cafe", max_length=300), refresh: bool = False) -> dict:
    parsed, warning = _parse(query)
    # Cache per (city, intent): hash the full intent so edited tags/weights don't collide.
    h = hashlib.sha1(json.dumps(parsed.model_dump(), sort_keys=True).encode()).hexdigest()[:10]
    path = settings.output_dir / f"{slug(city)}_{parsed.category_key}_{h}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        result = run_pipeline(city, parsed)
    except GeocodeError as e:
        raise HTTPException(404, str(e)) from e
    except (OverpassError, EarthEngineError) as e:
        raise HTTPException(502, str(e)) from e
    if warning:
        result["data_quality"]["flags"].append("intent_fallback_preset")
    save_result(result, path)
    return result
