# Demo video plan

Under 3 minutes, YouTube or Vimeo, public, English. Judges are not required to
watch past 3:00, so the recap plays inside the first minute.

## The audio decision, and the disclosure

The Vega Virtual Device cannot play audio — its sink never initializes (see
`FRICTION.md` entry 7). We have no physical Fire TV Stick, so a screen recording
of the simulator is silent.

So: **record the simulator, lay the narration track under it in the edit, and
say so on screen.** The narration is the real artifact the backend produced for
that exact recap — not a re-record — and the manifest's segment timings come
from that same audio, so the cards line up with it frame for frame.

The caption, shown for its first 4 seconds and never removed from the
description:

> Narration is the app's own generated audio, laid under the capture: the Vega
> Virtual Device has no working audio sink. Cards are driven by the same
> timings.

Do not crop or soften this. A judge who spots undisclosed dubbing stops
believing the rest of the demo, and the limitation is Amazon's, not ours — it is
already written up as product feedback.

## The shape of the cut

Lead with the product working, not with how it works. The recap plays inside
the first minute; everything explaining it comes after a judge has already
seen it.

The spine is one claim — **the recap is different every time you ask** — and
one defence of it: **that is possible because nothing about it is pre-made,
and trustworthy because no model decides what mattered.**

Three minutes is the cap. This cut runs about 2:50.

| Time | On screen | Voiceover |
|---|---|---|
| 0:00–0:10 | Game list on the simulator. Disclosure caption up for its first 4s. | "You sit down forty minutes into a game. The score says 7–4 and you have no idea how it got there." |
| 0:10–0:18 | Cursor on the live row; the dimmed scheduled game visible below. | "Catch-Up 60 is one button on Fire TV. Live games first. Scheduled ones are shown but not offered — there is nothing to recap yet." |
| 0:18–1:08 | **Press Catch Up.** Cards play through, narration under. Footer counter visible. | *Silent.* Let the recap play. |
| 1:08–1:18 | Footer in close-up: `5 of 5 runs · 5 of 26 plays`. | "Five plays, and every run on the board accounted for. When sixty seconds will not fit everything, it says so rather than quietly dropping a run." |
| 1:18–1:40 | Back to the list. Press **Catch Up** on the *same game* again. New cards, new score. Cut the two headers side by side. | "Ask again a few minutes later and it is a different recap — because it is built from the live feed at the moment you press it. Nothing here is pre-made." |
| 1:40–2:05 | `src/engine/rank.py`, then a manifest's `engine` block. | "Which plays mattered is computed, never asked of a model. Baseball publishes how much each at-bat moved the game. Ranking is arithmetic on that number." |
| 2:05–2:25 | `narrate/guard.py`, then a terminal run showing `narrationSource: bedrock` and `guardViolations: []`. | "Claude rewrites the lines so they read well aloud. Then every number it wrote is checked against the engine's own figures. One unsupported digit and the recap falls back to the plain wording — and the manifest records that it did." |
| 2:25–2:45 | On the simulator: press the source switch to **AWS**, pick a game, recap arrives. | "The same app, pointed at the deployed version. Lambda, Bedrock, Polly, S3. Three seconds from press to recap." |
| 2:45–2:55 | Repo URL and the two GitHub links. | "Sixty seconds, built when you ask for it, and honest about what it left out." |

### If a live game is available on recording day

Swap the 1:18 shot for a genuinely live game and say "live right now" instead
of "a few minutes later". That is the stronger version. The replay clock below
exists so the shot is rehearsable and repeatable when no game is on — which,
in a three-day editing window, is most of the time.

## Capture runbook

Everything below is scripted so the take can be repeated without hunting for
the same game state.

**1. Start the device and both listeners.**

```bash
source ~/vega/env && vega virtual-device start --display-res=1920,1080
```

```bash
adb kill-server
```

The second one is not optional on a machine with Android tooling: an adb
server scanning emulator ports takes the VVD down mid-take (`FRICTION.md` 14).

**2. Serve a game that advances while you film.**

```bash
./run serve --port 8080 --replay 849832 --replay-rate 8 --replay-from 28
```

```bash
./run serve --port 8443 --https
```

The rate is not arbitrary. About 75 seconds of real time passes between the
two Catch Up presses — the recap itself runs ~50s, plus navigating back — and
the second recap has to be *visibly* different on camera, not subtly. On this
game:

| at-bat | score | inning | plays shown |
|---|---|---|---|
| 28 | 0–2 | top 4 | 7 |
| 31 | 0–2 | bottom 4 | 7 |
| 34 | 1–2 | top 5 | 6 |
| 37 | 3–2 | top 5 | 5 |

Three at-bats apart changes only the inning, which reads as a glitch rather
than a different recap. Nine apart changes the score by three runs, the
inning, and the number of cards. At 8 seconds an at-bat, 75 seconds of filming
covers exactly that: start at 28, press again around 37.

**3. Install and launch.**

`source ~/vega/env` has to be on this line. Without it the build gets most of
the way — JS bundle, sourcemap, Hermes, several minutes of healthy output —
and then the native step fails with `Vega CLI was not found in ambient
environment, nor could be found within $KEPLER_SDK_PATH (value = 'undefined')`.
Late enough to be expensive on a shoot day.

```bash
source ~/vega/env && cd tv && npm run build:release && cd .. && vega device install-app --device VirtualDevice --packagePath "$PWD/tv/build/aarch64-release/catchup60_aarch64.vpkg" && vega device launch-app --device VirtualDevice --appName com.pradeepkonda.catchup60.main
```

**4. Drive it.** The simulator takes no remote key presses (`FRICTION.md` 13),
so taps go through the console helper. Coordinates are in the 1920×1080 frame.

```bash
./tools/vvd tap 900 332
```

That is the top row. The source switch is the last row; take a screenshot
first and read its position off that, because it moves with the number of
games on the slate:

```bash
./tools/vvd shot /tmp/frame.png
```

**5. Pull the narration track for the edit.**

One track per press. For the first one, filmed at at-bat 28:

```bash
./run recap 849832 --as-of 28 --audio --voice polly-ssml --narrator bedrock --summary --out out/demo-manifest-28.json
```

The mp3 lands in `cache/work/849832-28/narration.mp3`. Align its start to the
first card appearing; the manifest's segment timings came from that same file,
so nothing else needs nudging.

**Use the `--as-of` you actually filmed.** Read it off the screen recording —
the app reports it, and the server log prints it — because a track from a
different cursor is a different script and will drift against the cards
immediately.

## Terminal shots worth having

For 1:40–2:25, these produce clean output to film rather than scrolling source:

```bash
./run recap 849832 --as-of 39 --narrator bedrock --summary
```

```bash
./.venv/bin/python -m pytest tests/ -q
```

Showing `narrationSource: bedrock` beside `guardViolations: []` makes the
guard point in one frame. `144 passed` makes the second.

## Tools, and the one setting that decides the quality

**Set the display before anything else.** The VVD renders 1920×1080. This Mac's
desktop is 1440×900 logical on a 2560×1600 Retina panel, so a 1920×1080 window
does not fit and macOS shows it shrunk — a recording then captures the shrunk
copy, and no amount of editing gets the detail back. Open System Settings →
Displays and pick the most-space scaled option (1920×1200 if the panel offers
it, which leaves room for the menu bar). Everything on screen becomes small for
the session; that is the trade, and it is worth it.

If no mode reaches 1920 wide, restart the device at a size that fits instead,
and accept 720p rather than filming a downscale:

```bash
vega virtual-device start --display-res=1280,720
```

**Capture: macOS Cmd+Shift+5**, set to *Record Selected Portion*, drawn tight
to the VVD window. Built in, no watermark, no account, and it records the
Retina backing store — so a 1920×1080 region arrives with more pixels than the
timeline needs and downscales cleanly. Turn the microphone **off**: the
narration is laid in afterwards and a live mic only adds room noise.

**OBS Studio** is the alternative, and earns its setup cost only if you want
the four app↔terminal switches done live as scene cuts rather than in the edit.
For a cut this short, separate clips are less work.

**Audio.** Three sources, none of them recorded off the screen:

| | |
|---|---|
| Narration | the app's own mp3, pulled per step 5 — the real artifact, not a re-record |
| Voiceover | QuickTime Player → File → New Audio Recording, one take per row of the table |
| Music | none. The rules forbid anything licensed and silence under a voiceover is fine |

**Edit: DaVinci Resolve** — free, no watermark, no export limit, handles 1080p
and multi-track audio. iMovie works if the cut stays simple, but it fights you
on more than two audio tracks, and this has three.

**Export** 1920×1080, H.264, 30fps. Under 3:00.

## What not to include

No team logos, no game footage, no commercial music — the rules forbid them and
we have no licence. Team identity stays as text. If a shot needs to avoid real
club names entirely, use the committed fixture game (Harbor Gulls at Cedar
Foxes), which is fictional for exactly this reason.

## Before uploading

- Disclosure caption legible for its full 4 seconds, and repeated in the
  description
- Under 3:00
- Public, not unlisted
- No credentials, account ids or presigned URLs visible in any terminal frame —
  check the AWS shot at 2:25 especially
