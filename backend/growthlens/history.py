"""Yearly built-up history per hex for the time slider (Dynamic World annual mean 'built' probability).

Computed lazily on first use (one Earth Engine pass per batch of hexes, all years as bands), cached on disk,
and run in the background; the UI polls for the state.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import ee

from .config import settings
from .results import load_result
from .satellite import DW, EarthEngineError, _hex_collection, init_ee

BATCH = 300
_executor = ThreadPoolExecutor(max_workers=1)  # history passes are heavy; run one at a time
_state: dict[str, dict] = {}
_lock = threading.RLock()  # start() calls get_status() while holding it


def years() -> list[int]:
    return list(range(settings.history_start_year, date.today().year + 1))


def _file(result_id: str):
    d = settings.cache_dir / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{result_id}.json"


def _image(region: ee.Geometry) -> ee.Image:
    bands = [
        ee.ImageCollection(DW)
        .filterBounds(region)
        .filterDate(f"{y}-01-01", f"{y + 1}-01-01")
        .select("built")
        .mean()
        .rename(f"y{y}")
        for y in years()
    ]
    return ee.Image.cat(bands)


def _compute(result_id: str) -> None:
    st = _state[result_id]
    try:
        result = load_result(result_id)
        cells = [h["hex"] for h in result["hexes"]]
        minx, miny, maxx, maxy = result["city"]["bbox"]
        init_ee()
        image = _image(ee.Geometry.Rectangle([minx, miny, maxx, maxy]))
        ys = years()
        values: dict[str, list[float | None]] = {}
        for i in range(0, len(cells), BATCH):
            chunk = cells[i : i + BATCH]
            res = image.reduceRegions(
                collection=_hex_collection(chunk), reducer=ee.Reducer.mean(), scale=10, tileScale=4
            ).getInfo()
            for f in res["features"]:
                pr = f["properties"]
                values[pr["hex"]] = [None if pr.get(f"y{y}") is None else round(pr[f"y{y}"], 3) for y in ys]
            st["progress"] = min(i + BATCH, len(cells)) / len(cells)
        data = {"years": ys, "values": values}
        _file(result_id).write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        st.update(state="done", data=data, progress=1.0)
    except Exception as e:  # noqa: BLE001 - surface a friendly message; the UI offers a retry
        msg = str(e) if isinstance(e, EarthEngineError) else "Growth history could not be computed right now."
        st.update(state="error", error=msg)


def get_status(result_id: str) -> dict:
    """Idle/running/done/error. Reads the disk cache so history survives server restarts."""
    with _lock:
        st = _state.get(result_id)
        if st is None and _file(result_id).exists():
            st = _state[result_id] = {"state": "done", "data": json.loads(_file(result_id).read_text(encoding="utf-8")), "progress": 1.0}
        return dict(st) if st else {"state": "idle"}


def start(result_id: str) -> dict:
    """Idempotent: starts a computation unless one is running/done. A failed one may be retried."""
    load_result(result_id)  # validates the id (raises ResultNotFound)
    with _lock:
        st = _state.get(result_id)
        if st is None and _file(result_id).exists():
            return get_status(result_id)
        if st is None or st["state"] == "error":
            _state[result_id] = {"state": "running", "progress": 0.0}
            _executor.submit(_compute, result_id)
    return get_status(result_id)
