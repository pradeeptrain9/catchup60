"""Polly, with the network faked but the audio real.

    pytest -m media

boto3 is stubbed to hand back genuine mp3 bytes, so the parts are measured and
concatenated by the same code the AWS path uses. What that catches is a timing
contract that only holds for Kokoro.
"""

import subprocess

import pytest

from src.speech import polly

pytestmark = pytest.mark.media

SEGMENTS = [
    {"kind": "intro", "text": "Bottom of the 7th."},
    {"kind": "play", "text": "Bichette homers."},
    {"kind": "outro", "text": "Back to live."},
]


@pytest.fixture
def fake_polly(monkeypatch, tmp_path):
    """A Polly client that returns real mp3 bytes of known length."""
    source = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-codec:a", "libmp3lame", str(source)],
        check=True, capture_output=True,
    )
    payload = source.read_bytes()

    class Stream:
        def read(self):
            return payload

    class Client:
        def __init__(self):
            self.calls = []

        def synthesize_speech(self, **kwargs):
            self.calls.append(kwargs)
            return {"AudioStream": Stream()}

    client = Client()
    monkeypatch.setattr(polly, "available", lambda: (True, ""))
    import boto3
    monkeypatch.setattr(boto3, "client", lambda service: client)
    return client


class TestContract:
    def test_returns_one_duration_per_segment(self, fake_polly, tmp_path):
        _, durations = polly.synthesize(SEGMENTS, tmp_path / "work")
        assert len(durations) == len(SEGMENTS)

    def test_durations_sum_to_the_rendered_track(self, fake_polly, tmp_path):
        from src.speech.encode import duration_seconds
        path, durations = polly.synthesize(SEGMENTS, tmp_path / "work")
        assert sum(durations) == pytest.approx(duration_seconds(path), abs=0.1)

    def test_emits_mp3_because_vega_refuses_wav(self, fake_polly, tmp_path):
        path, _ = polly.synthesize(SEGMENTS, tmp_path / "work")
        assert path.suffix == ".mp3"

    def test_asks_polly_for_mp3_with_a_neural_voice(self, fake_polly, tmp_path):
        polly.synthesize(SEGMENTS, tmp_path / "work")
        first = fake_polly.calls[0]
        assert first["OutputFormat"] == "mp3"
        assert first["Engine"] == "neural"
        assert first["Text"] == "Bottom of the 7th."

    def test_speaks_every_segment_once(self, fake_polly, tmp_path):
        polly.synthesize(SEGMENTS, tmp_path / "work")
        assert len(fake_polly.calls) == len(SEGMENTS)


class TestRejections:
    def test_an_empty_segment_is_an_error_not_silence(self, fake_polly,
                                                      tmp_path):
        with pytest.raises(ValueError):
            polly.synthesize([{"kind": "play", "text": "  "}],
                             tmp_path / "work")
