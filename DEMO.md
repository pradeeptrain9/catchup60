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

Most of this is mechanical and `tools/record` does it, because every step
below has been got wrong at least once here:

```bash
./tools/record preflight      # device, build, install, warm, servers, launch
./tools/record take take-1    # two presses in one continuous take -> .webm + .mp4
./tools/record narration 32   # the audio for one press
./tools/record narrate out/demo/take-1.mp4 32 40   # lay both under the take
```

`narrate` finds the offsets in the take itself rather than assuming them. What
matters is when the first *card* appears, not when the tap happened — between
them sits "Building your recap", which is one second warm and sixty cold. The
card's blue accent bar is bright where the loading screen is black, so one
brightness sample per tenth of a second finds the edge. It requires 1.5s of
sustained dark before counting a rise, because cards dip to black as they
change and a naive edge detector reported eight recaps in a take that had two.

Nothing else needs nudging afterwards: the manifest's segment timings came
from the same mp3, and its length matched what the device reported playing to
within 0.03 seconds (55.920 against 55.89, 48.216 against 48.19).

`preflight` takes about twelve minutes, almost all of it warming. That is the
step worth understanding rather than skipping: a cold recap spends **62
seconds** on "Building your recap", a warm one **1.0 second**, and warming has
to go through the server rather than `./run recap` — the CLI defaults to Polly
and Bedrock while the server uses Kokoro and the template narrator, which are
different cache keys. A CLI warm looks like it worked and buys nothing. Lower
the window with `CATCHUP60_DEMO_WARM=4` if you only need one press.

`take` waits for the device to report each recap finished rather than sleeping
a guess, so the second tap cannot land in the middle of a card. Measured on a
real run: press one at at-bat 32, press two at 40, cards 8 then 7, score 0-2
then 3-2. That is the beat the whole video is built around and it comes out of
one command.

The manual steps below are what `tools/record` runs, kept because when a take
goes wrong you need to do them one at a time.



Everything below is scripted so the take can be repeated without hunting for
the same game state.

**1. Start the device and both listeners.**

```bash
source ~/vega/env && ./tools/vvd up
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

## Tools

**Do not screen-record the simulator window.** The VVD renders 1920×1080 and
this Mac's desktop maxes out at 1680×1050 logical, so the window is shown
shrunk and a screen recording captures the shrunk copy. No edit recovers that.

Record the device framebuffer instead. The emulator console has
`screenrecord start` / `stop`, which writes true 1920×1080 VP9 regardless of
what the display is doing, and `tools/vvd` wraps it:

```bash
./tools/vvd rec start out/take-1.webm
# ... drive the app ...
./tools/vvd rec stop
```

Verified: 1920×1080, 30fps, VP9. Two limits, both from the console and
neither a problem here — **180 seconds maximum per take**, which is longer
than any single shot in the table, and **no audio**, which is moot because the
device has no audio sink at all (`FRICTION.md` 7) and narration is laid under
in the edit regardless.

Editors prefer H.264 to VP9:

```bash
ffmpeg -i out/take-1.webm -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p out/take-1.mp4
```

**Terminal shots** are the one thing still captured from the screen, with
**Cmd+Shift+5** → *Record Selected Portion*. Microphone **off**; voiceover is
recorded separately. Make the terminal font large before filming — the frames
at 1:40–2:25 exist to be read.

**OBS Studio** is not needed. Its value is live scene switching, and with the
app footage coming off the device rather than the screen there is nothing to
switch between while recording.

**Audio — three tracks, none captured from the screen:**

| | |
|---|---|
| Narration | the app's own mp3, pulled per step 5 — the real artifact, not a re-record |
| Voiceover | QuickTime Player → File → New Audio Recording, one take per table row |
| Music | none. Licensed audio is forbidden and silence under a voiceover is fine |

**Edit: DaVinci Resolve** — free, no watermark, no export limit, comfortable
with three audio tracks. iMovie fights you past two.

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
