"""The replay clock. Pure arithmetic over an injected `now`, so no sleeping."""

from src.replay import Replay


class TestCursor:
    def test_starts_part_way_in(self):
        """A replay that opens at the first pitch has nothing to recap."""
        r = Replay(game_pk=1, started_at=1000.0, head_start=20)
        assert r.cursor(now=1000.0) == 20

    def test_advances_with_the_wall_clock(self):
        r = Replay(game_pk=1, started_at=1000.0, head_start=20,
                   seconds_per_at_bat=10.0)
        assert r.cursor(now=1005.0) == 20   # inside the first at-bat
        assert r.cursor(now=1010.0) == 21
        assert r.cursor(now=1100.0) == 30

    def test_holds_at_the_last_at_bat_instead_of_running_past_the_feed(self):
        """Asking for an index the game never reached is a 'no plays' error,
        which would end a demo on an error screen."""
        r = Replay(game_pk=1, started_at=1000.0, head_start=20,
                   seconds_per_at_bat=10.0, last_index=25)
        assert r.cursor(now=10000.0) == 25
        assert r.is_finished(now=10000.0) is True

    def test_is_not_finished_before_the_end(self):
        r = Replay(game_pk=1, started_at=1000.0, head_start=20,
                   seconds_per_at_bat=10.0, last_index=60)
        assert r.is_finished(now=1100.0) is False

    def test_is_never_finished_while_the_last_index_is_unknown(self):
        """Before the feed has been read once, the end is not known, and
        guessing it would truncate a game that has not ended."""
        r = Replay(game_pk=1, started_at=1000.0)
        assert r.is_finished(now=9_999_999.0) is False
