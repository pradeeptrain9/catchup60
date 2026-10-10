"""MLB StatsAPI client.

Public, no key, no auth. Two calls per recap, both narrowed with the API's own
`fields` parameter: the unfiltered winProbability response for a full game is
1.08 MB, and the filtered one is 39 KB. That 27x matters when this runs in a
Lambda and polls a game every few seconds.
"""

import httpx

from . import config
from .engine.state import GameContext, Play

# Every field the engine reads, and nothing else. StatsAPI's `fields` filter is
# a flat name list, not a path list, so a name is kept wherever it appears.
WP_FIELDS = ",".join([
    "atBatIndex",
    "homeTeamWinProbability",
    "awayTeamWinProbabilityAdded",
    "homeTeamWinProbabilityAdded",
    "about", "inning", "halfInning", "isTopInning", "isScoringPlay",
    "captivatingIndex",
    "result", "event", "description", "awayScore", "homeScore", "rbi",
    "count", "outs",
    "matchup", "batter", "pitcher", "fullName",
])

FEED_FIELDS = ",".join([
    "gameData", "teams", "away", "home", "abbreviation", "teamName", "id",
    "status", "detailedState", "abstractGameState",
])

SCHEDULE_FIELDS = ",".join([
    "dates", "date", "games", "gamePk", "gameDate", "teams", "away", "home",
    "team", "name", "id", "status", "detailedState", "abstractGameState",
    "seriesDescription",
])


class FeedError(RuntimeError):
    """A StatsAPI call failed in a way the caller should surface, not retry."""


def _get(path: str, params: dict | None = None) -> dict | list:
    url = f"{config.STATSAPI}{path}"
    try:
        response = httpx.get(url, params=params or {}, timeout=config.HTTP_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        raise FeedError(f"{url} failed: {exc}") from exc


def schedule(date: str | None = None, start: str | None = None,
             end: str | None = None) -> list[dict]:
    """Games for a date (YYYY-MM-DD) or an inclusive date range."""
    params: dict = {"sportId": 1, "fields": SCHEDULE_FIELDS}
    if start and end:
        params["startDate"], params["endDate"] = start, end
    elif date:
        params["date"] = date
    payload = _get("/api/v1/schedule", params)
    games: list[dict] = []
    for day in payload.get("dates", []):
        for game in day.get("games", []):
            games.append({
                "gamePk": game["gamePk"],
                "date": day["date"],
                "start": game.get("gameDate"),
                "away": game["teams"]["away"]["team"].get("name", "?"),
                "home": game["teams"]["home"]["team"].get("name", "?"),
                "state": game["status"].get("detailedState", "?"),
                "abstract": game["status"].get("abstractGameState", "?"),
                "series": game.get("seriesDescription"),
            })
    return games


def context(game_pk: int) -> GameContext:
    """Team abbreviations and status. 403 bytes on the wire."""
    payload = _get(
        f"/api/v1.1/game/{game_pk}/feed/live", {"fields": FEED_FIELDS}
    )
    data = payload.get("gameData", {})
    teams = data.get("teams", {})
    away, home = teams.get("away", {}), teams.get("home", {})
    status = data.get("status", {})
    return GameContext(
        game_pk=game_pk,
        away_abbr=away.get("abbreviation", "AWY"),
        home_abbr=home.get("abbreviation", "HOM"),
        away_name=away.get("teamName", "Away"),
        home_name=home.get("teamName", "Home"),
        detailed_state=status.get("detailedState", "Unknown"),
        abstract_state=status.get("abstractGameState", "Unknown"),
    )


def parse_plays(raw: list[dict]) -> list[Play]:
    """Translate the winProbability response into Play records.

    Plays arrive in chronological order and keep that order. Anything missing
    the win-probability delta is dropped rather than defaulted to zero: a play
    we cannot score is a play we must not rank.
    """
    plays: list[Play] = []
    for item in raw:
        wpa = item.get("homeTeamWinProbabilityAdded")
        if wpa is None:
            continue
        about = item.get("about", {})
        result = item.get("result", {})
        matchup = item.get("matchup", {})
        plays.append(Play(
            index=item.get("atBatIndex", about.get("atBatIndex", len(plays))),
            inning=about.get("inning", 0),
            half=about.get("halfInning", "top"),
            event=result.get("event", ""),
            description=result.get("description", ""),
            away_score=result.get("awayScore", 0),
            home_score=result.get("homeScore", 0),
            rbi=result.get("rbi", 0),
            outs=item.get("count", {}).get("outs", 0),
            batter=matchup.get("batter", {}).get("fullName", ""),
            pitcher=matchup.get("pitcher", {}).get("fullName", ""),
            wpa=float(wpa),
            home_wp=float(item.get("homeTeamWinProbability") or 0.0),
            is_scoring=bool(about.get("isScoringPlay", False)),
            captivating=int(about.get("captivatingIndex") or 0),
        ))
    return plays


def win_probability(game_pk: int) -> list[Play]:
    raw = _get(f"/api/v1/game/{game_pk}/winProbability", {"fields": WP_FIELDS})
    if not isinstance(raw, list):
        raise FeedError(f"winProbability for {game_pk} was not a list")
    return parse_plays(raw)
