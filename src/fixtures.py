"""Loader for the offline fixture game.

Exists so `./run synthetic` works with no key, no network and no live game. A
judge cloning this repo at 2am in November, long after the postseason, still
gets a real manifest out of it.
"""

import json

from . import config
from .engine.state import GameContext, Play
from .mlb import parse_plays

SYNTHETIC = config.FIXTURES / "synthetic_game.json"


def load_synthetic() -> tuple[GameContext, list[Play]]:
    payload = json.loads(SYNTHETIC.read_text())
    raw = payload["context"]
    context = GameContext(
        game_pk=raw["gamePk"],
        away_abbr=raw["away"]["abbreviation"],
        home_abbr=raw["home"]["abbreviation"],
        away_name=raw["away"]["teamName"],
        home_name=raw["home"]["teamName"],
        detailed_state=raw["detailedState"],
        abstract_state=raw["abstractGameState"],
    )
    # Parsed through the same translator as live data, so the fixture exercises
    # the real code path instead of a parallel one that can drift.
    return context, parse_plays(payload["winProbability"])
