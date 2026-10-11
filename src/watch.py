"""Does winProbability actually update during a live game?

Every ranking decision in this project reads `homeTeamWinProbabilityAdded`
from `/api/v1/game/{pk}/winProbability`. That has only ever been confirmed on
*finished* games. If the endpoint is populated in bulk after a game ends —
which is a perfectly normal way for a stats provider to work — then the
product's central beat, launching the recap again ten minutes later and
getting a different one, does not exist, and the whole design has to change.

Cheap to answer today. Impossible to answer the night before the deadline.

So this polls a game and writes one JSON line per tick: what the cheap feed
says the cursor is, how many plays winProbability has published, and the swing
of the last one. Afterwards the question is arithmetic on a file rather than a
memory of watching a screen. The record is the point — a premise confirmed by
recollection is a premise still unconfirmed.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, mlb


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tick(game_pk: int) -> dict:
    """One observation. Never raises: a watcher that dies at 2am is no watcher."""
    row: dict = {"at": _now()}
    try:
        context = mlb.context(game_pk)
        row["state"] = context.abstract_state
        row["detail"] = context.detailed_state
        row["cursor"] = context.cursor
    except Exception as exc:
        row["error"] = f"context: {type(exc).__name__}: {exc}"
        return row

    if not context.has_started:
        return row

    try:
        plays = mlb.win_probability(game_pk)
    except Exception as exc:
        # The interesting failure. A live game whose winProbability 404s while
        # the feed advances is the answer to the question, not an outage.
        row["error"] = f"winProbability: {type(exc).__name__}: {exc}"
        return row

    row["wpPlays"] = len(plays)
    if plays:
        last = plays[-1]
        row["wpLastIndex"] = last.index
        row["wpLastSwing"] = round(last.swing, 2)
        row["score"] = [last.away_score, last.home_score]
        row["inning"] = f"{last.half} {last.inning}"
        # The gap that matters. The feed's cursor is the live edge; wpLastIndex
        # is how far the ranking signal has caught up to it. A gap that stays
        # constant is a working feed running a play or two behind. A gap that
        # grows all game is a feed that is not publishing until the end.
        if context.cursor is not None:
            row["lag"] = context.cursor - last.index
    return row


def watch(game_pk: int, *, every: float = 60.0, hours: float = 26.0,
          idle_every: float = 600.0, dest: Path | None = None) -> Path:
    """Poll until the game ends or `hours` runs out.

    Two cadences, because the useful window is three hours inside a day-long
    wait: first pitch is often most of a day away, and polling a scheduled game
    every minute until then is a thousand requests that answer nothing. Slow
    until the game goes Live, fast once it does.
    """
    dest = dest or config.OUT / f"watch-{game_pk}.jsonl"
    dest.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + hours * 3600

    print(f"watching {game_pk}: {idle_every:.0f}s until live, "
          f"then {every:.0f}s -> {dest}", file=sys.stderr)
    with open(dest, "a") as handle:
        while time.time() < deadline:
            row = tick(game_pk)
            handle.write(json.dumps(row) + "\n")
            handle.flush()  # the file is the product; buffering loses it
            print(f"  {row.get('at')} {row.get('state','?'):8}"
                  f" cursor={row.get('cursor')} wpPlays={row.get('wpPlays')}"
                  f" lag={row.get('lag')}"
                  + (f" {row['error']}" if row.get("error") else ""),
                  file=sys.stderr, flush=True)
            pause = every if row.get("state") == "Live" else idle_every
            if row.get("state") == "Final":
                # One more tick after Final is deliberate: it captures whether
                # a backfill lands at the whistle, which is exactly the failure
                # mode being tested for.
                time.sleep(every)
                handle.write(json.dumps(tick(game_pk)) + "\n")
                handle.flush()
                break
            time.sleep(pause)
    return dest


def parse(text: str) -> list[dict]:
    """Rows out of jsonl, skipping anything unreadable.

    The last line of a watch file is routinely a fragment — the watcher is
    killed with ^C, or the laptop closes mid-write. Losing the whole record to
    it would be absurd.
    """
    rows = []
    for line in text.splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def verdict(path: Path) -> dict:
    """Read a watch file and answer the question it was opened to answer."""
    return verdict_rows(parse(path.read_text()))


def verdict_rows(rows: list[dict]) -> dict:
    """The arithmetic, separated from where the rows came from.

    Two watchers now feed this: the local one writing jsonl, and a scheduled
    Lambda writing one object per tick to S3. The question is the same either
    way, and there must be exactly one implementation of the answer — a second
    copy in the handler is a copy that disagrees with this one on the morning
    it matters.
    """
    rows = sorted(rows, key=lambda r: r.get("at") or "")
    live = [r for r in rows if r.get("state") == "Live" and "wpPlays" in r]
    counts = [r["wpPlays"] for r in live]
    grew = sum(1 for a, b in zip(counts, counts[1:]) if b > a)
    lags = [r["lag"] for r in live if r.get("lag") is not None]

    return {
        "ticks": len(rows),
        "liveTicks": len(live),
        "wpPlaysFirst": counts[0] if counts else None,
        "wpPlaysLast": counts[-1] if counts else None,
        "timesItGrew": grew,
        "lagMin": min(lags) if lags else None,
        "lagMax": max(lags) if lags else None,
        "errorsWhileLive": [r["error"] for r in rows
                            if r.get("state") == "Live" and r.get("error")][:5],
        # The one line this file exists to produce. Tri-state on purpose:
        # None is "never saw a live tick", which is not the same answer as
        # "watched it live and the endpoint stood still". A plain False for
        # both reads as a disproof of the premise the whole project rests on,
        # when in fact nothing was observed — the first run of this watcher
        # idled nine hours in Preview against a game whose first pitch was
        # still eight hours out, and reported `updatesMidGame: false`.
        "updatesMidGame": bool(grew) if live else None,
        "verdict": (
            "updates mid-game" if grew
            else "inconclusive — no live ticks observed" if not live
            else "did NOT update across %d live ticks" % len(live)
        ),
    }
