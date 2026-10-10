"""The pipeline. One function the CLI, the server and the tests all call.

Order is load-bearing: the engine selects, the narrator writes, the guard
checks, and only then would speech be synthesized. Synthesis sits downstream of
the guard so audio can never say a number the text was not allowed to.
"""

from typing import Callable

from . import cache, config, manifest, mlb
from .engine import pack as packer
from .engine.rank import estimate_seconds
from .engine.state import GameContext, Play, state_after
from .narrate import guard, script


def play_cost(play: Play) -> float:
    """What a play actually costs: the spoken sentence plus its trailing gap.

    Two undercounts were found here by measuring rendered audio against the
    estimate. Costing the raw StatsAPI description omits the inning phrase the
    narrator prepends, which turned a 60-second budget into 65. Costing speech
    alone omits the silence between segments — eight gaps of 0.28s is 2.24s,
    which is how a 57.7s estimate rendered as 59.7s of audio.

    The gap belongs to the segment because the TV app changes cards in it.
    """
    return estimate_seconds(script.play_text(play)) + config.SEGMENT_GAP


SynthFn = Callable[[list[dict]], tuple[object, list[float]]]


def build(
    context: GameContext,
    plays: list[Play],
    *,
    as_of: int | None = None,
    total_seconds: float = config.TOTAL_SECONDS,
    synth: SynthFn | None = None,
) -> dict:
    """Build a recap manifest for a game truncated at `as_of`.

    `as_of` is an atBatIndex, so a finished game replays exactly what a viewer
    would have been shown at that moment. That is what makes the demo
    rehearsable and the output testable.
    """
    last_in_feed = plays[-1].index if plays else None
    if as_of is not None:
        plays = [p for p in plays if p.index <= as_of]
    if not plays:
        raise ValueError("no plays at or before that index")

    cursor = plays[-1].index
    # Only a cursor sitting at the end of a finished game is a final score.
    finished = context.abstract_state == "Final" and cursor == last_in_feed
    state = state_after(plays)

    # Reserve the fixed segments at their real length rather than at a constant.
    # The constants drift the moment anyone rewords the intro.
    intro_cost = (
        estimate_seconds(script.intro_text(context, state)) + config.SEGMENT_GAP
    )
    # The outro is last, so it has no trailing gap to pay for.
    outro_cost = estimate_seconds(script.outro_text(context, state, finished))

    result = packer.pack(
        plays,
        total_seconds=total_seconds * (1.0 - config.BUDGET_MARGIN),
        intro_seconds=intro_cost,
        outro_seconds=outro_cost,
        cost_fn=play_cost,
    )

    segments = script.build_segments(context, state, result.plays, finished)
    payload = manifest.engine_payload(context, state, result.plays, plays)

    # The template narrator formats engine output, so it cannot fail this. It is
    # checked anyway: the guard must be exercised on every path, or it rots
    # until the day the model path needs it.
    violations = guard.check_segments(segments, payload)

    durations: list[float] | None = None
    audio_url: str | None = None
    speech_skipped: str | None = None
    if synth is not None:
        if violations:
            # Narration that failed the guard is never spoken. Falling back to
            # estimated timings keeps the manifest usable while making the
            # refusal visible, which is the behaviour agrin settled on: a wrong
            # figure read aloud is worse than a recap with no audio.
            speech_skipped = "narration failed the numeric guard"
        else:
            audio_path, durations = synth(segments)
            audio_url = str(audio_path)

    deltas = packer.runs_on_each_play(plays)
    selected = {p.index for p in result.plays}

    return manifest.build(
        context,
        state,
        segments,
        result,
        as_of=cursor,
        narration_source="template",
        guard_violations=violations,
        durations=durations,
        audio_url=audio_url,
        speech_skipped=speech_skipped,
        runs_explained=sum(deltas[i] for i in selected),
        runs_total=plays[-1].away_score + plays[-1].home_score,
    )


def from_api(game_pk: int, as_of: int | None = None,
             total_seconds: float = config.TOTAL_SECONDS,
             synth: SynthFn | None = None,
             use_cache: bool = True) -> dict:
    """Fetch and build, cheapest call first.

    The state check costs 403 bytes and runs before the 39 KB play feed,
    because winProbability 404s on a scheduled game with a message that reads
    like a bad gamePk. Asking the cheap endpoint first turns that into an
    honest "the game has not started".

    That same cheap call carries the current at-bat index, which is the cache
    key. So a poll that lands inside an at-bat already seen costs 403 bytes and
    no synthesis, instead of 39 KB and twenty seconds of CPU.
    """
    context = mlb.context(game_pk)
    if not context.has_started:
        raise mlb.GameNotStarted(
            f"{context.away_abbr} @ {context.home_abbr} is "
            f"{context.detailed_state.lower()} — no plays yet"
        )

    cursor = as_of if as_of is not None else context.cursor
    cache_key = cache.key(game_pk, cursor, total_seconds, synth is not None)
    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit

    plays = mlb.win_probability(game_pk)
    result = build(context, plays, as_of=as_of, total_seconds=total_seconds,
                   synth=synth)
    if use_cache:
        cache.put(cache_key, result)
    return result


def kokoro_synth(workdir, *, progress: bool = False) -> SynthFn:
    """A synth function bound to a working directory.

    Imported lazily so the engine path never pulls numpy, soundfile or a 325 MB
    ONNX model into a process that only wants a manifest.
    """
    def run(segments: list[dict]):
        from .speech import kokoro
        return kokoro.synthesize(segments, workdir, progress=progress)
    return run
