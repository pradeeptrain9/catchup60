"""Fit the ranked plays into the 60-second promise.

Two rules fight here. Taking the biggest swings is what makes the recap useful;
taking only the biggest swings produces six plays from one chaotic inning and a
viewer who still does not know how the game got there. So the packer selects by
swing under a per-half-inning cap, and relaxes the cap only while budget is left
over.

The selected plays are then returned in chronological order. A recap ordered by
importance is a highlight reel; a recap ordered by time is a catch-up, which is
what the viewer actually asked for.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Callable

from .rank import MIN_SWING, estimate_seconds, rank
from .state import Play

# Cap relaxation ladder. One play per half-inning first, so the spread is wide
# before it is deep; None means uncapped, used only if budget still remains.
CAP_LADDER: tuple[int | None, ...] = (1, 2, 3, None)

# Stop relaxing once this much of the budget is committed. Without it, the last
# pass crams marginal plays into the final two seconds.
SATISFIED_AT = 0.9

# Ceiling on plays, independent of budget. Eleven plays technically fit inside
# 51 seconds, at 4.6 seconds each, and the result is a breathless list nobody
# can follow. Seven leaves each moment about seven seconds, which is one card
# the eye can actually land on. Budget is not the only constraint on pacing.
MAX_PLAYS = 7


@dataclass
class PackResult:
    plays: list[Play]  # chronological
    seconds_estimated: float  # plays only, excludes intro and outro
    budget_seconds: float  # what the plays were allowed to use
    total_seconds: float  # budget_seconds plus the fixed segments
    considered: int  # plays that cleared MIN_SWING
    coverage_added: int  # pulled in below the floor to explain runs
    cap_reached: int | None  # the ladder rung that was actually needed
    limited_by: str  # "budget" | "count" | "supply"

    @property
    def is_short(self) -> bool:
        """A quiet game yields a short recap. That is correct, not a bug."""
        return self.seconds_estimated < self.budget_seconds * SATISFIED_AT


def default_cost(play: Play) -> float:
    return estimate_seconds(play.description)


def pack(
    plays: list[Play],
    total_seconds: float = 60.0,
    intro_seconds: float = 5.0,
    outro_seconds: float = 4.0,
    min_swing: float = MIN_SWING,
    max_plays: int = MAX_PLAYS,
    cost_fn: Callable[[Play], float] = default_cost,
) -> PackResult:
    """Select plays that fit, keeping innings spread.

    `cost_fn` is injected so the packer never imports the narrator: the real
    cost of a play is the length of the sentence that will be spoken about it,
    and that belongs to narrate/, not here.
    """
    budget = max(0.0, total_seconds - intro_seconds - outro_seconds)
    ranked = rank(plays, min_swing=min_swing)

    chosen: list[Play] = []
    chosen_indexes: set[int] = set()
    per_half: Counter[tuple[int, str]] = Counter()
    used = 0.0
    cap_reached: int | None = None

    for cap in CAP_LADDER:
        if used >= budget * SATISFIED_AT or len(chosen) >= max_plays:
            break
        cap_reached = cap
        for play in ranked:
            if len(chosen) >= max_plays:
                break
            if play.index in chosen_indexes:
                continue
            if cap is not None and per_half[play.half_key] >= cap:
                continue
            cost = cost_fn(play)
            if cost <= 0 or used + cost > budget:
                continue
            chosen.append(play)
            chosen_indexes.add(play.index)
            per_half[play.half_key] += 1
            used += cost

    chosen, used, coverage_added = _ensure_scoring_coverage(
        chosen, plays, budget, used, max_plays, cost_fn
    )
    chosen, used = _enforce_budget(chosen, plays, budget, used, cost_fn)

    if len(chosen) >= max_plays:
        limited_by = "count"
    elif used >= budget * SATISFIED_AT:
        limited_by = "budget"
    else:
        limited_by = "supply"

    chosen.sort(key=lambda p: p.index)
    return PackResult(
        plays=chosen,
        seconds_estimated=round(used, 2),
        budget_seconds=round(budget, 2),
        total_seconds=total_seconds,
        considered=len(ranked),
        coverage_added=coverage_added,
        cap_reached=cap_reached,
        limited_by=limited_by,
    )


def runs_on_each_play(plays: list[Play]) -> dict[int, int]:
    """Runs that scored on each play, from the cumulative score.

    Derived from the score rather than from `rbi`, because runs arrive without
    an RBI often enough to matter: errors, wild pitches, passed balls, balks.
    An rbi-based account silently loses those runs.
    """
    deltas: dict[int, int] = {}
    previous = 0
    for play in plays:
        total = play.away_score + play.home_score
        deltas[play.index] = max(0, total - previous)
        previous = total
    return deltas


def _ensure_scoring_coverage(
    chosen: list[Play],
    plays: list[Play],
    budget: float,
    used: float,
    max_plays: int,
    cost_fn: Callable[[Play], float],
) -> tuple[list[Play], float, int]:
    """Make every run in the recap traceable to a play the viewer is shown.

    Swing ranking alone produces recaps where the score goes 2-0 to 4-0 across a
    strikeout, because the strikeout moved win probability more than either run
    did. The viewer is left to infer two runs from nothing.

    So runs are accounted for one at a time, per half-inning: a half-inning that
    scored three runs is not satisfied by one selected RBI single. Missing runs
    pull in their own scoring plays, displacing the weakest selection that
    explains no runs when there is no room left. A play that explains a run is
    never dropped to describe a different run.
    """
    deltas = runs_on_each_play(plays)
    chosen_indexes = {p.index for p in chosen}
    added = 0

    scored_halves: dict[tuple[int, str], list[Play]] = {}
    for play in plays:
        if deltas.get(play.index, 0) > 0:
            scored_halves.setdefault(play.half_key, []).append(play)

    for half_key in sorted(scored_halves):
        in_half = scored_halves[half_key]
        runs_total = sum(deltas[p.index] for p in in_half)

        while True:
            explained = sum(
                deltas.get(p.index, 0) for p in chosen if p.half_key == half_key
            )
            if explained >= runs_total:
                break

            candidates = [p for p in in_half if p.index not in chosen_indexes]
            if not candidates:
                break
            # Biggest run-producer first, so one selection can settle a
            # three-run double before we spend a slot on a solo single.
            candidate = max(
                candidates, key=lambda p: (deltas[p.index], p.swing, p.index)
            )
            cost = cost_fn(candidate)
            if cost <= 0:
                break

            if used + cost <= budget and len(chosen) < max_plays:
                chosen.append(candidate)
                chosen_indexes.add(candidate.index)
                used += cost
                added += 1
                continue

            droppable = [p for p in chosen if deltas.get(p.index, 0) == 0]
            if not droppable:
                break
            weakest = min(droppable, key=lambda p: (p.swing, -p.index))
            chosen.remove(weakest)
            chosen_indexes.discard(weakest.index)
            used -= cost_fn(weakest)
            chosen.append(candidate)
            chosen_indexes.add(candidate.index)
            used += cost
            added += 1

    return chosen, used, added


def _enforce_budget(
    chosen: list[Play],
    plays: list[Play],
    budget: float,
    used: float,
    cost_fn: Callable[[Play], float],
) -> tuple[list[Play], float]:
    """Hard-trim back inside the budget.

    The coverage pass displaces a cheap non-scoring play with a more expensive
    scoring one, and the replacement can cost more than what it replaced. Left
    alone that pushes a 60-second promise to 65 seconds, which the TV app has no
    way to absorb.

    Runs are protected as far as possible: non-scoring plays go first, weakest
    swing first. Only if nothing else can go does a scoring play get dropped,
    and then it is the one explaining the fewest runs.
    """
    deltas = runs_on_each_play(plays)

    while used > budget and chosen:
        droppable = [p for p in chosen if deltas.get(p.index, 0) == 0]
        if droppable:
            victim = min(droppable, key=lambda p: (p.swing, -p.index))
        else:
            victim = min(
                chosen, key=lambda p: (deltas.get(p.index, 0), p.swing, -p.index)
            )
        chosen.remove(victim)
        used -= cost_fn(victim)

    return chosen, used
