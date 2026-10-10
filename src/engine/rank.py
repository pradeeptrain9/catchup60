"""Which plays mattered.

This is the one question a language model is never asked. StatsAPI publishes a
per-play win-probability delta; importance is arithmetic on that field. A model
that decides what mattered will confidently tell a viewer the game turned on a
groundout, and there is no way to catch it after the fact.
"""

from .state import Play

# Plays below this swing are noise. A recap padded with 0.4% at-bats is worse
# than a short recap, so the packer is allowed to come in under budget.
MIN_SWING = 2.0


def rank(plays: list[Play], min_swing: float = MIN_SWING) -> list[Play]:
    """Most game-changing first.

    Ties break on StatsAPI's own captivatingIndex, then on recency: when two
    plays moved the game equally, the later one is the one the viewer is closer
    to and more likely to hear referenced on the broadcast.
    """
    eligible = [p for p in plays if p.swing >= min_swing]
    return sorted(
        eligible,
        key=lambda p: (p.swing, p.captivating, p.index),
        reverse=True,
    )


def estimate_seconds(text: str, words_per_second: float = 2.6) -> float:
    """Spoken length before synthesis.

    Only used to decide what fits; the manifest's timings come from the TTS
    engine's real per-segment durations. Lifted from shorts-factory, where this
    rate held up across hundreds of Kokoro renders.
    """
    words = len((text or "").split())
    if not words:
        return 0.0
    return words / words_per_second
