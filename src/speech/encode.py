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


def duration_seconds(path: Path) -> float:
    """Length of an audio file, measured rather than assumed.

    The manifest's timings must describe the file the app actually plays, so
    every duration that reaches it is measured from real audio.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed on {path.name}")
    return float(result.stdout.strip())


def concat_with_gaps(parts: list[Path], gap: float, dest: Path) -> list[float]:
    """Join audio parts, padding all but the last with `gap` seconds.

    Returns the per-part durations including their padding, which is what the
    manifest's segment timings are built from.

    Padding is applied by ffmpeg's `apad` rather than by splicing silence files,
    so the gap is exact and there is no second format to keep in step. The last
    part is unpadded: this recap hands straight back to a live game, and a tail
    of silence before the handoff reads as a stall.
    """
    ok, reason = available()
    if not ok:
        raise SystemExit(reason)
    if not parts:
        raise ValueError("nothing to concatenate")

    last = len(parts) - 1
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for index, part in enumerate(parts):
        inputs += ["-i", str(part)]
        pad = 0.0 if index == last else gap
        label = f"a{index}"
        filters.append(f"[{index}:a]apad=pad_dur={pad}[{label}]")
        labels.append(f"[{label}]")
    graph = (";".join(filters) + ";" + "".join(labels)
             + f"concat=n={len(parts)}:v=0:a=1[out]")

    temp = dest.with_suffix(".part.mp3")
    result = subprocess.run(
        ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", graph, "-map", "[out]",
         "-codec:a", "libmp3lame", "-b:a", BITRATE,
         "-ac", "2", "-ar", SAMPLE_RATE, str(temp)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        temp.unlink(missing_ok=True)
        tail = result.stderr.strip().splitlines()
        raise SystemExit(f"ffmpeg concat failed: {tail[-1] if tail else '?'}")
    temp.rename(dest)

    return [
        duration_seconds(part) + (0.0 if index == last else gap)
        for index, part in enumerate(parts)
    ]
