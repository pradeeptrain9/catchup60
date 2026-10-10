"""Numeric guard for model-generated narration.

Ported from agrin, where the rule was that a model must never invent an
irrigation depth. Here the stake is lower but the mechanism is the same: the
engine decides which plays mattered and what the score was, and the model only
chooses words. A model that writes "a three-run double in the fifth" over a
two-run double in the sixth has produced a confident, fluent, wrong recap, and
"we told it not to" is not an enforcement mechanism.

So the guard is mechanical: collect every number the engine's payload contains,
extract every number the model wrote, and reject the narration if the model
produced one the engine never did. Rejection triggers one corrective retry, then
falls back to the deterministic template narrator.

Numbers inside payload *strings* count as allowed, because StatsAPI's own play
descriptions legitimately carry figures ("doubles (28)", "homers (17)").

Known limit: this catches digits, not words. "seven plays" is invisible to it.
The template narrator therefore never spells out a count, and the model prompt
forbids spelled numerals rather than relying on the guard to catch them.
"""

import re

# Matches integers, decimals and thousands-separated numbers, with an optional
# leading sign. Deliberately greedy about separators so "1,250.5" is one number.
NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _normalise(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def numbers_in_text(text: str) -> list[float]:
    out: list[float] = []
    for match in NUMBER_RE.findall(text or ""):
        value = _normalise(match)
        if value is not None:
            out.append(value)
    return out


def collect_allowed_numbers(payload) -> set[float]:
    """Every number the engine produced, including those inside note strings."""
    allowed: set[float] = set()

    def walk(node) -> None:
        if isinstance(node, bool):
            return  # bools are ints in Python; they are not quantities
        if isinstance(node, (int, float)):
            allowed.add(float(node))
        elif isinstance(node, str):
            allowed.update(numbers_in_text(node))
        elif isinstance(node, dict):
            for key, value in node.items():
                allowed.update(numbers_in_text(str(key)))
                walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(payload)

    # A model may legitimately round: 45.4 mm -> "45 mm". Admit the rounded
    # forms of every allowed value rather than loosening the comparison.
    for value in list(allowed):
        allowed.add(round(value))
        allowed.add(round(value, 1))
    return allowed


def is_supported(value: float, allowed: set[float]) -> bool:
    if value in allowed:
        return True
    for candidate in allowed:
        # Absolute tolerance for small numbers, relative for large ones.
        tolerance = max(0.05, abs(candidate) * 0.005)
        if abs(value - candidate) <= tolerance:
            return True
    return False


def unsupported_numbers(text: str, allowed: set[float]) -> list[float]:
    """Numbers the model wrote that the engine never produced."""
    return [n for n in numbers_in_text(text) if not is_supported(n, allowed)]


def check_segments(segments: list[dict], payload) -> list[str]:
    """Validate narration segments against the engine payload.

    Returns human-readable violations; empty means every figure spoken was one
    the engine computed.
    """
    allowed = collect_allowed_numbers(payload)
    violations: list[str] = []
    for index, segment in enumerate(segments):
        label = f"segment[{index}]({segment.get('kind', '?')})"
        bad = unsupported_numbers(segment.get("text", ""), allowed)
        if bad:
            rendered = ", ".join(f"{n:g}" for n in bad)
            violations.append(f"{label} contains figures not in the data: {rendered}")
    return violations
