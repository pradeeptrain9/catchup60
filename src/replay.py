"""Make a finished game behave like a live one.

Two problems, one answer.

The first is that the TV app's live path has never run. Every frame so far has
come from a finished game or the committed fixture, and the live path differs
in ways that matter: the game sorts first and carries a LIVE badge, the outro
says "back to live" instead of "that's your final", and the recap is supposed
to *change* as the cursor advances. Code that has never run is not code that
works, and the next live game is most of a day away.

The second is the demo. The shot the whole project rests on is launching the
recap, waiting, launching it again, and seeing a different recap — and that
shot cannot be rehearsed if it requires a live game to be in progress at the
moment the camera is on.

So: take a finished game, pick a start time, and map wall-clock seconds onto
at-bat indices. The server then answers every request with the cursor the
replay clock says we are at. Nothing here fabricates data — every play is the
real play from the real feed, arriving in the real order. What is synthesized
is only *when* they arrive.

That distinction is why this is disclosed on screen rather than hidden: the
recap is genuine, the clock is not.
"""

import time
from dataclasses import dataclass

# An at-bat every ten seconds. Real baseball runs nearer one every two or three
# minutes, which is correct and useless to watch: the point of a replay is to
# reach "ask again and the recap changed" inside a demo, not inside an evening.
DEFAULT_SECONDS_PER_AT_BAT = 10.0

# Start a little way in. A replay that opens at the first pitch has nothing to
# recap for its first minute, which is a poor first frame and a worse demo.
DEFAULT_HEAD_START = 20


@dataclass
class Replay:
    """A finished game, played back against the wall clock."""

    game_pk: int
    seconds_per_at_bat: float = DEFAULT_SECONDS_PER_AT_BAT
    head_start: int = DEFAULT_HEAD_START
    started_at: float = 0.0
    last_index: int | None = None  # the real game's final at-bat, once known

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = time.time()

    def cursor(self, now: float | None = None) -> int:
        """Which at-bat the replay is standing on."""
        elapsed = (now or time.time()) - self.started_at
        index = self.head_start + int(elapsed / self.seconds_per_at_bat)
        if self.last_index is not None:
            # Past the end, the replay holds at the final at-bat rather than
            # running off into indices the feed does not have. It reports
            # itself finished from then on.
            return min(index, self.last_index)
        return index

    def is_finished(self, now: float | None = None) -> bool:
        return (self.last_index is not None
                and self.cursor(now) >= self.last_index)

    def describe(self) -> dict:
        """What the app and the disclosure caption both need to know."""
        return {
            "gamePk": self.game_pk,
            "secondsPerAtBat": self.seconds_per_at_bat,
            "cursor": self.cursor(),
            "finished": self.is_finished(),
        }
