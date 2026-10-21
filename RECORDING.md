# Recording script — one pass, screen and mic together

You speak live while you record. Nothing is laid under afterwards, so there is
no editing step and no second audio track to line up.

**Target 2:50.** Devpost caps at 3:00 and a video that runs over is a video
nobody finishes.

---

## Before you hit record

```bash
cd ~/Desktop/project/catchup60
./tools/record preflight
```

Wait for `ready.` It restarts the replay clock at at-bat 28, which is the only
thing in this setup that goes stale: a server left running from an earlier
session has a clock thousands of at-bats past the end of the game, and the
screen still says "In Progress (replay)" while being useless.

Then, in a **second terminal tab**, with a large font, run this and leave the
output on screen:

```bash
./tools/shot rank
```

And in a **third tab**:

```bash
./tools/shot guard
```

You will switch tabs on camera rather than type anything.

**Check before recording:**

- Simulator window fully visible, nothing overlapping it
- Terminal font large enough to read on a phone
- Notifications off (Do Not Disturb)
- Mic is the one you mean — test it, 10 seconds, play it back
- No credentials, account numbers or presigned URLs on any screen

---

## One thing you must say

The simulator has **no audio output at all**. The app generates spoken
narration — Polly on the deployed path, Kokoro locally — and you cannot hear
it in this recording because the device has nowhere to play it.

Say so, once, in the line at 0:22. Do not let a viewer assume the silence
means there is no narration, and do not imply you are hearing something you
are not.

---

## The script

Each row is one continuous stretch. The right column is what you say — read it
through twice before recording so it sounds spoken rather than read.

| Time | On screen | Say |
|---|---|---|
| **0:00–0:12** | Game list, cursor on the live row | "You sit down forty minutes into a game. The score says seven–four, and you have no idea how it got there. Your choices are to start at the live edge and be lost, or scrub backwards through the game you were trying to skip." |
| **0:12–0:22** | Still the list. Let the dimmed row be visible | "This is Catch-Up 60 on Fire TV. Live games first. Scheduled ones are shown but not offered — there is nothing to recap yet." |
| **0:22–0:30** | Hover the live row, about to press | "One note: this is the Vega simulator, and it has no audio output. The app does generate spoken narration. You just cannot hear it here, so I will talk you through." |
| **0:30–0:40** | **Press Catch Up.** Loading, then first card | "Press Catch Up, and it builds a recap of the game as it stands right now." |
| **0:40–1:20** | Cards play. Let them run. | *Mostly quiet — let it play.* Around the third card: "Every one of these is a play that actually moved the game. Not a highlight reel — highlights are cut after a game ends. This is what you missed, in the order it happened." |
| **1:20–1:32** | Footer in shot: `5 of 5 runs · 5 of 27 plays` | "Five plays out of twenty-seven. And every run on the board is accounted for. When sixty seconds will not fit everything, it says so, instead of quietly dropping a run." |
| **1:32–1:55** | End card → **Catch up again** | "Now watch what happens if I ask again. Minutes have passed in the game." *(press)* "Different score. Different inning. Different plays. It is built at the moment you press it — nothing here is pre-made." |
| **1:55–2:15** | **Tab 2** — `tools/shot rank` output | "Which plays mattered is computed, never asked of a model. Baseball publishes how much each at-bat moved the win probability. Ranking is arithmetic on that number — that is the whole rule, on one screen." |
| **2:15–2:35** | **Tab 3** — `tools/shot guard` output | "A model does rewrite the lines so they read well aloud. Then every number it wrote is checked against the engine's own figures. One unsupported digit and the recap falls back to the plain wording — and the manifest records that it did. These tests hold that." |
| **2:35–2:48** | Back to simulator. **Tap the Source row** → AWS, list reloads | "Same app, pointed at the deployed stack. Lambda, Bedrock, Polly, S3. The list reloads from AWS — the replayed game is gone, because the deployed version has no replay server." |
| **2:48–2:56** | Repo links on screen | "Sixty seconds, built when you ask for it, and honest about what it left out. Thanks for watching." |

---

## Taps, if you drive it from the terminal

You can press with the remote in the simulator window, or tap from a terminal
tab off camera. Coordinates are in the 1600×900 frame the device is running:

```bash
./tools/vvd tap 800 486    # top game row            (verified)
./tools/vvd tap 550 613    # "Catch up again"        (verified)
./tools/vvd tap 1072 613   # "Other games"           (verified)
./tools/vvd tap 800 318    # the Source row          (measured, not tapped)
```

These were measured off the running 1600x900 frame, not scaled from the
1920x1080 numbers — the layout uses fixed padding, so scaling coordinates
between resolutions gives answers that are wrong by forty pixels and land
between rows.

Take a screenshot first and read the positions off it if the slate has
changed — the game rows move with the day's schedule, though the Source row
does not:

```bash
./tools/vvd shot /tmp/frame.png
```

---

## If a take goes wrong

Stop, run `./tools/record preflight` again, start over. It takes about a
minute once the cache is warm, and the replay clock resets to at-bat 28 so the
second take looks like the first.

The virtual device has died unprompted several times during this project. If
the screen freezes, that is what happened — `./tools/vvd up 1600,900` brings
it back, then preflight.

---

## Before uploading

- Under 3:00
- The audio-output line at 0:22 is in and audible
- No team logos, no broadcast footage, no music — the rules forbid them and we
  have no licence. Text team names only.
- No credentials, account ids or presigned URLs in any frame
- Public, not unlisted
