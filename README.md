# Catch-Up 60

**You sat down 40 minutes into the game. Press one button, get a 60-second
recap of the game as it stands right now, then land at the live edge.**

Built for the Amazon Developer Hackathon, Fire TV track (Vega OS). The recap is
rebuilt from the live feed every time you ask for it, so launching it again ten
minutes later gives you a different recap.

## The one rule

**Which plays mattered is computed, never asked of a model.**

MLB StatsAPI publishes a per-play win-probability delta. Importance is
arithmetic on that field — `abs(homeTeamWinProbabilityAdded)`. A language model
only chooses words, and every number it writes is checked against the engine's
own JSON before anything is spoken. A model that decides what mattered will
confidently tell you the game turned on a groundout, and there is no way to
catch that after the fact.

## Quick start

```bash
./setup.sh
./run doctor
./run synthetic --summary
```

`synthetic` uses a fictional game committed to the repo. No key, no network, no
live game required — it works in November, long after the postseason.

`setup.sh` needs a Python between 3.10 and 3.13 and will find one: kokoro-onnx
does not support 3.14. The engine alone runs on any 3.11+; only speech has the
ceiling. It also fetches the Kokoro weights (~330 MB, once). Set
`CATCHUP60_KOKORO_DIR` to share them with another project instead.

Against real games:

```bash
./run games                              # today's games and their gamePks
./run recap 849820 --summary             # recap the game as it stands now
./run recap 849820 --as-of 63 --summary  # replay the game as of that at-bat
```

`--as-of` takes an `atBatIndex`, so a finished game replays exactly what a
viewer would have been shown at that moment. That is what makes the demo
rehearsable and the output testable.

### Narration

```bash
./run synthetic --audio --summary
./run recap 849820 --audio --out recap.json
```

`--audio` synthesizes the narration locally with Kokoro and replaces the
manifest's estimated timings with the real ones (`timingSource` flips from
`estimate` to `tts`). Runs about 3x faster than realtime — roughly 20 seconds
for a 60-second recap — on CPU, with no key and no per-call cost.

Synthesis is strictly downstream of the guard. If narration ever fails the
numeric check, nothing is spoken: the manifest comes back on estimated timings
with `speechSkipped` set. A wrong figure read aloud is worse than no audio.

## How it works

```
StatsAPI winProbability
   -> engine/rank.py     score = abs(homeTeamWinProbabilityAdded)
   -> engine/pack.py     fit into the 60s budget, keep innings spread,
                         then make every run on the scoreboard traceable
   -> narrate/script.py  deterministic sentences from engine output
   -> narrate/guard.py   reject any figure the engine did not produce
   -> speech/            synthesis, strictly downstream of the guard
   -> manifest.py        timed segments
   -> tv/                Vega app animates cards against the audio track
```

Order is load-bearing. Synthesis sits downstream of the guard so audio can never
say a number the text was not allowed to.

### Two things the engine does that a naive version does not

**It keeps the innings spread.** Selecting purely by swing produces six plays
from one chaotic inning and a viewer who still does not know how the game got
there. Plays are selected under a per-half-inning cap that relaxes only while
budget remains.

**It explains the score.** Swing ranking alone produces recaps where the score
goes 2-0 to 4-0 across a strikeout, because the strikeout moved win probability
more than either run did — leaving the viewer to infer two runs from nothing.
Runs are accounted for one at a time, per half-inning, and a half-inning that
scored three runs is not satisfied by one selected RBI single. The manifest
reports `runsExplained` / `runsTotal` so a gap is visible rather than hidden.

Run coverage deliberately overrides the swing floor: a sacrifice fly may move
the game less than the floor allows, but the viewer still watched the score
change. Plays admitted that way are counted in `coverageAdded`.

## Manifest

The contract between the engine and the TV app. Segment timings are absolute and
contiguous, because the app animates cards against a single audio track: a gap
or overlap shows up on screen as a card that changes mid-sentence.

```json
{
  "gamePk": 823570,
  "asOfPlayIndex": 55,
  "gameState": {"inning": 7, "half": "bottom", "away": 4, "home": 1, "outs": 1},
  "totalSeconds": 53.46,
  "timingSource": "estimate",
  "narrationSource": "template",
  "guardViolations": [],
  "engine": {"selected": 7, "considered": 23, "runsExplained": 5, "runsTotal": 5,
             "limitedBy": "count", "coverageAdded": 0},
  "segments": [
    {"kind": "intro", "start": 0.0, "dur": 4.62, "text": "..."},
    {"kind": "play", "start": 4.62, "dur": 8.85, "playIndex": 3, "text": "..."}
  ]
}
```

`timingSource` is `estimate` until speech is synthesized and `tts` after. The
app is entitled to know when it has been handed a guess — though the two agree
closely by construction: measured against rendered audio, the estimate for the
fixture game is 53.11s against 52.73s real.

`limitedBy` names what actually stopped the recap — `budget`, `count` or
`supply` — decided after every selection pass rather than from the first one, so
it points at the knob worth turning.

## Tests

```bash
pytest           # offline, no model needed; a bare clone goes green
pytest -m tts    # real speech synthesis (needs the Kokoro weights)
pytest -m live   # hits the real StatsAPI
```

59 offline, 8 speech, 4 live.

The live tests exist because the feed's shape is the one thing this project does
not control, and a field rename would otherwise surface as a broken demo.

## Notes on content

No team logos, no game footage, no commercial music — team identity is text
abbreviations only. The committed fixture game uses fictional teams, and is the
safe source for any demo frame where real club names would raise a question.
