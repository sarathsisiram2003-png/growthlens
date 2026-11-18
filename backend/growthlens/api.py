"""FastAPI wrapper. Phase 1: synchronous; Phase 5 moves this to background jobs."""
import json

from fastapi import FastAPI, HTTPException, Query

from .geocode import GeocodeError
from .osm import OverpassError
from .pipeline import run_pipeline, save_result, slug
from .config import settings
from .satellite import EarthEngineError

app = FastAPI(title="GrowthLens API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/analyze")
def analyze(city: str = Query("Bengaluru"), category: str = Query("cafe"), refresh: bool = False) -> dict:
    path = settings.output_dir / f"{slug(city)}_{category}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        result = run_pipeline(city, category)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except GeocodeError as e:
        raise HTTPException(404, str(e)) from e
    except (OverpassError, EarthEngineError) as e:
        raise HTTPException(502, str(e)) from e
    save_result(result, path)
    return result
