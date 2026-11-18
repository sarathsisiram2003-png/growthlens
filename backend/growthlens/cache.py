"""Tiny SQLite key/value cache for JSON-serialisable API responses."""
import json
import sqlite3
import time
from typing import Any

from .config import settings

_DB = settings.cache_dir / "cache.sqlite"


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_DB)
    con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, ts REAL)")
    return con


def get(key: str, max_age_s: float | None = None) -> Any | None:
    with _conn() as con:
        row = con.execute("SELECT v, ts FROM kv WHERE k=?", (key,)).fetchone()
    if row is None:
        return None
    if max_age_s is not None and time.time() - row[1] > max_age_s:
        return None
    return json.loads(row[0])


def put(key: str, value: Any) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO kv (k, v, ts) VALUES (?, ?, ?)",
            (key, json.dumps(value), time.time()),
        )
