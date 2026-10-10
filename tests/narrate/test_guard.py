"""The guard must actually bite.

Ported with the module from agrin. The point of these tests is that the guard
stays sharp on the template path, where it can never fire, so that it still
works on the day the Bedrock path needs it.
"""

from src.narrate import guard

PAYLOAD = {
    "state": {"inning": 8, "away": 7, "home": 2},
    "plays": [
        {"inning": 6, "runs": 1,
         "description": "Bo Bichette homers (17) on a fly ball."},
    ],
}


class TestExtraction:
    def test_reads_thousands_separators_as_one_number(self):
        assert guard.numbers_in_text("a crowd of 41,922") == [41922.0]

    def test_reads_decimals(self):
        assert guard.numbers_in_text("moved it 11.1 percent") == [11.1]

    def test_ignores_text_without_numbers(self):
        assert guard.numbers_in_text("a long fly ball") == []


class TestAllowedCollection:
    def test_numbers_inside_payload_strings_count(self):
        """StatsAPI descriptions legitimately carry figures: "homers (17)"."""
        allowed = guard.collect_allowed_numbers(PAYLOAD)
        assert 17.0 in allowed

    def test_booleans_are_not_quantities(self):
        allowed = guard.collect_allowed_numbers({"isScoringPlay": True})
        assert 1.0 not in allowed


class TestCheckSegments:
    def test_passes_narration_built_from_the_payload(self):
        segments = [
            {"kind": "intro", "text": "Top of the 8th. Away 7, home 2."},
            {"kind": "play", "text": "Bo Bichette homers (17) in the 6th."},
        ]
        assert guard.check_segments(segments, PAYLOAD) == []

    def test_catches_an_invented_inning(self):
        segments = [{"kind": "play", "text": "Bichette homered in the 4th."}]
        violations = guard.check_segments(segments, PAYLOAD)
        assert len(violations) == 1
        assert "4" in violations[0]

    def test_catches_an_invented_season_total(self):
        segments = [{"kind": "play", "text": "Bichette homers (23)."}]
        assert guard.check_segments(segments, PAYLOAD)

    def test_names_the_offending_segment(self):
        segments = [
            {"kind": "intro", "text": "Top of the 8th."},
            {"kind": "play", "text": "A 3-run shot in the 5th."},
        ]
        violations = guard.check_segments(segments, PAYLOAD)
        assert violations[0].startswith("segment[1](play)")

    def test_allows_a_rounded_figure(self):
        """45.4 spoken as 45 is a rewording, not an invention."""
        payload = {"swing": 45.4}
        assert guard.check_segments(
            [{"kind": "play", "text": "about 45 percent"}], payload) == []
