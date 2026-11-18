import httpx
from google.genai import errors as genai_errors
import pytest
from pydantic import ValidationError

from growthlens import intent as intent_mod
from growthlens.intent import Driver, Intent, IntentCore, Tag, Weights, intent_from_preset, parse_intent
from growthlens.profiles import PRESETS, match_preset
from growthlens.scoring import METRICS


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """No real cache file, no real key unless a test sets one."""
    store: dict = {}
    monkeypatch.setattr(intent_mod.cache, "get", lambda k, max_age_s=None: store.get(k))
    monkeypatch.setattr(intent_mod.cache, "put", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "")
    return store


def llm_intent(**over) -> Intent:
    base = intent_from_preset("cafe").model_copy(update={"source": "llm", "summary": "students"})
    return base.model_copy(update=over)


# ---- validation / sanitisation (tags are interpolated into Overpass queries) ----

@pytest.mark.parametrize("bad", ['cafe"]; out;', "Amenity", "a b", "x" * 41, ""])
def test_tag_key_rejected(bad):
    with pytest.raises(ValidationError):
        Tag(key=bad, value="x")


@pytest.mark.parametrize("bad", ['cafe"', "a b", "x" * 41, "a;b)(", "é"])
def test_tag_value_rejected(bad):
    # quotes, brackets, spaces and non-ASCII never reach an Overpass query
    with pytest.raises(ValidationError):
        Tag(key="amenity", value=bad)


def test_tag_empty_value_means_any():
    assert Tag(key="office", value="").value == ""


def test_driver_weight_clamped():
    assert Driver(key="a", value="b", weight=99).weight == 5.0
    assert Driver(key="a", value="b", weight=-3).weight == 0.1


def test_tag_lists_capped():
    many = [Tag(key="amenity", value=f"v{i}") for i in range(20)]
    i = llm_intent(competitors=many)
    assert len(Intent.model_validate(i.model_dump()).competitors) == 8


def test_category_key_normalised():
    assert Intent.model_validate({**llm_intent().model_dump(), "category_key": "Pet Grooming!!"}).category_key == "pet_grooming"


def test_llm_schema_has_no_source_and_forbids_extra():
    schema = IntentCore.model_json_schema()
    assert "source" not in schema["properties"]
    assert schema["additionalProperties"] is False
    assert all(d.get("additionalProperties") is False for d in schema["$defs"].values())


# ---- presets ----

@pytest.mark.parametrize("key", list(PRESETS))
def test_every_preset_builds_valid_profile(key):
    prof = intent_from_preset(key).to_profile()
    assert prof["competitors"] and prof["demand"] and prof["access"]
    assert set(prof["weights"]) == set(METRICS)
    assert sum(prof["weights"].values()) == pytest.approx(1.0)
    assert all(v is None or isinstance(v, str) for _, v in prof["competitors"])  # "" mapped to None


def test_empty_value_becomes_any_in_profile():
    prof = intent_from_preset("cafe").to_profile()
    assert ("office", None) in prof["demand"]


@pytest.mark.parametrize(
    "text,key",
    [("a specialty café for college students", "cafe"), ("24x7 pharmacy", "pharmacy"), ("budget gym", "gym"),
     ("EV charging hub", "ev_charging"), ("grocery store", "supermarket"), ("dental clinic", "clinic")],
)
def test_match_preset(text, key):
    assert match_preset(text) == key


def test_match_preset_none():
    assert match_preset("alpaca farm") is None


# ---- parse_intent ----

def test_empty_text_rejected():
    with pytest.raises(ValueError):
        parse_intent("   ")


def test_no_key_falls_back_with_warning():
    i, warn = parse_intent("budget gym")
    assert i.category_key == "gym" and i.source == "preset"
    assert "GEMINI_API_KEY" in warn


def test_no_llm_flag_has_no_warning():
    i, warn = parse_intent("budget gym", use_llm=False)
    assert i.category_key == "gym" and warn is None


def test_unknown_business_offline_raises_friendly_error():
    with pytest.raises(ValueError, match="Try one of"):
        parse_intent("alpaca farm")


def test_llm_result_used_and_cached(monkeypatch):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")
    calls = []
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: calls.append(t) or llm_intent())
    i, warn = parse_intent("specialty café for college students")
    assert i.source == "llm" and warn is None
    parse_intent("Specialty café for college students ")  # same after normalisation
    assert len(calls) == 1


def test_llm_weights_are_normalised(monkeypatch):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")
    w = Weights(growth=2, activity=2, demand=2, competition=2, access=2)
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: llm_intent(weights=w))
    i, _ = parse_intent("anything")
    assert sum(i.weights.model_dump().values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "exc",
    [ValueError("LLM declined the request"), httpx.ConnectError("boom"), genai_errors.ServerError(503, {"error": {"message": "overloaded"}})],
)
def test_llm_failure_falls_back_to_preset(monkeypatch, exc):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")

    def boom(_t):
        raise exc

    monkeypatch.setattr(intent_mod, "_call_llm", boom)
    i, warn = parse_intent("24x7 pharmacy")
    assert i.category_key == "pharmacy" and i.source == "preset"
    assert "unavailable" in warn


def test_llm_failure_and_unknown_business_raises(monkeypatch):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: (_ for _ in ()).throw(ValueError("x")))
    with pytest.raises(ValueError):
        parse_intent("alpaca farm")


def test_llm_with_no_competitors_is_rejected(monkeypatch):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: llm_intent(competitors=[]))
    i, warn = parse_intent("budget gym")
    assert i.source == "preset" and warn


def test_long_input_truncated(monkeypatch):
    seen = []
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: seen.append(t) or llm_intent())
    parse_intent("cafe " + "x" * 1000)
    assert len(seen[0]) == 300


def test_any_exception_type_falls_back(monkeypatch):
    """The Google SDK raises httpx2 errors, not httpx ones; no exception type may escape."""
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "sk-test")

    class Httpx2ReadError(Exception):
        pass

    def boom(_t):
        raise Httpx2ReadError("connection forcibly closed")

    monkeypatch.setattr(intent_mod, "_call_llm", boom)
    i, warn = parse_intent("budget gym")
    assert i.source == "preset" and "Httpx2ReadError" in warn


def test_intent_llm_can_be_disabled_by_setting(monkeypatch):
    monkeypatch.setattr(intent_mod.settings, "gemini_api_key", "k")
    monkeypatch.setattr(intent_mod.settings, "intent_use_llm", False)
    monkeypatch.setattr(intent_mod, "_call_llm", lambda t: (_ for _ in ()).throw(AssertionError("LLM must not be called")))
    i, warn = parse_intent("budget gym")
    assert i.source == "preset" and warn is None
