"""The pipeline. One function the CLI, the server and the tests all call.

Order is load-bearing: the engine selects, the narrator writes, the guard
checks, and only then would speech be synthesized. Synthesis sits downstream of
the guard so audio can never say a number the text was not allowed to.
"""

from . import config, manifest, mlb
from .engine import pack as packer
from .engine.rank import estimate_seconds
from .engine.state import GameContext, Play, state_after
from .narrate import guard, script


def play_cost(play: Play) -> float:
    """What a play actually costs: the sentence that will be spoken about it.

    Costing the raw StatsAPI description instead undercounts by the inning
    phrase the narrator prepends, which is how a 60-second budget quietly
    becomes 65 seconds.
    """
    return estimate_seconds(script.play_text(play))


def build(
    context: GameContext,
    plays: list[Play],
    *,
    as_of: int | None = None,
    total_seconds: float = config.TOTAL_SECONDS,
) -> dict:
    """Build a recap manifest for a game truncated at `as_of`.

    `as_of` is an atBatIndex, so a finished game replays exactly what a viewer
    would have been shown at that moment. That is what makes the demo
    rehearsable and the output testable.
    """
    if as_of is not None:
        plays = [p for p in plays if p.index <= as_of]
    if not plays:
        raise ValueError("no plays at or before that index")

    cursor = plays[-1].index
    state = state_after(plays)

    # Reserve the fixed segments at their real length rather than at a constant.
    # The constants drift the moment anyone rewords the intro.
    intro_cost = estimate_seconds(script.intro_text(context, state))
    outro_cost = estimate_seconds(script.outro_text(context, state))

    result = packer.pack(
        plays,
        total_seconds=total_seconds,
        intro_seconds=intro_cost,
        outro_seconds=outro_cost,
        cost_fn=play_cost,
    )

    segments = script.build_segments(context, state, result.plays)
    payload = manifest.engine_payload(context, state, result.plays, plays)

    # The template narrator formats engine output, so it cannot fail this. It is
    # checked anyway: the guard must be exercised on every path, or it rots
    # until the day the model path needs it.
    violations = guard.check_segments(segments, payload)

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
        runs_explained=sum(deltas[i] for i in selected),
        runs_total=plays[-1].away_score + plays[-1].home_score,
    )


def from_api(game_pk: int, as_of: int | None = None,
             total_seconds: float = config.TOTAL_SECONDS) -> dict:
    context = mlb.context(game_pk)
    plays = mlb.win_probability(game_pk)
    return build(context, plays, as_of=as_of, total_seconds=total_seconds)
