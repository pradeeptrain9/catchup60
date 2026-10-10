"""Ranking must stay arithmetic on the win-probability delta.

If this file starts needing judgement calls about baseball, the model has crept
into the part of the pipeline it is not allowed into.
"""

from src.engine.rank import MIN_SWING, estimate_seconds, rank
from src.engine.state import Play


def play(index: int, wpa: float, captivating: int = 0, inning: int = 1) -> Play:
    return Play(
        index=index, inning=inning, half="top", event="Single",
        description="A batter singles.", away_score=0, home_score=0, rbi=0,
        outs=0, batter="B", pitcher="P", wpa=wpa, home_wp=50.0,
        is_scoring=False, captivating=captivating,
    )


class TestRank:
    def test_orders_by_absolute_swing(self):
        plays = [play(0, 3.0), play(1, -9.0), play(2, 5.0)]
        assert [p.index for p in rank(plays)] == [1, 2, 0]

    def test_sign_is_irrelevant(self):
        """A play that wrecks the home team matters as much as one that saves it."""
        assert rank([play(0, -8.0)])[0].swing == 8.0

    def test_drops_plays_below_the_floor(self):
        plays = [play(0, MIN_SWING - 0.1), play(1, MIN_SWING)]
        assert [p.index for p in rank(plays)] == [1]

    def test_ties_break_on_captivating_then_recency(self):
        plays = [play(0, 5.0, captivating=1), play(1, 5.0, captivating=9),
                 play(2, 5.0, captivating=9)]
        assert [p.index for p in rank(plays)] == [2, 1, 0]


class TestEstimate:
    def test_empty_text_costs_nothing(self):
        assert estimate_seconds("") == 0.0

    def test_longer_text_costs_more(self):
        assert estimate_seconds("a b c d e f") > estimate_seconds("a b c")
