"""What the app is offered, and in what order.

The ordering is a product decision, not an implementation detail: a live game
is the point of the app, a finished one still deserves a recap, and a scheduled
one is shown only so the viewer knows it is coming.
"""

from src import catalog, mlb


def game(pk: int, abstract: str, state: str = "x") -> dict:
    return {"gamePk": pk, "away": "A", "home": "B", "state": state,
            "abstract": abstract, "series": None}


class TestOrdering:
    def test_live_games_come_first(self):
        feed = lambda date=None: [game(1, "Final"), game(2, "Live")]
        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert result[0]["id"] == "2"

    def test_finished_games_outrank_scheduled(self):
        feed = lambda date=None: [game(1, "Preview"), game(2, "Final")]
        ids = [g["id"] for g in catalog.playable(today="2026-10-11", fetch=feed)]
        assert ids.index("2") < ids.index("1")

    def test_the_fixture_is_always_last_and_always_present(self):
        feed = lambda date=None: [game(1, "Live")]
        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert result[-1]["id"] == "synthetic"


class TestPlayability:
    def test_a_scheduled_game_is_not_playable(self):
        """It has no plays, so there is nothing to recap."""
        feed = lambda date=None: [game(1, "Preview", "Scheduled")]
        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert result[0]["playable"] is False

    def test_live_and_final_are_playable(self):
        feed = lambda date=None: [game(1, "Live"), game(2, "Final")]
        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert all(g["playable"] for g in result[:2])


class TestOffDay:
    def test_falls_back_to_an_earlier_day_when_nothing_is_recappable(self):
        """A postseason off-day should not produce an empty screen."""
        def feed(date=None):
            if date == "2026-10-11":
                return [game(1, "Preview")]
            return [game(9, "Final")]

        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert [g["id"] for g in result if g["id"] == "9"] == ["9"]

    def test_keeps_walking_back_past_consecutive_empty_days(self):
        """One day back is not enough: a travel day can follow an off-day."""
        def feed(date=None):
            if date == "2026-10-09":
                return [game(7, "Final")]
            return []

        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert [g["id"] for g in result][0] == "7"

    def test_gives_up_after_the_lookback_window(self):
        calls = []

        def feed(date=None):
            calls.append(date)
            return []

        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert result == [catalog.FIXTURE]
        assert len(calls) == catalog.LOOKBACK_DAYS + 1

    def test_does_not_reach_for_yesterday_when_today_has_a_final(self):
        calls = []

        def feed(date=None):
            calls.append(date)
            return [game(1, "Final")]

        catalog.playable(today="2026-10-11", fetch=feed)
        assert calls == ["2026-10-11"]


class TestFailure:
    def test_a_schedule_outage_still_leaves_something_playable(self):
        def feed(date=None):
            raise mlb.FeedError("statsapi down")

        result = catalog.playable(today="2026-10-11", fetch=feed)
        assert result == [catalog.FIXTURE]
