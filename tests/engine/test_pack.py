"""The packer's invariants.

The 60-second budget is a promise the TV app cannot absorb a breach of, and an
unexplained score jump is the defect that made the coverage pass necessary. Both
are asserted here rather than eyeballed.
"""

from src import recap
from src.engine import pack as packer
from src.engine.rank import estimate_seconds


def costs(result, cost_fn) -> float:
    return sum(cost_fn(p) for p in result.plays)


class TestBudget:
    def test_never_exceeds_the_play_budget(self, synthetic):
        _, plays = synthetic
        result = packer.pack(plays, cost_fn=recap.play_cost)
        assert costs(result, recap.play_cost) <= result.budget_seconds + 1e-6

    def test_holds_under_a_tight_budget(self, synthetic):
        _, plays = synthetic
        result = packer.pack(plays, total_seconds=20.0, cost_fn=recap.play_cost)
        assert costs(result, recap.play_cost) <= result.budget_seconds + 1e-6

    def test_a_quiet_game_yields_a_short_recap(self, synthetic):
        """Padding to fill the budget is worse than coming in under it."""
        _, plays = synthetic
        result = packer.pack(plays, min_swing=15.0, max_plays=2,
                             cost_fn=recap.play_cost)
        assert result.seconds_estimated < result.budget_seconds


class TestOrdering:
    def test_output_is_chronological(self, synthetic):
        """Importance order is a highlight reel; a catch-up is a timeline."""
        _, plays = synthetic
        result = packer.pack(plays, cost_fn=recap.play_cost)
        indexes = [p.index for p in result.plays]
        assert indexes == sorted(indexes)

    def test_respects_the_play_ceiling(self, synthetic):
        _, plays = synthetic
        result = packer.pack(plays, max_plays=3, cost_fn=recap.play_cost)
        assert len(result.plays) <= 3


class TestScoringCoverage:
    def test_every_run_is_explained_when_budget_allows(self, synthetic):
        _, plays = synthetic
        result = packer.pack(plays, total_seconds=120.0, max_plays=20,
                             cost_fn=recap.play_cost)
        deltas = packer.runs_on_each_play(plays)
        explained = sum(deltas[p.index] for p in result.plays)
        assert explained == plays[-1].away_score + plays[-1].home_score

    def test_prefers_a_scoring_play_over_a_bigger_swing_strikeout(self, synthetic):
        """The regression that forced this pass: 2-0 to 4-0 across a strikeout."""
        _, plays = synthetic
        result = packer.pack(plays, cost_fn=recap.play_cost)
        deltas = packer.runs_on_each_play(plays)
        scoring = [p for p in result.plays if deltas[p.index] > 0]
        assert len(scoring) >= len(result.plays) - 1

    def test_coverage_overrides_the_swing_floor_and_says_so(self, synthetic):
        """A sacrifice fly can score a run while moving the game very little.

        The run still has to be explained, so coverage admits plays the floor
        rejected — and reports how many, so `selected` exceeding `considered` is
        documented behaviour rather than a bug someone has to re-derive.
        """
        _, plays = synthetic
        result = packer.pack(plays, min_swing=15.0, cost_fn=recap.play_cost)
        assert result.considered == 2
        assert result.coverage_added > 0
        assert len(result.plays) == result.considered + result.coverage_added

    def test_run_accounting_uses_the_score_not_rbi(self, synthetic):
        """Runs arrive without an RBI often enough to matter: errors, balks."""
        _, plays = synthetic
        deltas = packer.runs_on_each_play(plays)
        assert sum(deltas.values()) == plays[-1].away_score + plays[-1].home_score
