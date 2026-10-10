"""What the TV app should offer to recap.

The app asks one question — "what can I catch up on?" — and gets an ordered,
already-decided answer. Putting this in Python rather than in the app keeps it
testable, and the app has no business knowing that a Preview game cannot be
recapped or that yesterday's finals are worth offering when nothing is live.

Ordering is the product decision: a live game is the point of the app, a
finished one is still worth a recap, and a scheduled one is listed only so the
viewer can see it is coming.
"""

from datetime import date, timedelta

from . import mlb

# How far back to look for a finished game when nothing is on today. Three
# days covers a postseason off-day plus a travel day either side of it.
LOOKBACK_DAYS = 3

# The committed fixture, always last and always available. A demo at 2am in
# November needs something to show, and so does a judge with no live game.
FIXTURE = {
    "id": "synthetic",
    "away": "Harbor Gulls",
    "home": "Cedar Foxes",
    "status": "Demo game",
    "abstract": "Live",
    "series": "Offline fixture",
    "playable": True,
    "live": False,
}


def _entry(game: dict) -> dict:
    abstract = game.get("abstract", "")
    return {
        "id": str(game["gamePk"]),
        "away": game.get("away", "?"),
        "home": game.get("home", "?"),
        "status": game.get("state", "?"),
        "abstract": abstract,
        "series": game.get("series"),
        # Preview games have no plays, so there is nothing to recap yet.
        "playable": abstract in {"Live", "Final"},
        "live": abstract == "Live",
    }


def playable(today: str | None = None,
             fetch=None) -> list[dict]:
    """Games worth offering, best first, with the fixture last.

    `fetch` is injected so this can be tested without the network.
    """
    fetch = fetch or mlb.schedule
    when = today or date.today().isoformat()

    try:
        games = [_entry(g) for g in fetch(date=when)]
    except mlb.FeedError:
        # A schedule failure must not leave the app with nothing. The fixture
        # is always playable, so the Catch Up button still works.
        return [FIXTURE]

    live = [g for g in games if g["live"]]
    final = [g for g in games if g["abstract"] == "Final"]
    upcoming = [g for g in games if not g["playable"]]

    # Nothing to recap today: walk back for finished games rather than show an
    # empty screen. One day back is not enough — the postseason has off-days,
    # and a travel day between series can leave two consecutive dates empty.
    if not live and not final:
        for days in range(1, LOOKBACK_DAYS + 1):
            earlier = (date.fromisoformat(when) - timedelta(days=days)).isoformat()
            try:
                found = [
                    g for g in (_entry(x) for x in fetch(date=earlier))
                    if g["abstract"] == "Final"
                ]
            except mlb.FeedError:
                found = []
            if found:
                final = found
                break

    return [*live, *final, *upcoming, FIXTURE]
