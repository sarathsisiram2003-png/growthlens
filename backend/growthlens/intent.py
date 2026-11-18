"""Turn a free-text business description into a validated scoring profile.

The LLM proposes category, OSM tags and weights as structured JSON. Everything it returns is
validated and sanitised before it reaches Overpass (tags are interpolated into queries).
If the LLM is unavailable, refuses, or returns something invalid, we fall back to a keyword-matched
preset so the app never fails because of this step.
"""
import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import cache
from .config import settings
from .llm import generate_json
from .profiles import PRESETS, match_preset
from .scoring import validate_weights

KEY_RE = re.compile(r"^[a-z_:]{1,40}$")
VALUE_RE = re.compile(r"^[A-Za-z0-9_:;-]{0,40}$")  # "" = any value
MAX_TAGS = 8
INTENT_CACHE_AGE = 30 * 24 * 3600


class Tag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str = Field(description='OSM tag value, or "" to match any value for the key')

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        if not KEY_RE.match(v):
            raise ValueError(f"invalid OSM key: {v!r}")
        return v

    @field_validator("value")
    @classmethod
    def _value(cls, v: str) -> str:
        if not VALUE_RE.match(v):
            raise ValueError(f"invalid OSM value: {v!r}")
        return v


class Driver(Tag):
    weight: float = Field(description="Relative importance, 0.1 to 5")

    @field_validator("weight")
    @classmethod
    def _w(cls, v: float) -> float:
        return min(max(v, 0.1), 5.0)


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    growth: float
    activity: float
    demand: float
    competition: float
    access: float


class IntentCore(BaseModel):
    """The part the LLM fills in (this is the JSON schema sent to the API)."""

    model_config = ConfigDict(extra="forbid")

    category_key: str = Field(description="Preset key if one fits, else a short snake_case id")
    label: str = Field(description="Human-readable business type, e.g. 'Specialty café'")
    summary: str = Field(description="One sentence: who the customers are and what matters most")
    competitors: list[Tag] = Field(description="OSM tags of directly competing places")
    demand_drivers: list[Driver] = Field(description="OSM tags of places that generate customers, with weights")
    access: list[Tag] = Field(description="OSM tags for transport access relevant to this business")
    weights: Weights

    @field_validator("category_key")
    @classmethod
    def _ck(cls, v: str) -> str:
        v = re.sub(r"[^a-z0-9_]+", "_", v.lower()).strip("_")
        return v[:40] or "custom"

    @field_validator("competitors", "demand_drivers", "access")
    @classmethod
    def _cap(cls, v: list) -> list:
        return v[:MAX_TAGS]

    def to_profile(self) -> dict:
        """Shape consumed by osm.osm_metrics and scoring."""
        norm = lambda t: (t.key, t.value or None)  # noqa: E731 - "" -> any value
        w = validate_weights(self.weights.model_dump())
        return {
            "label": self.label,
            "competitors": [norm(t) for t in self.competitors],
            "demand": {norm(d): d.weight for d in self.demand_drivers},
            "access": [norm(t) for t in self.access],
            "weights": w,
        }

    @property
    def slug(self) -> str:
        return self.category_key


class Intent(IntentCore):
    """Validated intent plus where it came from."""

    model_config = ConfigDict(extra="forbid")
    source: Literal["llm", "preset"] = "llm"


def intent_from_preset(key: str, source: Literal["llm", "preset"] = "preset") -> Intent:
    p = PRESETS[key]
    return Intent(
        category_key=key,
        label=p["label"],
        summary=f"{p['label']} (preset profile)",
        competitors=[Tag(key=k, value=v) for k, v in p["competitors"]],
        demand_drivers=[Driver(key=k, value=v, weight=w) for k, v, w in p["demand"]],
        access=[Tag(key=k, value=v) for k, v in p["access"]],
        weights=Weights(**p["weights"]),
        source=source,
    )


SYSTEM_PROMPT = """You convert a business idea into a site-selection profile for a map of one city.
The profile drives scoring of ~0.7 km² hexagonal areas using OpenStreetMap (OSM) data.

Rules:
- competitors: OSM tags of places that directly compete (same customer need). Use real, common OSM tags.
- demand_drivers: OSM tags of places that bring this business's customers, weight 0.1-5 (higher = stronger).
  Use value "" to match any value for a key (e.g. key "office").
- access: transport tags that matter for this business (e.g. highway=bus_stop, railway=station).
- weights: relative importance of five signals for THIS business: growth (satellite built-up growth),
  activity (night-light trend), demand (demand drivers), competition (fewer competitors is better),
  access. Any positive numbers; they are normalised later.
- If the idea matches a preset below, reuse its category_key; otherwise invent a short snake_case key.
- Reflect the specifics the user gave (e.g. "for college students" raises weight on colleges).
- Use only keys/values that exist in OSM. Do not invent tags. At most 8 tags per list.

Presets (category_key: label): """ + "; ".join(f"{k}: {p['label']}" for k, p in PRESETS.items())


def _cache_key(text: str) -> str:
    h = hashlib.sha1(f"{settings.llm_model}|{text.strip().lower()}".encode()).hexdigest()
    return f"intent:{h}"


def _call_llm(text: str) -> Intent:
    raw = generate_json(SYSTEM_PROMPT, f"Business idea: {text}", IntentCore.model_json_schema())
    return Intent.model_validate({**raw, "source": "llm"})


def parse_intent(text: str, use_llm: bool = True) -> tuple[Intent, str | None]:
    """Returns (intent, warning). warning is set when we fell back to a preset or could not understand."""
    text = text.strip()
    if not text:
        raise ValueError("Please describe the business you want to open")
    if len(text) > 300:
        text = text[:300]
    use_llm = use_llm and settings.intent_use_llm

    if use_llm and settings.gemini_api_key:
        cached = cache.get(_cache_key(text), INTENT_CACHE_AGE)
        if cached is not None:
            return Intent.model_validate(cached), None
        try:
            intent = _call_llm(text)
            intent.weights = Weights(**validate_weights(intent.weights.model_dump()))
            if not intent.competitors:
                raise ValueError("LLM returned no competitor tags")
            cache.put(_cache_key(text), intent.model_dump())
            return intent, None
        except Exception as e:  # noqa: BLE001 - ANY LLM failure (API, network via httpx2, bad JSON) must fall back
            warning = f"AI intent parsing unavailable ({type(e).__name__}); used a preset profile"
    elif use_llm:
        warning = "No GEMINI_API_KEY set; used a preset profile"
    else:
        warning = None

    key = match_preset(text)
    if key is None:
        raise ValueError(
            "Could not understand that business type offline. "
            f"Try one of: {', '.join(PRESETS)} (or configure GEMINI_API_KEY)."
        )
    return intent_from_preset(key), warning

