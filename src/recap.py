"""The pipeline. One function the CLI, the server and the tests all call.

Order is load-bearing: the engine selects, the narrator writes, the guard
checks, and only then would speech be synthesized. Synthesis sits downstream of
the guard so audio can never say a number the text was not allowed to.
"""

from dataclasses import replace
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
# Returns (segments, fallback_reason). A reason means the rewrite was not used.
RephraseFn = Callable[[list[dict], dict], tuple[list[dict], "str | None"]]


def build(
    context: GameContext,
    plays: list[Play],
    *,
    as_of: int | None = None,
    total_seconds: float = config.TOTAL_SECONDS,
    synth: SynthFn | None = None,
    rephrase: RephraseFn | None = None,
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

    # A model may reword what the engine wrote. It never decides what the engine
    # decided, and the manifest reports which narrator actually produced the
    # text rather than which one was asked for.
    narration_source = "template"
    fallback_reason: str | None = None
    if rephrase is not None:
        candidate, fallback_reason = rephrase(segments, payload)
        if fallback_reason is None:
            segments = candidate
            narration_source = "bedrock"

    # The template narrator formats engine output, so it cannot fail this. It is
    # checked anyway: the guard must be exercised on every path, or it rots
    # until the day the model path needs it.
    violations = guard.check_segments(segments, payload)

    durations: list[float] | None = None
    audio_url: str | None = None
    speech_skipped: str | None = None
    trimmed = 0
    if synth is not None:
        if violations:
            # Narration that failed the guard is never spoken. Falling back to
            # estimated timings keeps the manifest usable while making the
            # refusal visible, which is the behaviour agrin settled on: a wrong
            # figure read aloud is worse than a recap with no audio.
            speech_skipped = "narration failed the numeric guard"
        else:
            # The budget is enforced against measured audio, not against the
            # estimate that chose the plays. estimate_seconds is a word count
            # over a constant rate and it runs systematically low on play
            # descriptions — proper names and fielding sequences read slower
            # than the average sentence. On the first device run that put a
            # 63.9s recap behind a 60-second promise. Measuring and then
            # trimming costs a re-synthesis in the rare case; promising sixty
            # seconds and delivering sixty-four costs the product's one claim.
            while True:
                audio_path, durations = synth(segments)
                if (sum(durations) <= total_seconds
                        or len(result.plays) <= 1):
                    break
                weakest = min(range(len(result.plays)),
                              key=lambda i: result.plays[i].swing)
                kept = [p for i, p in enumerate(result.plays) if i != weakest]
                result = replace(result, plays=kept)
                trimmed += 1
                segments = script.build_segments(context, state, kept, finished)
                payload = manifest.engine_payload(context, state, kept, plays)
                violations = guard.check_segments(segments, payload)
                if violations:
                    # The template narrator cannot fail this, so reaching here
                    # means the model's text is being re-checked against a
                    # smaller payload and no longer clears it. Silence beats a
                    # figure the engine no longer supports.
                    speech_skipped = "narration failed the numeric guard"
                    durations = None
                    break
            audio_url = str(audio_path) if durations is not None else None

    deltas = packer.runs_on_each_play(plays)
    selected = {p.index for p in result.plays}

    return manifest.build(
        context,
        state,
        segments,
        result,
        as_of=cursor,
        narration_source=narration_source,
        fallback_reason=fallback_reason,
        guard_violations=violations,
        durations=durations,
        audio_url=audio_url,
        speech_skipped=speech_skipped,
        runs_explained=sum(deltas[i] for i in selected),
        runs_total=plays[-1].away_score + plays[-1].home_score,
        trimmed_after_synthesis=trimmed,
    )


def cacheable(manifest: dict) -> bool:
    """Whether a manifest is worth keeping.

    A narration fallback is a statement about the environment, not about the
    game: the model was unreachable, unentitled or misconfigured. Storing it
    under the key that means "the model was asked" makes the outage outlive
    its own fix — a manifest cached while Bedrock was misconfigured kept being
    served for a week afterwards, still carrying the obsolete reason, long
    after the model itself was answering.

    The cost of this is that a persistently broken model re-synthesizes on
    every request instead of once. That is the right way round: a fallback is
    a thing to notice and fix, and paying for it is how it stays noticed.
    A guard rejection is not included here, because that is a property of the
    text and the payload and will repeat identically.
    """
    return not manifest.get("narrationFallback")


def from_api(game_pk: int, as_of: int | None = None,
             total_seconds: float = config.TOTAL_SECONDS,
             synth: SynthFn | None = None,
             rephrase: RephraseFn | None = None,
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
    cache_key = cache.key(game_pk, cursor, total_seconds, synth is not None,
                          rephrase is not None)
    if use_cache:
        hit = cache.get(cache_key)
        if hit is not None:
            return hit

    plays = mlb.win_probability(game_pk)
    result = build(context, plays, as_of=as_of, total_seconds=total_seconds,
                   synth=synth, rephrase=rephrase)
    if use_cache and cacheable(result):
        cache.put(cache_key, result)
    return result


def polly_synth(workdir, *, progress: bool = False) -> SynthFn:
    """Speech through Amazon Polly. Emits mp3 directly, so no encode step."""
    def run(segments: list[dict]):
        from .speech import polly
        return polly.synthesize(segments, workdir, progress=progress)
    return run


def polly_ssml_synth(workdir) -> SynthFn:
    """One Polly call, timed by speech marks. The path that runs in Lambda.

    No progress argument: there is nothing to report per segment when the whole
    recap is a single request.
    """
    def run(segments: list[dict]):
        from .speech import polly_ssml
        return polly_ssml.synthesize(segments, workdir)
    return run


def bedrock_rephrase() -> RephraseFn:
    def run(segments: list[dict], payload: dict):
        from .narrate import bedrock
        return bedrock.rephrase(segments, payload)
    return run


def kokoro_synth(workdir, *, progress: bool = False,
                 encode: bool = True) -> SynthFn:
    """A synth function bound to a working directory.

    Imported lazily so the engine path never pulls numpy, soundfile or a 325 MB
    ONNX model into a process that only wants a manifest.

    Encodes to mp3 by default because Vega's AudioPlayer silently refuses wav —
    see speech/encode.py. The wav stays on disk as the timing source.
    """
    def run(segments: list[dict]):
        from .speech import kokoro
        wav, durations = kokoro.synthesize(segments, workdir, progress=progress)
        if not encode:
            return wav, durations
        from .speech.encode import to_mp3
        return to_mp3(wav), durations
    return run
