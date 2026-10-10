"""The engine's view of a game.

Everything downstream — ranking, packing, narration, the guard's allowed-number
set — reads these types and never the raw StatsAPI JSON. One translation point
means one place to fix when the feed changes shape.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Play:
    """One completed at-bat, with the only importance signal we trust."""

    index: int  # atBatIndex; stable within a game, so it is our as-of cursor
    inning: int
    half: str  # "top" | "bottom"
    event: str  # "Home Run", "Groundout", ...
    description: str  # StatsAPI's own sentence; we never paraphrase it away
    away_score: int  # score AFTER this play
    home_score: int
    rbi: int
    outs: int
    batter: str
    pitcher: str
    wpa: float  # homeTeamWinProbabilityAdded, signed toward the home team
    home_wp: float  # home win probability after the play
    is_scoring: bool
    captivating: int  # StatsAPI's own 0-100 highlight hint; a tie-breaker only

    @property
    def swing(self) -> float:
        """How much this play moved the game. The whole ranking rests here."""
        return abs(self.wpa)

    @property
    def half_key(self) -> tuple[int, str]:
        return (self.inning, self.half)


@dataclass(frozen=True)
class GameState:
    """Where the game stands at the as-of cursor."""

    inning: int
    half: str
    away_score: int
    home_score: int
    outs: int

    def as_dict(self) -> dict:
        return {
            "inning": self.inning,
            "half": self.half,
            "away": self.away_score,
            "home": self.home_score,
            "outs": self.outs,
        }


@dataclass(frozen=True)
class GameContext:
    """Identity and status. Abbreviations only — no logos, no marks."""

    game_pk: int
    away_abbr: str
    home_abbr: str
    away_name: str
    home_name: str
    detailed_state: str
    abstract_state: str  # "Preview" | "Live" | "Final"
    # atBatIndex of the current play, from the cheap feed call. None before the
    # first pitch. Used to poll a live game without pulling the 39 KB
    # win-probability payload on every tick.
    cursor: int | None = None

    @property
    def is_live(self) -> bool:
        return self.abstract_state == "Live"

    @property
    def has_started(self) -> bool:
        return self.abstract_state in {"Live", "Final"}


def ordinal(n: int) -> str:
    """1 -> 1st. Used in narration, so it must never produce a stray number."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def state_after(plays: list[Play]) -> GameState:
    """Game state implied by the last play we are allowed to know about.

    Derived from the plays themselves rather than from the live linescore, so a
    replay at --as-of N reproduces exactly what a viewer would have seen then.
    """
    if not plays:
        return GameState(inning=1, half="top", away_score=0, home_score=0, outs=0)
    last = plays[-1]
    return GameState(
        inning=last.inning,
        half=last.half,
        away_score=last.away_score,
        home_score=last.home_score,
        outs=last.outs,
    )
