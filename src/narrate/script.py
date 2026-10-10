"""The deterministic narrator.

This path always works: no key, no network, no model. It is what ships when
Bedrock is unavailable, and it is what the guard falls back to when the model
writes a number the engine never produced. Because it formats engine output
directly, it cannot be wrong about the game.

Everything the viewer hears about a play is StatsAPI's own description. We clean
it, we never paraphrase it: a paraphrase is a chance to change the facts.
"""

import re

from ..engine.state import GameContext, GameState, Play, ordinal

# StatsAPI prefixes a reviewed play's description with the review itself:
#   "Mets challenged (tag play), call on the field was upheld: Luis Arraez out
#    on a sacrifice fly to left fielder Juan Soto. Bryce Harper scores."
# The play is real and belongs in the recap; the procedural preamble does not.
REVIEW_PREFIX = re.compile(
    r"^.*?call on the field was (?:upheld|overturned):\s*", re.IGNORECASE
)
# Umpire-initiated reviews use a different stem but the same colon convention.
UMPIRE_REVIEW_PREFIX = re.compile(
    r"^umpire review[^:]*:\s*", re.IGNORECASE
)


def clean_description(text: str) -> str:
    """Strip review bookkeeping, keep the play."""
    cleaned = REVIEW_PREFIX.sub("", text or "")
    cleaned = UMPIRE_REVIEW_PREFIX.sub("", cleaned)
    cleaned = cleaned.strip()
    if cleaned and not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    return cleaned


def half_phrase(play: Play) -> str:
    return f"{play.half.capitalize()} of the {ordinal(play.inning)}"


def intro_text(context: GameContext, state: GameState) -> str:
    """Where the game stands, before any history.

    Deliberately avoids spelling out how many plays follow: the guard checks
    digits, not words, so a spelled count is a figure nothing can verify.
    """
    half = "Top" if state.half == "top" else "Bottom"
    return (
        f"{half} of the {ordinal(state.inning)}. "
        f"{context.away_name} {state.away_score}, "
        f"{context.home_name} {state.home_score}. "
        f"Here's what you missed."
    )


def play_text(play: Play) -> str:
    return f"{half_phrase(play)}. {clean_description(play.description)}"


def outro_text(context: GameContext, state: GameState,
               finished: bool = False) -> str:
    """Close on the score, and hand off to wherever the viewer is going.

    `finished` is about the cursor, not about the game. A replay at --as-of 40
    of a game that ended hours ago is standing in for a moment when the game
    was live, so it says "back to live" — reading "that's your final" over a
    4-0 score in the fifth is the kind of wrongness that costs the viewer's
    trust in everything else the recap said.
    """
    score = (
        f"{context.away_name} {state.away_score}, "
        f"{context.home_name} {state.home_score}"
    )
    if finished:
        return f"That's your final: {score}."
    return f"That's how it got to {score}. Back to live."


def build_segments(
    context: GameContext, state: GameState, plays: list[Play],
    finished: bool = False,
) -> list[dict]:
    """Narration segments in play order, intro first, outro last.

    Timings are not set here. The TTS engine returns real per-segment durations
    and manifest.py stamps them; an estimate written in at this stage would
    silently become the thing the TV app trusts.
    """
    segments: list[dict] = [{"kind": "intro", "text": intro_text(context, state)}]
    for play in plays:
        segments.append({
            "kind": "play",
            "text": play_text(play),
            "playIndex": play.index,
        })
    segments.append(
        {"kind": "outro", "text": outro_text(context, state, finished)}
    )
    return segments
