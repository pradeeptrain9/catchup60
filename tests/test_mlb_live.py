"""Live checks against the real StatsAPI. Marked, so the default run skips them.

    pytest -m live

These exist because the feed's shape is the one thing this project does not
control, and a field rename would otherwise surface as a broken demo.
"""

import pytest

from src import mlb, recap

FINISHED_GAME = 823570  # PHI @ NYM, 2026-09-20. Final, so it never changes.


@pytest.mark.live
class TestFeedShape:
    def test_context_carries_abbreviations_and_status(self):
        context = mlb.context(FINISHED_GAME)
        assert context.away_abbr and context.home_abbr
        assert context.abstract_state in {"Preview", "Live", "Final"}

    def test_win_probability_returns_scored_plays(self):
        plays = mlb.win_probability(FINISHED_GAME)
        assert len(plays) > 50
        assert any(p.swing > 5 for p in plays), "no play moved the game?"

    def test_every_play_has_a_description(self):
        """Narration is the description; an empty one is a silent segment."""
        plays = mlb.win_probability(FINISHED_GAME)
        assert all(p.description for p in plays)

    def test_a_real_game_produces_a_recap_inside_the_promise(self):
        manifest = recap.from_api(FINISHED_GAME)
        assert manifest["totalSeconds"] <= 60.0
        assert manifest["guardViolations"] == []
