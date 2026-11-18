"""FastAPI app. Jobs run in the background; the frontend polls for progress."""
import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .intent import parse_intent
from .jobs import get_job, start_job

app = FastAPI(title="GrowthLens API", version="0.3.0")

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
