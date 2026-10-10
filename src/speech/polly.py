"""Speech via Amazon Polly.

The AWS counterpart to speech/kokoro.py, behind the same contract: render one
file per segment, return the stitched track and the per-segment durations that
become the manifest's timings.

Polly emits mp3 directly, which is what Vega's player wants — wav is refused
outright there. Durations are measured from the rendered files rather than
estimated, so the manifest describes the audio the app actually plays.
"""

import os
from pathlib import Path

from .. import config
from .encode import concat_with_gaps, duration_seconds

# Matthew reads sports copy without the sing-song that the older concatenative
# voices bring to short declarative sentences.
VOICE = os.environ.get("CATCHUP60_POLLY_VOICE", "Matthew")
ENGINE = os.environ.get("CATCHUP60_POLLY_ENGINE", "neural")


def available() -> tuple[bool, str]:
    try:
        import boto3
    except ImportError:
        return False, "boto3 not installed — pip install -r requirements-aws.txt"
    session = boto3.Session()
    if session.get_credentials() is None:
        return False, "no AWS credentials — aws configure, or set AWS_PROFILE"
    if not (session.region_name or os.environ.get("AWS_REGION")):
        return False, "no AWS region — set AWS_REGION or configure a default"
    from .encode import available as ffmpeg_available
    return ffmpeg_available()


def synthesize(
    segments: list[dict],
    workdir: Path,
    *,
    voice: str | None = None,
    engine: str | None = None,
    gap: float | None = None,
    progress: bool = False,
) -> tuple[Path, list[float]]:
    """Render segments through Polly. Returns (mp3_path, durations)."""
    import sys

    import boto3

    ok, reason = available()
    if not ok:
        raise SystemExit(reason)

    voice = voice or VOICE
    engine = engine or ENGINE
    gap = config.SEGMENT_GAP if gap is None else gap
    workdir.mkdir(parents=True, exist_ok=True)

    polly = boto3.client("polly")
    parts: list[Path] = []

    for position, segment in enumerate(segments):
        text = (segment.get("text") or "").strip()
        if not text:
            raise ValueError(f"segment {position} has no text to speak")

        response = polly.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=voice, Engine=engine,
        )
        part = workdir / f"segment_{position:02d}.mp3"
        with open(part, "wb") as handle:
            handle.write(response["AudioStream"].read())
        parts.append(part)
        if progress:
            # stderr, because the manifest goes to stdout.
            print(f"   {position + 1}/{len(segments)} "
                  f"[{segment.get('kind', '?')}] "
                  f"{duration_seconds(part):.2f}s",
                  file=sys.stderr, flush=True)

    narration = workdir / "narration.mp3"
    durations = concat_with_gaps(parts, gap, narration)
    return narration, durations
