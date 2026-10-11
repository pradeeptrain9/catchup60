"""Paths and tunables.

Hand-rolled env loading so the engine has no config dependency: a judge should
be able to clone this, run ./run synthetic, and get a manifest with no .env and
no network.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Lambda unpacks the package into a read-only /var/task and gives you /tmp.
# Creating cache/ next to the source therefore fails at *import* time there,
# before any handler code runs, which surfaces as an unexplained init error
# rather than as a path problem. One override keeps both deployments honest.
CACHE = Path(os.environ.get("CATCHUP60_CACHE") or ROOT / "cache")
OUT = Path(os.environ.get("CATCHUP60_OUT") or ROOT / "out")
WORK = CACHE / "work"
MODELS = CACHE / "models"
FIXTURES = ROOT / "tests" / "fixtures"


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_env()

# The recap budget. 60s is the product promise; the packer treats it as hard.
TOTAL_SECONDS = 60.0

# Fixed-cost segments, reserved before any play is selected. Measured against
# the deterministic narrator's own wording, not guessed.
INTRO_SECONDS = 5.0
OUTRO_SECONDS = 4.0

# Speech rate for the pre-synthesis budget pass. 2.6 came from shorts-factory
# and from one early measurement of a whole recap. Measured again across 18
# rendered segments it is wrong in the dangerous direction: real speech runs
# 2.28 words/sec, so the estimate was 14% low and a recap packed to 60s
# rendered at 63.9s on the device — past the one promise the product makes.
#
# Play descriptions are what drag it down. Proper names and fielding
# sequences ("grounds into a double play, first baseman to shortstop to...")
# read slower than ordinary prose, while the short generic outro runs at 3.16.
# A single constant cannot be right for both, and it is also voice-dependent:
# this is Kokoro at SPEED 1.05, where Polly differs again.
#
# So this is now set to the measured rate rather than the average one, and it
# is no longer load-bearing: recap.build enforces the budget against the
# rendered audio and trims if the estimate still missed.
WORDS_PER_SECOND = 2.28

# Headroom for per-segment variance. The rate above is accurate in aggregate but
# not per sentence — short lines synthesize faster per word than long ones
# (measured 3.10 w/s on a 14-word outro against 2.46 on an 18-word play), so a
# recap packed exactly to 60.0s can render at 60.4s. Two percent is more than
# the observed spread and costs about one second of content.
BUDGET_MARGIN = 0.02

STATSAPI = os.environ.get("CATCHUP60_STATSAPI", "https://statsapi.mlb.com")
HTTP_TIMEOUT = float(os.environ.get("CATCHUP60_HTTP_TIMEOUT", "20"))

# Kokoro weights. Overridable so the 330 MB pair can be shared with sibling
# projects instead of downloaded per repo.
KOKORO_DIR = Path(os.environ.get("CATCHUP60_KOKORO_DIR", str(MODELS)))
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"

# A catch-up is brisk by nature — the viewer is waiting to get to the live game,
# not settling in for a documentary. shorts-factory runs 0.92 for atmosphere;
# this runs slightly above natural pace for the opposite reason.
VOICE = os.environ.get("CATCHUP60_VOICE", "bm_george")
SPEED = float(os.environ.get("CATCHUP60_SPEED", "1.05"))

# Silence after each segment. Doubles as the card-change beat in the TV app: the
# cut lands in the gap, not over the voice.
SEGMENT_GAP = 0.28

for directory in (CACHE, OUT, WORK, MODELS):
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A read-only root is not a reason to refuse to import. Whatever
        # actually needs the directory will say so, with its own path in the
        # message.
        pass
