"""Thin wrapper around Gemini structured-JSON generation, shared by intent parsing and location briefs."""
import json

from google import genai
from google.genai import types

from .config import settings


def generate_json(system: str, content: str, schema: dict, max_tokens: int = 4000, temperature: float = 0.2) -> dict:
    """Returns the parsed JSON object. Raises on any failure; callers decide how to fall back."""
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=60_000, retry_options=types.HttpRetryOptions(attempts=3)),
    )
    resp = client.models.generate_content(
        model=settings.llm_model,
        contents=content,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
        ),
    )
    if not resp.text:
        reason = resp.candidates[0].finish_reason if resp.candidates else "no candidates"
        raise ValueError(f"LLM returned no output ({reason})")
    return json.loads(resp.text)
