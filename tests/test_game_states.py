"""Behaviour across the states a game actually passes through.

StatsAPI is unhelpful at both ends: a scheduled game 404s on the play feed with
a message that reads like a bad id, and a nonexistent gamePk answers 200 with a
fully populated placeholder. Both were real defects, so both are pinned here.
"""

import pytest

from src import mlb, recap
from src.engine.state import GameContext
from src.narrate import script


def context(**overrides) -> GameContext:
    base = dict(
        game_pk=1, away_abbr="PHI", home_abbr="NYM", away_name="Phillies",
        home_name="Mets", detailed_state="In Progress",
        abstract_state="Live", cursor=40,
    )
    base.update(overrides)
    return GameContext(**base)


class TestHasStarted:
    def test_a_scheduled_game_has_not_started(self):
        assert not context(abstract_state="Preview",
                           detailed_state="Scheduled").has_started

    def test_a_live_game_has_started(self):
        assert context(abstract_state="Live").has_started

    def test_a_finished_game_has_started(self):
        """A recap of a finished game is still a recap."""
        assert context(abstract_state="Final").has_started


class TestOutroFollowsTheCursor:
    def test_a_finished_game_at_the_end_says_final(self, synthetic):
        _, plays = synthetic
        manifest = recap.build(context(abstract_state="Final"), plays)
        assert "final" in manifest["segments"][-1]["text"].lower()

    def test_a_finished_game_replayed_mid_game_says_back_to_live(self, synthetic):
        """The bug this pins: "that's your final" over a 4-0 score in the 5th.

        A replay at --as-of stands in for a moment when the game was live, so
        the outro has to follow the cursor and not the game's real status.
        """
        _, plays = synthetic
        manifest = recap.build(context(abstract_state="Final"), plays, as_of=10)
        assert "back to live" in manifest["segments"][-1]["text"].lower()

    def test_a_live_game_says_back_to_live(self, synthetic):
        _, plays = synthetic
        manifest = recap.build(context(abstract_state="Live"), plays)
        assert "back to live" in manifest["segments"][-1]["text"].lower()

    def test_the_score_is_stated_either_way(self, synthetic):
        _, plays = synthetic
        for state in ("Live", "Final"):
            manifest = recap.build(context(abstract_state=state), plays)
            text = manifest["segments"][-1]["text"]
            assert str(manifest["gameState"]["away"]) in text
            assert str(manifest["gameState"]["home"]) in text


class TestPregameIsRefusedClearly:
    def test_raises_game_not_started_before_the_first_pitch(self, monkeypatch):
        """And without touching the play feed, which would 404 misleadingly."""
        monkeypatch.setattr(
            mlb, "context",
            lambda game_pk: context(abstract_state="Preview",
                                    detailed_state="Scheduled", cursor=None))

        def explode(game_pk):
            raise AssertionError("fetched plays for a game with none")

        monkeypatch.setattr(mlb, "win_probability", explode)
        with pytest.raises(mlb.GameNotStarted) as caught:
            recap.from_api(1)
        assert "scheduled" in str(caught.value).lower()


class TestOutroWordingDirectly:
    def test_finished_wording(self):
        from src.engine.state import GameState
        state = GameState(inning=9, half="bottom", away_score=7,
                          home_score=2, outs=3)
        assert script.outro_text(context(), state, finished=True).startswith(
            "That's your final")

    def test_live_wording(self):
        from src.engine.state import GameState
        state = GameState(inning=7, half="top", away_score=4,
                          home_score=2, outs=1)
        assert "Back to live" in script.outro_text(context(), state,
                                                   finished=False)
