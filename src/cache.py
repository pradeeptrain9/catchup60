"""Manifest cache, keyed on game state rather than on time.

A live game is polled repeatedly and most polls land inside the same at-bat, so
the same recap gets rebuilt — and re-synthesized, which costs 20 seconds of CPU.
Keying on (gamePk, cursor) makes those polls free.

The key deliberately excludes anything volatile. agrin learned this the hard way
with `generated_at` in a payload hash: every lookup missed, and the cache was
pure overhead. Nothing here may depend on the clock.
"""

import hashlib
import json

from . import config

DIR = config.CACHE / "recaps"


def key(game_pk: int, cursor: int | None, total_seconds: float,
        with_audio: bool, with_model: bool = False) -> str:
    """Identity of a recap request.

    `cursor` is what advances: a new at-bat is a new recap, and nothing else
    about the request changes between polls. Audio is part of the key because a
    manifest with real timings is a different artifact from one with estimates.
    """
    payload = {
        "gamePk": game_pk,
        "cursor": cursor,
        "totalSeconds": round(float(total_seconds), 3),
        "audio": bool(with_audio),
        # Model-reworded narration is a different artifact from the template's,
        # so it cannot share a cache entry.
        "model": bool(with_model),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def get(cache_key: str) -> dict | None:
    path = DIR / f"{cache_key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        # A corrupt or half-written entry is a cache miss, never an error. The
        # caller can always rebuild; failing the request because a cache file is
        # bad would turn an optimization into an outage.
        return None


def put(cache_key: str, manifest: dict) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path = DIR / f"{cache_key}.json"
        # Write-then-rename so a reader never sees a partial file.
        temp = path.with_suffix(".part")
        temp.write_text(json.dumps(manifest))
        temp.rename(path)
    except OSError:
        pass  # Failing to cache is not failing the request.
