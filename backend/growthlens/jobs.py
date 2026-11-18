"""Background analysis jobs with live step progress, persisted in SQLite.

- The frontend polls GET /jobs/{id} to tick off steps and fetches the result when status == "done".
- Jobs survive a server restart: unfinished ones are re-queued on startup (the pipeline's caches make a
  resumed job cheap), finished ones stay readable until they expire.
- Identical in-flight searches share one job; cancelling only stops it when nobody else is waiting on it.
"""
import hashlib
import json
import sqlite3
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
from .quality import add_flag

STEPS = [
    ("intent", "Understanding your business"),
    ("map", "Mapping the city"),
    ("satellite", "Reading satellite history"),
    ("competitors", "Counting competitors"),
    ("scoring", "Scoring areas"),
    ("briefs", "Writing briefs"),
]
_ORDER = [s for s, _ in STEPS]
ACTIVE = ("queued", "running")

_executor = ThreadPoolExecutor(max_workers=settings.job_workers)
_jobs: dict[str, "Job"] = {}
_by_key: dict[str, str] = {}
_waiting: list[str] = []  # queued job ids, in order
_lock = threading.RLock()


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass


@dataclass
class Job:
    id: str
    city: str
    query: str
    key: str = ""
    status: str = "queued"  # queued | running | done | error | cancelled
    steps: dict[str, str] = field(default_factory=lambda: {s: "pending" for s in _ORDER})
    message: str = ""
    intent: dict | None = None
    warning: str | None = None
    meta: dict = field(default_factory=dict)  # boundary / center once known
    error: str | None = None
    result_path: Path | None = None
    result_id: str | None = None
    created: float = field(default_factory=time.time)
    # runtime only (not persisted)
    refs: int = 1  # how many searches are waiting on this job
    cancelled: bool = False
    started: float | None = None
    refresh: bool = False

    def public(self) -> dict:
        with _lock:
            pos = _waiting.index(self.id) + 1 if self.status == "queued" and self.id in _waiting else None
        return {
            "id": self.id, "city": self.city, "query": self.query, "status": self.status,
            "steps": [{"id": s, "label": l, "state": self.steps[s]} for s, l in STEPS],
            "message": self.message, "intent": self.intent, "warning": self.warning,
            "meta": self.meta, "error": self.error, "result_id": self.result_id, "queue_position": pos,
        }


# ---------------------------------------------------------------- persistence

def _db() -> sqlite3.Connection:
    path = settings.data_dir / "jobs.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, key TEXT, city TEXT, query TEXT, status TEXT, steps TEXT, message TEXT,
            intent TEXT, warning TEXT, meta TEXT, error TEXT, result_id TEXT, created REAL, updated REAL)"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status)")
    return con


def _save(job: Job) -> None:
    con = _db()
    try:
        with con:
            con.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.id, job.key, job.city, job.query, job.status, json.dumps(job.steps), job.message,
                 json.dumps(job.intent), job.warning, json.dumps(job.meta), job.error, job.result_id,
                 job.created, time.time()),
            )
    finally:
        con.close()


def _from_row(row: tuple) -> Job:
    (jid, key, city, query, status, steps, message, intent, warning, meta, error, result_id, created, _upd) = row
    job = Job(
        id=jid, city=city, query=query, key=key or "", status=status, steps=json.loads(steps), message=message or "",
        intent=json.loads(intent) if intent else None, warning=warning, meta=json.loads(meta) if meta else {},
        error=error, result_id=result_id, created=created,
    )
    if result_id:
        job.result_path = settings.output_dir / f"{result_id}.json"
    return job


def _query(sql: str, args: tuple = ()) -> list[tuple]:
    con = _db()
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def _load(job_id: str) -> Job | None:
    rows = _query("SELECT * FROM jobs WHERE id=?", (job_id,))
    return _from_row(rows[0]) if rows else None


def prune() -> int:
    """Delete finished jobs older than the retention period."""
    cutoff = time.time() - settings.job_retention_days * 86400
    con = _db()
    try:
        with con:
            return con.execute(
                "DELETE FROM jobs WHERE updated < ? AND status NOT IN ('queued','running')", (cutoff,)
            ).rowcount
    finally:
        con.close()


def recover() -> int:
    """Called at startup: forget expired jobs and re-queue the ones a restart interrupted."""
    prune()
    rows = _query("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY created")
    for row in rows:
        job = _from_row(row)
        job.status, job.message = "queued", "Resuming after a restart"
        job.steps = {s: "pending" for s in _ORDER}
        with _lock:
            _jobs[job.id] = job
            _by_key[job.key] = job.id
            _waiting.append(job.id)
        _save(job)
        _executor.submit(_run, job)
    return len(rows)


# ---------------------------------------------------------------- running

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
        return "OpenStreetMap is busy right now. Please try again in a few minutes."
    if isinstance(e, JobTimeout):
        return "This analysis took too long and was stopped. Try again, or pick a smaller city."
    if isinstance(e, ValueError):  # includes AreaTooLarge; messages are written for users
        return str(e)
    return "Something went wrong while analysing this city. Please try again."


def _cached_result(path: Path) -> dict | None:
    """A saved result for this (city, intent) if it is current: right schema and not too old."""
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > settings.result_max_age_days * 86400:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if data.get("schema", 1) >= SCHEMA_VERSION else None


def _check(job: Job) -> None:
    if job.cancelled:
        raise JobCancelled()
    if job.started and time.time() - job.started > settings.job_timeout_s:
        raise JobTimeout()


def _run(job: Job) -> None:
    with _lock:
        if job.id in _waiting:
            _waiting.remove(job.id)
        if job.cancelled or job.status == "cancelled":
            job.status = "cancelled"
            _save(job)
            return
        job.status, job.started = "running", time.time()
    _save(job)
    try:
        _advance(job, "intent")
        job.message = "Reading your description"
        intent, warning = parse_intent(job.query)
        job.intent, job.warning = intent.model_dump(), warning
        _check(job)

        path = result_path(job.city, job.intent, intent.category_key)
        data = None if job.refresh else _cached_result(path)
        if data is not None:  # per (city, intent) cache: repeat searches are instant
            job.meta = {"boundary": data["city"]["boundary"], "center": [data["city"]["lat"], data["city"]["lon"]]}
            job.steps = {s: "done" for s in _ORDER}
            job.result_path, job.result_id = path, path.stem
            job.status, job.message = "done", "Loaded from cache"
            _save(job)
            return

        def on_progress(step: str, msg: str, meta: dict | None) -> None:
            _check(job)
            _advance(job, step, (meta or {}).get("state", "active"))
            job.message = msg
            if meta:
                job.meta.update({k: v for k, v in meta.items() if k in ("boundary", "center")})
            _save(job)

        result = run_pipeline(job.city, intent, progress=on_progress)
        _check(job)
        if warning:
            add_flag(result["data_quality"], "intent_fallback_preset")
        job.result_path = save_result(result, path)
        job.result_id = job.result_path.stem
        for s in _ORDER:
            if job.steps[s] != "skipped":
                job.steps[s] = "done"
        job.status, job.message = "done", "Done"
    except JobCancelled:
        job.status, job.message = "cancelled", "Cancelled"
        for s in _ORDER:
            if job.steps[s] == "active":
                job.steps[s] = "pending"
    except Exception as e:  # noqa: BLE001 - jobs must never crash the worker; surface a friendly error
        job.status, job.error = "error", _friendly(e)
        for s in _ORDER:
            if job.steps[s] == "active":
                job.steps[s] = "error"
    _save(job)


def start_job(city: str, query: str, refresh: bool = False) -> Job:
    key = f"{city.strip().lower()}|{query.strip().lower()}"
    with _lock:
        existing = _jobs.get(_by_key.get(key, ""))
        if existing and existing.status in ACTIVE and not existing.cancelled:
            existing.refs += 1  # identical in-flight search: share the job
            return existing
        job = Job(id=uuid.uuid4().hex[:12], city=city.strip(), query=query.strip(), key=key, refresh=refresh)
        _jobs[job.id] = job
        _by_key[key] = job.id
        _waiting.append(job.id)
        _evict()
    _save(job)
    _executor.submit(_run, job)
    return job


def cancel_job(job_id: str) -> Job | None:
    """Stop a job nobody else is waiting for. Safe to call repeatedly or on a finished job."""
    job = get_job(job_id)
    if job is None:
        return None
    with _lock:
        if job.status not in ACTIVE:
            return job
        job.refs -= 1
        if job.refs > 0:
            return job  # another search still wants this result
        job.cancelled = True
        was_queued = job.status == "queued"
        # Show "cancelled" at once. A running worker notices at its next progress/heartbeat check and stops.
        job.status, job.message = "cancelled", "Cancelled"
        if was_queued and job.id in _waiting:
            _waiting.remove(job.id)
    _save(job)
    return job


def _evict(keep: int = 200) -> None:
    """Bound memory: drop the oldest finished jobs from the in-memory table (they stay in SQLite)."""
    done = sorted((j for j in _jobs.values() if j.status not in ACTIVE), key=lambda j: j.created)
    for j in done[: max(0, len(_jobs) - keep)]:
        _jobs.pop(j.id, None)


def get_job(job_id: str) -> Job | None:
    job = _jobs.get(job_id)
    return job if job is not None else _load(job_id)
