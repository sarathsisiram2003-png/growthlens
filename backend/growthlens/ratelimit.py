"""Small in-memory sliding-window rate limiter for the endpoints that spend Earth Engine / Gemini quota.

Per client (IP) and bucket. In-memory is enough for a single-process deployment; behind several workers each
would count separately (use a shared store such as Redis if that ever matters). Set TRUST_PROXY=true only when
a proxy you control sets X-Forwarded-For, otherwise clients could spoof their address.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import settings

# bucket -> (max requests, window in seconds)
LIMITS: dict[str, tuple[int, int]] = {
    "jobs": (20, 3600),  # new analyses (each can cost minutes of Earth Engine + Overpass work)
    "brief": (40, 600),  # LLM calls
    "intent": (30, 600),  # LLM calls (business parsing preview)
    "imagery": (150, 600),  # Earth Engine thumbnails (cached ones are cheap, but count anyway)
    "history": (10, 3600),  # multi-year Earth Engine passes
    "area_name": (120, 600),  # Nominatim lookups
}

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_id(request: Request) -> str:
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(bucket: str, client: str, now: float | None = None) -> int:
    """Record a hit. Returns 0 if allowed, else the seconds until the client may try again."""
    limit, window = LIMITS[bucket]
    now = time.time() if now is None else now
    with _lock:
        q = _hits[(bucket, client)]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return max(1, int(q[0] + window - now) + 1)
        q.append(now)
        if len(_hits) > 20_000:  # keep memory bounded under a flood of distinct clients
            for k in [k for k, v in _hits.items() if not v or v[-1] <= now - LIMITS[k[0]][1]]:
                _hits.pop(k, None)
        return 0


def reset() -> None:
    with _lock:
        _hits.clear()


def limit(bucket: str):
    """FastAPI dependency: raises 429 with Retry-After when the client is over the bucket's limit."""

    def dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        retry = check(bucket, client_id(request))
        if retry:
            minutes = max(1, round(retry / 60))
            raise HTTPException(
                429,
                f"Too many requests. Please try again in about {minutes} minute{'s' if minutes != 1 else ''}.",
                headers={"Retry-After": str(retry)},
            )

    return dependency
