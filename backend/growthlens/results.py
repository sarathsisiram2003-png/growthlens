"""Safe access to saved analysis results by id (the result file's stem)."""
import json
import re
from pathlib import Path

from .config import settings

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,120}$")
HEX_RE = re.compile(r"^[0-9a-f]{15}$")  # H3 cell index


class ResultNotFound(LookupError):
    pass


def result_file(result_id: str) -> Path:
    """Resolve an id to a file inside the output dir. Rejects anything that isn't a plain slug."""
    if not _ID_RE.match(result_id):
        raise ResultNotFound("Unknown result")
    path = (settings.output_dir / f"{result_id}.json").resolve()
    if path.parent != settings.output_dir.resolve() or not path.exists():
        raise ResultNotFound("Unknown result. Please search again.")
    return path


def load_result(result_id: str) -> dict:
    return json.loads(result_file(result_id).read_text(encoding="utf-8"))


def find_hex(result: dict, hex_id: str) -> dict:
    if not HEX_RE.match(hex_id):
        raise ResultNotFound("Invalid area id")
    for h in result["hexes"]:
        if h["hex"] == hex_id:
            return h
    raise ResultNotFound("That area is not part of this result")
