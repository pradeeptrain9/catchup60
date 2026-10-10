"""Speech via one Polly call, timed by SSML speech marks.

speech/polly.py renders a file per segment and stitches them with ffmpeg,
measuring each part with ffprobe. That is the right shape locally and the wrong
shape in Lambda, which has no ffmpeg and no ffprobe, and where Kokoro's 325MB
of ONNX does not fit inside the 250MB unzipped limit either.

So the deployed path asks Polly for the whole recap at once and lets Polly
report the boundaries. The text goes up as SSML with a <mark> before every
segment, a <break> between them, and one final mark after the last word:

    <speak><mark name="s0"/>…<break time="280ms"/><mark name="s1"/>…
           <mark name="end"/></speak>

Two calls on that same SSML — one for `json` speech marks, one for `mp3` —
give measured timings and the audio, with no subprocess and no concatenation.
Each segment's duration is the distance to the next mark, so the trailing
break lands inside the segment that precedes it. That is deliberately the same
accounting speech/kokoro.py uses, where every duration carries its own gap and
the last one carries none, which is what makes the manifest's timings
interchangeable between the two paths.

The engine must be `neural`. `generative` rejects ssml speech marks outright
("The selected speech mark type - ssml - is not supported for this engine"),
so the voice that reads best is the one that cannot tell us when it finished.
"""

import json
import os
from pathlib import Path
from xml.sax.saxutils import escape

from .. import config

VOICE = os.environ.get("CATCHUP60_POLLY_VOICE", "Matthew")

# Not configurable, unlike speech/polly.py's engine. Only neural reports ssml
# speech marks, and without those this module has no timings to return.
ENGINE = "neural"

# Polly accepts 6000 characters per request, 3000 of them billable. A 60-second
# recap runs near 1500, so the ceiling is a guard against a malformed caller
# rather than a limit the product can reach.
MAX_SSML_CHARS = 6000


def available() -> tuple[bool, str]:
    """Credentials only. Nothing here shells out, so there is no ffmpeg to find."""
    from ..narrate.bedrock import _aws_ready
    return _aws_ready()


def build_ssml(segments: list[dict], gap: float) -> str:
    """One SSML document with a mark before each segment and one at the end."""
    gap_ms = int(round(gap * 1000))
    parts = ["<speak>"]
    for position, segment in enumerate(segments):
        text = (segment.get("text") or "").strip()
        if not text:
            raise ValueError(f"segment {position} has no text to speak")
        if position:
            parts.append(f'<break time="{gap_ms}ms"/>')
        parts.append(f'<mark name="s{position}"/>{escape(text)}')
    parts.append('<mark name="end"/></speak>')
    ssml = "".join(parts)
    if len(ssml) > MAX_SSML_CHARS:
        raise ValueError(
            f"ssml is {len(ssml)} characters, over Polly's {MAX_SSML_CHARS}"
        )
    return ssml


def durations_from_marks(marks: list[dict], count: int) -> list[float]:
    """Segment durations from mark times, in seconds.

    Polly puts a few milliseconds of silence before the first word, so the
    first mark is not at zero. Treating zero as segment 0's start rather than
    that mark folds the lead-in into the first segment, which keeps every
    later start equal to its own mark — the manifest's timings then match the
    audio instead of running uniformly early by the width of that silence.
    """
    times = {mark["value"]: mark["time"] / 1000.0 for mark in marks}
    missing = [n for n in [f"s{i}" for i in range(count)] + ["end"]
               if n not in times]
    if missing:
        raise ValueError(f"polly returned no mark for {', '.join(missing)}")

    boundaries = [0.0] + [times[f"s{i}"] for i in range(1, count)] + \
                 [times["end"]]
    durations = [round(boundaries[i + 1] - boundaries[i], 3)
                 for i in range(count)]
    if any(d <= 0 for d in durations):
        raise ValueError(f"polly marks are not increasing: {durations}")
    return durations


def synthesize(
    segments: list[dict],
    workdir: Path,
    *,
    voice: str | None = None,
    gap: float | None = None,
) -> tuple[Path, list[float]]:
    """Render the whole recap in one call. Returns (mp3_path, durations)."""
    import boto3

    ok, reason = available()
    if not ok:
        raise SystemExit(reason)

    voice = voice or VOICE
    gap = config.SEGMENT_GAP if gap is None else gap
    ssml = build_ssml(segments, gap)

    polly = boto3.client("polly")
    common = {"Text": ssml, "TextType": "ssml", "VoiceId": voice,
              "Engine": ENGINE}

    # Marks first. If the timings cannot be had there is no point paying for
    # audio the manifest would be unable to describe.
    marked = polly.synthesize_speech(
        OutputFormat="json", SpeechMarkTypes=["ssml"], **common,
    )
    marks = [json.loads(line) for line
             in marked["AudioStream"].read().decode().splitlines() if line]
    durations = durations_from_marks(marks, len(segments))

    spoken = polly.synthesize_speech(OutputFormat="mp3", **common)
    workdir.mkdir(parents=True, exist_ok=True)
    narration = workdir / "narration.mp3"
    with open(narration, "wb") as handle:
        handle.write(spoken["AudioStream"].read())
    return narration, durations
