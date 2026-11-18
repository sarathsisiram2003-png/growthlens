"""Plain-language one-line reasons for ranked areas, generated from the scores (no LLM needed)."""

# metric -> (phrase when strong, min normalised value to qualify). 'competition' is already inverted
# in the stored norms: high = few competitors.
_PHRASES = {
    "growth": "fast-growing built-up area",
    "demand": "strong demand drivers nearby",
    "activity": "rising night-time activity",
    "competition": "few direct competitors",
    "access": "good transit access",
}
_STRONG = 0.7


def build_reason(norm: dict[str, float], raw: dict[str, float | None]) -> str:
    strong = sorted(
        (m for m in _PHRASES if norm.get(m, 0.5) >= _STRONG), key=lambda m: -norm[m]
    )[:3]
    if raw.get("competition") == 0 and "competition" in strong:
        phrases = [("no mapped competitors" if m == "competition" else _PHRASES[m]) for m in strong]
    else:
        phrases = [_PHRASES[m] for m in strong]
    text = ", ".join(phrases).capitalize() if phrases else "Balanced profile across all signals"
    cautions = []
    if norm.get("competition", 0.5) <= 0.3:
        cautions.append("crowded with competitors")
    if norm.get("demand", 0.5) <= 0.3:
        cautions.append("few demand drivers")
    if cautions:
        text += f"; watch out: {' and '.join(cautions)}"
    return text + "."
