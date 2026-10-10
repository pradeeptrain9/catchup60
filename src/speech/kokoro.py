"""Local speech synthesis via Kokoro ONNX. No key, no network, no per-call cost.

Ported from shorts-factory, with two changes that matter here.

First, the trailing gap is dropped from the final segment. shorts-factory pads
every beat equally because its output is a video that fades out; this output is
a recap that hands straight back to a live game, and 0.28s of dead air before
the handoff reads as a stall.

Second, the returned durations are the manifest's timings. They include each
segment's gap, so the card change lands in the silence rather than over the
voice, and consecutive segments stay contiguous by construction.
"""

import sys
from pathlib import Path

from .. import config

_engine = None


def available() -> tuple[bool, str]:
    """Whether synthesis can run, and if not, the fix.

    Checked rather than attempted because the engine path is the one that must
    always work: a missing model should degrade the recap to estimated timings,
    not fail the command.
    """
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False, "kokoro-onnx not installed — run ./setup.sh"
    except Exception as exc:  # a broken install surfaces here, not at render
        return False, f"kokoro-onnx failed to import: {exc}"
    if not config.KOKORO_MODEL.exists():
        return False, f"model missing at {config.KOKORO_MODEL} — run ./setup.sh"
    if not config.KOKORO_VOICES.exists():
        return False, f"voices missing at {config.KOKORO_VOICES} — run ./setup.sh"
    return True, ""


def engine():
    global _engine
    if _engine is None:
        ok, reason = available()
        if not ok:
            raise SystemExit(reason)
        from kokoro_onnx import Kokoro
        _engine = Kokoro(str(config.KOKORO_MODEL), str(config.KOKORO_VOICES))
    return _engine


def synthesize(
    segments: list[dict],
    workdir: Path,
    *,
    voice: str = None,
    speed: float = None,
    gap: float = None,
    progress: bool = False,
) -> tuple[Path, list[float]]:
    """Render one wav per segment plus a stitched track.

    Returns (narration_path, durations) with one duration per segment, in order.
    """
    import numpy as np
    import soundfile as sf

    voice = voice or config.VOICE
    speed = config.SPEED if speed is None else speed
    gap = config.SEGMENT_GAP if gap is None else gap

    kokoro = engine()
    workdir.mkdir(parents=True, exist_ok=True)

    chunks: list = []
    durations: list[float] = []
    rate = None
    last = len(segments) - 1

    for position, segment in enumerate(segments):
        text = (segment.get("text") or "").strip()
        if not text:
            raise ValueError(f"segment {position} has no text to speak")

        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        samples = np.asarray(samples, dtype=np.float32)

        # No tail on the last segment: this recap hands back to a live game.
        tail = 0.0 if position == last else gap
        piece = np.concatenate(
            [samples, np.zeros(int(rate * tail), dtype=np.float32)]
        )

        sf.write(workdir / f"segment_{position:02d}.wav", piece, rate)
        chunks.append(piece)
        durations.append(len(piece) / rate)
        if progress:
            # stderr, not stdout: the manifest goes to stdout, and progress
            # chatter mixed into it breaks `./run recap --audio > out.json`.
            kind = segment.get("kind", "?")
            print(f"   {position + 1}/{len(segments)} [{kind}] "
                  f"{durations[-1]:.2f}s", file=sys.stderr, flush=True)

    narration = workdir / "narration.wav"
    sf.write(narration, np.concatenate(chunks), rate)
    return narration, durations
