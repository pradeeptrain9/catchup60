"""The 60 seconds has to be true of the audio, not of the estimate.

estimate_seconds is a word count over a constant rate. It chooses the plays,
and it runs low on play descriptions — proper names and fielding sequences
read slower than ordinary prose. The first time this ran on a device the app
reported "done 9 cards in 63.94s" against a 60-second promise.

So the estimate is allowed to be wrong and the rendered audio is not: build
measures what came back and drops the least important play until it fits.
"""

import pytest

from src import config, recap


class Synth:
    """A synth whose durations are dictated, not estimated."""

    def __init__(self, *rounds):
        self.rounds = list(rounds)
        self.calls: list[int] = []

    def __call__(self, segments):
        self.calls.append(len(segments))
        durations = self.rounds.pop(0) if self.rounds else None
        if durations is None:
            # Nothing dictated: render exactly to budget.
            durations = [config.TOTAL_SECONDS / len(segments)] * len(segments)
        if len(durations) != len(segments):
            # Pad or trim so a round can be written without counting segments.
            durations = (durations + [1.0] * len(segments))[:len(segments)]
        return "/tmp/narration.mp3", durations


def build(synthetic, synth, **kwargs):
    context, plays = synthetic
    return recap.build(context, plays, synth=synth, **kwargs)


class TestMeasuredBudget:
    def test_audio_that_fits_is_left_alone(self, synthetic):
        synth = Synth([5.0] * 20)
        manifest = build(synthetic, synth)
        assert len(synth.calls) == 1
        assert manifest["engine"]["trimmedAfterSynthesis"] == 0

    def test_audio_over_budget_is_trimmed_and_re_rendered(self, synthetic):
        """The failure the device found: estimate said it fit, audio did not."""
        synth = Synth([99.0], [4.0] * 20)
        manifest = build(synthetic, synth)
        assert len(synth.calls) == 2
        assert synth.calls[1] < synth.calls[0]
        assert manifest["engine"]["trimmedAfterSynthesis"] == 1
        assert manifest["totalSeconds"] <= config.TOTAL_SECONDS

    def test_it_keeps_trimming_until_it_fits(self, synthetic):
        synth = Synth([99.0], [99.0], [3.0] * 20)
        manifest = build(synthetic, synth)
        assert manifest["engine"]["trimmedAfterSynthesis"] == 2
        assert manifest["totalSeconds"] <= config.TOTAL_SECONDS

    def test_the_weakest_play_is_the_one_dropped(self, synthetic):
        """Trimming is still a ranking decision, so it uses the same signal the
        packer did rather than dropping whatever is last."""
        context, plays = synthetic
        full = recap.build(context, plays, synth=Synth([5.0] * 20))
        trimmed = recap.build(context, plays, synth=Synth([99.0], [4.0] * 20))

        def kept(manifest):
            return {s["playIndex"] for s in manifest["segments"]
                    if s["kind"] == "play"}

        dropped = kept(full) - kept(trimmed)
        assert len(dropped) == 1
        by_index = {p.index: p for p in plays}
        gone = by_index[dropped.pop()]
        assert all(gone.swing <= by_index[i].swing for i in kept(trimmed))

    def test_the_manifest_reports_the_trim_rather_than_hiding_it(
            self, synthetic):
        """A non-zero count means the word-rate constant is drifting for this
        voice. Absorbing it silently is how it would drift unnoticed."""
        manifest = build(synthetic, Synth([99.0], [4.0] * 20))
        assert manifest["engine"]["trimmedAfterSynthesis"] == 1
        assert manifest["timingSource"] == "tts"

    def test_timings_stay_contiguous_after_a_trim(self, synthetic):
        manifest = build(synthetic, Synth([99.0], [4.0] * 20))
        cursor = 0.0
        for segment in manifest["segments"]:
            assert segment["start"] == pytest.approx(cursor, abs=0.01)
            cursor += segment["dur"]

    def test_a_shorter_budget_is_honoured_too(self, synthetic):
        manifest = build(synthetic, Synth([40.0], [2.0] * 20),
                         total_seconds=30.0)
        assert manifest["totalSeconds"] <= 30.0
