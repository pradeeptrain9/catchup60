"""Audio assembly. Shells out to ffmpeg, so marked.

    pytest -m media

The contract these protect: durations reaching the manifest are measured from
real audio and sum to the file the app will play. An estimate that drifts from
the file shows up on screen as a card changing mid-sentence.
"""

import pytest

from src import config
from src.speech.encode import (
    SAMPLE_RATE, concat_with_gaps, duration_seconds, to_mp3,
)

pytestmark = pytest.mark.media

SOURCE = config.FIXTURES / "synthetic_game.json"  # presence check only


@pytest.fixture
def tone(tmp_path):
    """Three short audio files, generated rather than committed."""
    import subprocess
    parts = []
    for index, seconds in enumerate((1.0, 2.0, 1.5)):
        part = tmp_path / f"tone_{index}.wav"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
             str(part)],
            check=True, capture_output=True,
        )
        parts.append(part)
    return parts


class TestDuration:
    def test_measures_a_known_length(self, tone):
        assert duration_seconds(tone[0]) == pytest.approx(1.0, abs=0.05)


class TestToMp3:
    def test_produces_an_mp3_at_a_tv_friendly_rate(self, tone):
        """Vega refuses wav; 24 kHz is unusual for consumer decoders."""
        import subprocess
        out = to_mp3(tone[0])
        assert out.suffix == ".mp3"
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=sample_rate,codec_name", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True,
        )
        assert "mp3" in probe.stdout
        assert SAMPLE_RATE in probe.stdout

    def test_leaves_no_partial_file(self, tone):
        to_mp3(tone[0])
        assert list(tone[0].parent.glob("*.part.mp3")) == []


class TestConcat:
    def test_pads_every_part_but_the_last(self, tone, tmp_path):
        """A tail of silence before the handoff to live reads as a stall."""
        gap = 0.25
        durations = concat_with_gaps(tone, gap, tmp_path / "out.mp3")
        assert durations[0] == pytest.approx(1.0 + gap, abs=0.05)
        assert durations[1] == pytest.approx(2.0 + gap, abs=0.05)
        assert durations[-1] == pytest.approx(1.5, abs=0.05)

    def test_durations_sum_to_the_rendered_file(self, tone, tmp_path):
        dest = tmp_path / "out.mp3"
        durations = concat_with_gaps(tone, 0.25, dest)
        assert sum(durations) == pytest.approx(duration_seconds(dest), abs=0.1)

    def test_refuses_an_empty_list(self, tmp_path):
        with pytest.raises(ValueError):
            concat_with_gaps([], 0.25, tmp_path / "out.mp3")
