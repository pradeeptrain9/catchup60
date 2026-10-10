"""Paths and tunables.

Hand-rolled env loading so the engine has no config dependency: a judge should
be able to clone this, run ./run synthetic, and get a manifest with no .env and
no network.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
OUT = ROOT / "out"
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

# Speech rate for the pre-synthesis budget pass. Lifted from shorts-factory,
# where it held up across hundreds of Kokoro renders.
WORDS_PER_SECOND = 2.6

STATSAPI = os.environ.get("CATCHUP60_STATSAPI", "https://statsapi.mlb.com")
HTTP_TIMEOUT = float(os.environ.get("CATCHUP60_HTTP_TIMEOUT", "20"))

for directory in (CACHE, OUT, WORK, MODELS):
    directory.mkdir(parents=True, exist_ok=True)
