"""Background analysis jobs with live step progress (in-memory; Phase 5 adds persistence).

The frontend polls GET /jobs/{id} to tick off steps and fetches the result when status == "done".
"""
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings
from .geocode import GeocodeError
from .intent import parse_intent
from .osm import OverpassError
from .pipeline import SCHEMA_VERSION, run_pipeline, save_result, slug

STEPS = [
    ("intent", "Understanding your business"),
    ("map", "Mapping the city"),
    ("satellite", "Reading satellite history"),
    ("competitors", "Counting competitors"),
    ("scoring", "Scoring areas"),
    ("briefs", "Writing briefs"),
]
_ORDER = [s for s, _ in STEPS]
MAX_JOBS = 50

_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, "Job"] = {}
_by_key: dict[str, str] = {}
_lock = threading.Lock()


@dataclass
class Job:
    id: str
    city: str
    query: str
    status: str = "queued"  # queued | running | done | error
    steps: dict[str, str] = field(default_factory=lambda: {s: "pending" for s in _ORDER})
    message: str = ""
    intent: dict | None = None
    warning: str | None = None
    meta: dict = field(default_factory=dict)  # boundary / center once known
    error: str | None = None
    result_path: Path | None = None
    result_id: str | None = None
    created: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id, "city": self.city, "query": self.query, "status": self.status,
            "steps": [{"id": s, "label": l, "state": self.steps[s]} for s, l in STEPS],
            "message": self.message, "intent": self.intent, "warning": self.warning,
            "meta": self.meta, "error": self.error, "result_id": self.result_id,
        }


def result_path(city: str, intent_dump: dict, category_key: str) -> Path:
    h = hashlib.sha1(json.dumps(intent_dump, sort_keys=True).encode()).hexdigest()[:10]
    return settings.output_dir / f"{slug(city)}_{category_key}_{h}.json"


def _advance(job: Job, step: str, state: str = "active") -> None:
    """Mark earlier active steps done, then set this step's state."""
    idx = _ORDER.index(step)
    for s in _ORDER[:idx]:
        if job.steps[s] in ("pending", "active"):
            job.steps[s] = "done"
    job.steps[step] = state


def _friendly(e: Exception) -> str:
    if isinstance(e, GeocodeError):
        return f"We couldn't find that city. {e}"
    if isinstance(e, OverpassError):
        return "OpenStreetMap is busy right now. Please try again in a minute."
    if isinstance(e, ValueError):
        return str(e)
    return "Something went wrong while analysing this city. Please try again."


def _run(job: Job) -> None:
    job.status = "running"
    try:
        _advance(job, "intent")
        job.message = "Reading your description"
        intent, warning = parse_intent(job.query)
        job.intent, job.warning = intent.model_dump(), warning

        path = result_path(job.city, job.intent, intent.category_key)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if data is not None and data.get("schema", 1) >= SCHEMA_VERSION:  # per (city, intent) cache: repeat searches are instant
            job.meta = {"boundary": data["city"]["boundary"], "center": [data["city"]["lat"], data["city"]["lon"]]}
            job.steps = {s: "done" for s in _ORDER}
            job.result_path, job.result_id = path, path.stem
            job.status, job.message = "done", "Loaded from cache"
            return

        def on_progress(step: str, msg: str, meta: dict | None) -> None:
            _advance(job, step, (meta or {}).get("state", "active"))
            job.message = msg
            if meta:
                job.meta.update({k: v for k, v in meta.items() if k in ("boundary", "center")})

        result = run_pipeline(job.city, intent, progress=on_progress)
        if warning:
            result["data_quality"]["flags"].append("intent_fallback_preset")
        job.result_path = save_result(result, path)
        job.result_id = job.result_path.stem
        for s in _ORDER:
            if job.steps[s] != "skipped":
                job.steps[s] = "done"
        job.status, job.message = "done", "Done"
    except Exception as e:  # noqa: BLE001 - jobs must never crash the worker; surface a friendly error
        job.status, job.error = "error", _friendly(e)
        for s in _ORDER:
            if job.steps[s] == "active":
                job.steps[s] = "error"


def start_job(city: str, query: str) -> Job:
    key = f"{city.strip().lower()}|{query.strip().lower()}"
    with _lock:
        existing = _jobs.get(_by_key.get(key, ""))
        if existing and existing.status in ("queued", "running"):
            return existing  # dedupe identical in-flight searches
        job = Job(id=uuid.uuid4().hex[:12], city=city.strip(), query=query.strip())
        _jobs[job.id] = job
        _by_key[key] = job.id
        while len(_jobs) > MAX_JOBS:  # drop oldest
            oldest = min(_jobs.values(), key=lambda j: j.created)
            _jobs.pop(oldest.id, None)
    _executor.submit(_run, job)
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)
