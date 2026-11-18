"""FastAPI app. Jobs run in the background; the frontend polls for progress."""
import json
import os

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import history
from .brief import build_brief
from .geocode import reverse_area
from .grid import is_hex
from .imagery import ImageryError, thumbnail_png, valid_year
from .intent import parse_intent
from .jobs import get_job, start_job
from .results import ResultNotFound, find_hex, load_result
from .satellite import EarthEngineError

app = FastAPI(title="GrowthLens API", version="0.4.0")

# Frontend origins; override in production with CORS_ORIGINS="https://app.example.com,..."
_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in _origins], allow_methods=["GET", "POST"], allow_headers=["*"])


class JobRequest(BaseModel):
    city: str = Field(min_length=2, max_length=200)
    query: str = Field(min_length=2, max_length=300)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/intent")
def intent(query: str = Query(..., max_length=300)) -> dict:
    """Preview what the AI understood (shown on the Analysing screen)."""
    try:
        parsed, warning = parse_intent(query)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"intent": parsed.model_dump(), "warning": warning}


@app.post("/jobs", status_code=202)
def create_job(req: JobRequest) -> dict:
    return start_job(req.city, req.query).public()


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job (the server may have restarted). Please search again.")
    return job.public()


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job. Please search again.")
    if job.status != "done" or job.result_path is None:
        raise HTTPException(409, f"Job is {job.status}")
    return json.loads(job.result_path.read_text(encoding="utf-8"))


def _result(result_id: str) -> dict:
    try:
        return load_result(result_id)
    except ResultNotFound as e:
        raise HTTPException(404, str(e)) from e


@app.get("/results/{result_id}")
def get_result(result_id: str) -> dict:
    return _result(result_id)


@app.get("/results/{result_id}/brief/{hex_id}")
def location_brief(result_id: str, hex_id: str) -> dict:
    """AI-written brief for one area (falls back to a template if the LLM is unavailable)."""
    result = _result(result_id)
    try:
        row = find_hex(result, hex_id)
    except ResultNotFound as e:
        raise HTTPException(404, str(e)) from e
    return build_brief(result, row).model_dump()


@app.post("/results/{result_id}/history", status_code=202)
def start_history(result_id: str) -> dict:
    try:
        st = history.start(result_id)
    except ResultNotFound as e:
        raise HTTPException(404, str(e)) from e
    return {k: v for k, v in st.items() if k != "data"}


@app.get("/results/{result_id}/history")
def get_history(result_id: str) -> dict:
    _result(result_id)
    return history.get_status(result_id)


@app.get("/imagery/{hex_id}")
def imagery(hex_id: str, year: int = Query(...)) -> Response:
    """Sentinel-2 annual composite for one area, as PNG (cached; first request per image takes a few seconds)."""
    if not is_hex(hex_id):
        raise HTTPException(400, "Invalid area id")
    if not valid_year(year):
        raise HTTPException(400, "Satellite imagery is available from 2017 onwards")
    try:
        png = thumbnail_png(hex_id, year)
    except (ImageryError, EarthEngineError) as e:
        raise HTTPException(502, str(e)) from e
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/area-name")
def area_name(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> dict:
    return {"name": reverse_area(lat, lon)}
