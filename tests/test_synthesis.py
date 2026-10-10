"""Synthesis wiring, without needing the 325 MB model.

The synth function is injected, so the ordering rule — narration is checked
before it is ever spoken — can be asserted with a fake that records whether it
was called at all. That is the property worth protecting; Kokoro's own output is
covered separately in tests/speech/.
"""

import pytest

from src import recap
from src.narrate import guard


class RecordingSynth:
    """Stands in for Kokoro. Returns fixed durations, remembers the call."""

    def __init__(self, per_segment: float = 5.0):
        self.per_segment = per_segment
        self.calls = 0
        self.segments = None

    def __call__(self, segments):
        self.calls += 1
        self.segments = segments
        return "/tmp/narration.wav", [self.per_segment] * len(segments)


def explode(segments):
    raise AssertionError("synthesis ran on narration that failed the guard")


class TestTimingsFromAudio:
    def test_real_durations_replace_estimates(self, synthetic):
        context, plays = synthetic
        synth = RecordingSynth(per_segment=4.0)
        manifest = recap.build(context, plays, synth=synth)
        assert manifest["timingSource"] == "tts"
        assert all(s["dur"] == 4.0 for s in manifest["segments"])

    def test_total_is_the_sum_of_real_durations(self, synthetic):
        context, plays = synthetic
        synth = RecordingSynth(per_segment=3.0)
        manifest = recap.build(context, plays, synth=synth)
        assert manifest["totalSeconds"] == pytest.approx(
            3.0 * len(manifest["segments"]))

    def test_segments_stay_contiguous_with_real_durations(self, synthetic):
        context, plays = synthetic
        manifest = recap.build(context, plays, synth=RecordingSynth(2.5))
        segments = manifest["segments"]
        for earlier, later in zip(segments, segments[1:]):
            assert later["start"] == pytest.approx(
                earlier["start"] + earlier["dur"], abs=0.01)

    def test_audio_url_is_recorded(self, synthetic):
        context, plays = synthetic
        manifest = recap.build(context, plays, synth=RecordingSynth())
        assert manifest["audioUrl"] == "/tmp/narration.wav"

    def test_every_segment_is_sent_for_synthesis(self, synthetic):
        """A missing segment would desync every card after it."""
        context, plays = synthetic
        synth = RecordingSynth()
        manifest = recap.build(context, plays, synth=synth)
        assert len(synth.segments) == len(manifest["segments"])


class TestGuardGatesSynthesis:
    def test_nothing_is_spoken_when_the_guard_fails(self, synthetic, monkeypatch):
        """The agrin rule: a wrong figure read aloud is worse than no audio."""
        context, plays = synthetic
        monkeypatch.setattr(
            guard, "check_segments", lambda segments, payload: ["invented 42"])
        manifest = recap.build(context, plays, synth=explode)
        assert manifest["guardViolations"] == ["invented 42"]
        assert manifest["speechSkipped"]
        assert manifest["audioUrl"] is None
        assert manifest["timingSource"] == "estimate"

    def test_clean_narration_is_spoken(self, synthetic):
        context, plays = synthetic
        synth = RecordingSynth()
        manifest = recap.build(context, plays, synth=synth)
        assert synth.calls == 1
        assert manifest["speechSkipped"] is None


class TestNoSynthRequested:
    def test_defaults_to_estimated_timings(self, synthetic):
        context, plays = synthetic
        manifest = recap.build(context, plays)
        assert manifest["timingSource"] == "estimate"
        assert manifest["audioUrl"] is None
