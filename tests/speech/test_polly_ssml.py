"""The deployed speech path, tested without spending anything at Polly.

Only two things here can be wrong in a way the eye would not catch: the SSML
the segments turn into, and the arithmetic that turns marks back into
durations. Both are pure, so both are tested directly; the two API calls
around them are not interesting enough to mock.
"""

import pytest

from src.speech import polly_ssml

SEGMENTS = [
    {"kind": "intro", "text": "Top of the 6th. Guardians 7, White Sox 4."},
    {"kind": "play", "text": "Ramirez doubles & scores."},
    {"kind": "outro", "text": "Back to live."},
]


class TestSsml:
    def test_marks_every_segment_and_closes_with_end(self):
        ssml = polly_ssml.build_ssml(SEGMENTS, 0.28)
        for name in ("s0", "s1", "s2", "end"):
            assert f'<mark name="{name}"/>' in ssml
        assert ssml.endswith('<mark name="end"/></speak>')

    def test_gaps_sit_between_segments_and_never_after_the_last(self):
        ssml = polly_ssml.build_ssml(SEGMENTS, 0.28)
        assert ssml.count('<break time="280ms"/>') == len(SEGMENTS) - 1
        assert '<break' not in ssml.split('<mark name="s2"/>')[1]

    def test_escapes_text_that_would_otherwise_break_the_document(self):
        """An ampersand in a play description is not exotic — Polly rejects the
        whole request on one, and the recap would lose its audio."""
        ssml = polly_ssml.build_ssml(SEGMENTS, 0.28)
        assert "doubles &amp; scores" in ssml

    def test_refuses_an_empty_segment_rather_than_shipping_a_silent_card(self):
        with pytest.raises(ValueError, match="segment 1"):
            polly_ssml.build_ssml(
                [SEGMENTS[0], {"kind": "play", "text": "  "}], 0.28)

    def test_refuses_to_exceed_pollys_character_ceiling(self, monkeypatch):
        monkeypatch.setattr(polly_ssml, "MAX_SSML_CHARS", 40)
        with pytest.raises(ValueError, match="over Polly's 40"):
            polly_ssml.build_ssml(SEGMENTS, 0.28)


class TestDurations:
    # The shape Polly actually returned for a three-segment recap.
    MARKS = [{"value": "s0", "time": 25}, {"value": "s1", "time": 3709},
             {"value": "s2", "time": 6607}, {"value": "end", "time": 7762}]

    def test_the_lead_in_silence_lands_in_the_first_segment(self):
        """Polly starts speaking a few ms in. Anchoring segment 0 at zero keeps
        every later start equal to its own mark, instead of running the whole
        timeline early by the width of that silence."""
        durations = polly_ssml.durations_from_marks(self.MARKS, 3)
        assert durations[0] == pytest.approx(3.709)
        starts = [sum(durations[:i]) for i in range(3)]
        assert starts == pytest.approx([0.0, 3.709, 6.607])

    def test_the_total_is_the_end_mark(self):
        durations = polly_ssml.durations_from_marks(self.MARKS, 3)
        assert sum(durations) == pytest.approx(7.762)

    def test_a_missing_mark_is_named_not_silently_dropped(self):
        """Short-counting the marks would shift every card after the gap."""
        marks = [m for m in self.MARKS if m["value"] != "s1"]
        with pytest.raises(ValueError, match="no mark for s1"):
            polly_ssml.durations_from_marks(marks, 3)

    def test_a_missing_end_mark_is_caught(self):
        marks = [m for m in self.MARKS if m["value"] != "end"]
        with pytest.raises(ValueError, match="no mark for end"):
            polly_ssml.durations_from_marks(marks, 3)

    def test_non_increasing_marks_are_rejected(self):
        marks = [{"value": "s0", "time": 25}, {"value": "s1", "time": 3709},
                 {"value": "s2", "time": 6607}, {"value": "end", "time": 6000}]
        with pytest.raises(ValueError, match="not increasing"):
            polly_ssml.durations_from_marks(marks, 3)
