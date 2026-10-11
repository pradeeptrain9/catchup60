"""The verdict arithmetic, tested against both answers.

This file exists to be read once, on the morning after a live game, at a point
where getting it wrong means either rebuilding a product that was fine or
shipping one whose central beat does not work. So both outcomes are tested
here, now, while a mistake is cheap.
"""

import json

import pytest

from src import watch


def write(tmp_path, rows):
    path = tmp_path / "watch-1.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def live_row(at, cursor, wp_plays):
    return {"at": at, "state": "Live", "cursor": cursor, "wpPlays": wp_plays,
            "wpLastIndex": wp_plays - 1, "lag": cursor - (wp_plays - 1)}


class TestVerdict:
    def test_growing_play_counts_confirm_the_premise(self, tmp_path):
        path = write(tmp_path, [
            {"at": "t0", "state": "Preview", "cursor": None},
            live_row("t1", 10, 9),
            live_row("t2", 24, 23),
            live_row("t3", 51, 50),
            {"at": "t4", "state": "Final", "cursor": 70, "wpPlays": 71},
        ])
        result = watch.verdict(path)
        assert result["updatesMidGame"] is True
        assert result["timesItGrew"] == 2
        assert (result["wpPlaysFirst"], result["wpPlaysLast"]) == (9, 50)

    def test_a_count_frozen_all_game_refuses_to_confirm(self, tmp_path):
        """The failure this watch exists to catch: the feed advances, the
        ranking signal does not, and winProbability is a post-game artifact."""
        path = write(tmp_path, [
            live_row("t1", 10, 0),
            live_row("t2", 24, 0),
            live_row("t3", 51, 0),
        ])
        result = watch.verdict(path)
        assert result["updatesMidGame"] is False
        assert result["timesItGrew"] == 0

    def test_errors_while_live_are_surfaced_not_averaged_away(self, tmp_path):
        """A 404 on winProbability during a live game is the answer, not noise."""
        path = write(tmp_path, [
            {"at": "t1", "state": "Live", "cursor": 10,
             "error": "winProbability: GameNotFound: no data"},
            live_row("t2", 24, 23),
        ])
        result = watch.verdict(path)
        assert result["errorsWhileLive"] == [
            "winProbability: GameNotFound: no data"]

    def test_lag_is_reported_as_a_range(self, tmp_path):
        """A constant lag is a feed running a play behind. A lag that grows all
        game is a feed that is not publishing until the end, and the two look
        identical in any single tick."""
        path = write(tmp_path, [live_row("t1", 10, 10), live_row("t2", 40, 21)])
        result = watch.verdict(path)
        assert (result["lagMin"], result["lagMax"]) == (1, 20)

    def test_only_live_ticks_count(self, tmp_path):
        """Final ticks are recorded on purpose — a backfill at the whistle is
        the failure mode — so they must not be counted as mid-game growth."""
        path = write(tmp_path, [
            live_row("t1", 10, 9),
            {"at": "t2", "state": "Final", "cursor": 70, "wpPlays": 71},
            {"at": "t3", "state": "Final", "cursor": 70, "wpPlays": 71},
        ])
        result = watch.verdict(path)
        assert result["liveTicks"] == 1
        assert result["updatesMidGame"] is False

    def test_a_half_written_line_is_skipped_not_fatal(self, tmp_path):
        """The watcher is killed with ^C or a closed laptop; the last line is
        often a fragment. Losing the whole record to it would be absurd."""
        path = tmp_path / "watch-1.jsonl"
        path.write_text(json.dumps(live_row("t1", 10, 9)) + "\n"
                        + json.dumps(live_row("t2", 24, 23)) + "\n"
                        + '{"at": "t3", "state": "Li')
        assert watch.verdict(path)["updatesMidGame"] is True
