"""The contract between the engine and the TV app.

Segment timings are absolute and contiguous, because the app animates cards
against a single audio track: a gap or an overlap here shows up on screen as a
card that changes while the voice is still mid-sentence.

`timingSource` tells the app whether the timings came from synthesized audio or
from the pre-synthesis estimate. The app is entitled to know it is being handed
a guess.
"""

from . import config
from .engine.pack import PackResult, runs_on_each_play
from .engine.rank import estimate_seconds
from .engine.state import GameContext, GameState, Play


def engine_payload(
    context: GameContext, state: GameState, plays: list[Play], all_plays: list[Play]
) -> dict:
    """Every fact the engine stands behind.

    This is also the guard's allowed-number set, so it must contain exactly the
    figures narration is permitted to use — and no more. Feeding it the whole
    game feed would let a model quote any number from any play and pass.
    """
    deltas = runs_on_each_play(all_plays)
    return {
        "game": {
            "gamePk": context.game_pk,
            "away": context.away_name,
            "home": context.home_name,
            "awayAbbr": context.away_abbr,
            "homeAbbr": context.home_abbr,
            "state": context.detailed_state,
        },
        "state": state.as_dict(),
        "plays": [
            {
                "index": p.index,
                "inning": p.inning,
                "half": p.half,
                "event": p.event,
                "description": p.description,
                "awayScore": p.away_score,
                "homeScore": p.home_score,
                "runs": deltas.get(p.index, 0),
                "wpa": p.wpa,
                "swing": round(p.swing, 1),
                "batter": p.batter,
                "pitcher": p.pitcher,
            }
            for p in plays
        ],
    }


def build(
    context: GameContext,
    state: GameState,
    segments: list[dict],
    pack_result: PackResult,
    *,
    as_of: int,
    narration_source: str,
    durations: list[float] | None = None,
    audio_url: str | None = None,
    guard_violations: list[str] | None = None,
    runs_explained: int = 0,
    runs_total: int = 0,
    speech_skipped: str | None = None,
    fallback_reason: str | None = None,
) -> dict:
    """Stamp absolute timings onto segments and assemble the manifest."""
    if durations is not None and len(durations) != len(segments):
        raise ValueError(
            f"{len(durations)} durations for {len(segments)} segments"
        )

    timing_source = "tts" if durations is not None else "estimate"
    timed: list[dict] = []
    cursor = 0.0
    last = len(segments) - 1
    for position, segment in enumerate(segments):
        if durations is not None:
            duration = durations[position]
        else:
            # Estimated timings must describe the same timeline synthesized
            # audio would, gaps included, or the two modes disagree about when
            # each card changes. Kokoro folds the gap into its own durations;
            # the estimate has to do the same, and skip it on the last segment
            # for the same reason synthesis does.
            tail = 0.0 if position == last else config.SEGMENT_GAP
            duration = estimate_seconds(segment["text"]) + tail
        entry = dict(segment)
        entry["start"] = round(cursor, 3)
        entry["dur"] = round(duration, 3)
        timed.append(entry)
        cursor += duration

    return {
        "gamePk": context.game_pk,
        "asOfPlayIndex": as_of,
        "away": context.away_abbr,
        "home": context.home_abbr,
        "awayName": context.away_name,
        "homeName": context.home_name,
        "gameStatus": context.detailed_state,
        "gameState": state.as_dict(),
        "totalSeconds": round(cursor, 2),
        "timingSource": timing_source,
        "narrationSource": narration_source,
        # Why the narrator in use is not the one that was asked for. Reporting
        # the requested narrator while serving another is how a demo starts
        # lying about itself.
        "narrationFallback": fallback_reason,
        "audioUrl": audio_url,
        "guardViolations": guard_violations or [],
        "speechSkipped": speech_skipped,
        "engine": {
            "considered": pack_result.considered,
            "selected": len(pack_result.plays),
            "coverageAdded": pack_result.coverage_added,
            "budgetSeconds": pack_result.budget_seconds,
            "limitedBy": pack_result.limited_by,
            "capReached": pack_result.cap_reached,
            # Surfaced rather than buried: when the budget forces a run out of
            # the recap, the viewer sees a score they were not shown earning.
            "runsExplained": runs_explained,
            "runsTotal": runs_total,
        },
        "segments": timed,
    }
