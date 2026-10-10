"""Kokoro itself. Needs the model, so these are marked and skipped by default.

    pytest -m tts

Kept small on purpose: synthesis is slow (about 3x realtime), and what matters
here is the contract the manifest depends on, not Kokoro's audio quality.
"""

import wave

import pytest

from src import config
from src.speech import kokoro

pytestmark = pytest.mark.tts

SEGMENTS = [
    {"kind": "intro", "text": "Bottom of the 7th. Phillies 4, Mets 2."},
    {"kind": "play", "text": "Bo Bichette homers on a fly ball."},
    {"kind": "outro", "text": "Back to live."},
]


@pytest.fixture(autouse=True)
def require_model():
    ok, reason = kokoro.available()
    if not ok:
        pytest.skip(reason)


@pytest.fixture
def rendered(tmp_path):
    return kokoro.synthesize(SEGMENTS, tmp_path)


def wav_seconds(path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


class TestContract:
    def test_returns_one_duration_per_segment(self, rendered):
        _, durations = rendered
        assert len(durations) == len(SEGMENTS)

    def test_durations_are_positive(self, rendered):
        _, durations = rendered
        assert all(d > 0 for d in durations)

    def test_writes_a_stitched_track(self, rendered):
        path, _ = rendered
        assert path.exists()

    def test_durations_sum_to_the_rendered_audio(self, rendered):
        """The manifest's timings must describe the file the app will play."""
        path, durations = rendered
        assert sum(durations) == pytest.approx(wav_seconds(path), abs=0.05)

    def test_writes_one_wav_per_segment(self, rendered, tmp_path):
        assert sorted(p.name for p in tmp_path.glob("segment_*.wav")) == [
            "segment_00.wav", "segment_01.wav", "segment_02.wav"]


class TestGaps:
    def test_the_last_segment_has_no_trailing_silence(self, rendered, tmp_path):
        """This recap hands straight back to a live game; a tail reads as a stall."""
        _, durations = rendered
        last_speech = wav_seconds(tmp_path / "segment_02.wav")
        assert durations[-1] == pytest.approx(last_speech, abs=0.01)

    def test_earlier_segments_carry_the_gap(self, rendered, tmp_path):
        _, durations = rendered
        first = wav_seconds(tmp_path / "segment_00.wav")
        assert first >= config.SEGMENT_GAP


class TestRejections:
    def test_an_empty_segment_is_an_error_not_silence(self, tmp_path):
        """Silent audio with a nonzero duration desyncs every later card."""
        with pytest.raises(ValueError):
            kokoro.synthesize([{"kind": "play", "text": "   "}], tmp_path)
