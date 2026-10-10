"""The manifest cache.

What matters is that the key tracks game state and nothing else. A key that
drifts turns the cache into dead weight, and a key that is too coarse serves a
stale recap over a live game — the one defect a catch-up cannot survive.
"""

import json

from src import cache


class TestKey:
    def test_is_stable_for_the_same_request(self):
        first = cache.key(1, 10, 60.0, False)
        second = cache.key(1, 10, 60.0, False)
        assert first == second

    def test_does_not_depend_on_the_clock(self):
        """agrin's lesson: a timestamp in the key means every lookup misses."""
        import time
        first = cache.key(1, 10, 60.0, False)
        time.sleep(0.01)
        assert cache.key(1, 10, 60.0, False) == first

    def test_a_new_at_bat_is_a_new_recap(self):
        assert cache.key(1, 10, 60.0, False) != cache.key(1, 11, 60.0, False)

    def test_a_different_game_is_a_different_key(self):
        assert cache.key(1, 10, 60.0, False) != cache.key(2, 10, 60.0, False)

    def test_audio_is_part_of_the_identity(self):
        """Real timings and estimated timings are different artifacts."""
        assert cache.key(1, 10, 60.0, True) != cache.key(1, 10, 60.0, False)

    def test_budget_is_part_of_the_identity(self):
        assert cache.key(1, 10, 30.0, False) != cache.key(1, 10, 60.0, False)

    def test_a_pregame_cursor_is_handled(self):
        assert cache.key(1, None, 60.0, False)


class TestRoundTrip:
    def test_stores_and_returns_a_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "DIR", tmp_path / "recaps")
        cache.put("abc", {"gamePk": 7, "totalSeconds": 58.1})
        assert cache.get("abc") == {"gamePk": 7, "totalSeconds": 58.1}

    def test_a_miss_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "DIR", tmp_path / "recaps")
        assert cache.get("nothing-here") is None

    def test_a_corrupt_entry_is_a_miss_not_an_error(self, tmp_path, monkeypatch):
        """Rebuilding is always possible; failing the request is not acceptable."""
        directory = tmp_path / "recaps"
        directory.mkdir()
        (directory / "bad.json").write_text("{ this is not json")
        monkeypatch.setattr(cache, "DIR", directory)
        assert cache.get("bad") is None

    def test_leaves_no_partial_file_behind(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cache, "DIR", tmp_path / "recaps")
        cache.put("abc", {"ok": True})
        assert list((tmp_path / "recaps").glob("*.part")) == []

    def test_an_unwritable_directory_does_not_fail_the_request(
            self, tmp_path, monkeypatch):
        blocker = tmp_path / "blocked"
        blocker.write_text("I am a file, not a directory")
        monkeypatch.setattr(cache, "DIR", blocker / "recaps")
        cache.put("abc", {"ok": True})  # must not raise
        assert cache.get("abc") is None
