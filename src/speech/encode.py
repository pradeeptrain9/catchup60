"""Encode narration to a format the TV can actually play.

Kokoro emits PCM wav. Vega's AudioPlayer refuses it: on the Vega Virtual Device
`canPlayType('audio/wav')` returns "" while 'audio/mpeg', 'audio/mp4' and
'audio/aac' all return "probably". Worse, the refusal is silent — play() still
resolves, and no loadedmetadata, canplay or timeupdate event ever fires, so an
app built on wav looks like a card-animation bug rather than a codec problem.

So wav is an intermediate here, never a deliverable.
"""

import shutil
import subprocess
from pathlib import Path

# MP3 over AAC because ffmpeg ships libmp3lame everywhere, and 'audio/mpeg' is
# the most broadly supported of the three types the device accepted.
BITRATE = "96k"  # Speech. Higher is wasted on a narration track.

# Kokoro renders at 24 kHz, which is fine for a file and unusual for TV audio
# hardware. Resampled to 48 kHz because consumer decoders are built around
# 44.1/48 kHz, and an off-rate stream is a plausible cause of a decoder that
# reaches `playing` and then reports MEDIA_ERR_SRC_NOT_SUPPORTED.
SAMPLE_RATE = "48000"


def available() -> tuple[bool, str]:
    if shutil.which("ffmpeg") is None:
        return False, "ffmpeg not found — brew install ffmpeg"
    return True, ""


def to_mp3(source: Path, dest: Path | None = None) -> Path:
    """Transcode a wav to mp3, returning the new path.

    Encoder delay adds on the order of 25 ms of leading silence, which is well
    inside the 0.28s gap between segments and so cannot push a card change over
    the voice. Per-segment durations therefore stay as measured from the wavs.
    """
    ok, reason = available()
    if not ok:
        raise SystemExit(reason)

    dest = dest or source.with_suffix(".mp3")
    # Write to a temp name and rename, so a reader never sees a partial file
    # and a failed encode cannot leave a plausible-looking mp3 behind.
    temp = dest.with_suffix(".part.mp3")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
         "-i", str(source),
         "-codec:a", "libmp3lame", "-b:a", BITRATE,
         "-ac", "2", "-ar", SAMPLE_RATE,
         str(temp)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        temp.unlink(missing_ok=True)
        raise SystemExit(
            f"ffmpeg failed encoding {source.name}: "
            f"{result.stderr.strip().splitlines()[-1] if result.stderr else '?'}"
        )
    temp.rename(dest)
    return dest
