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

## Shot list

| Time | Shot | Point being made |
|---|---|---|
| 0:00–0:12 | Split screen: simulator on the left, terminal playing the mp3 on the right, waveform visible | The audio is ours and it is the same track. Carries the disclosure caption. |
| 0:12–0:22 | Game list on the simulator: a live or final game, a scheduled one dimmed, the fixture | Real schedule data, and scheduled games are shown but not offered |
| 0:22–1:20 | Press **Catch Up**. The recap plays: card per play, progress bar, run coverage in the footer | The product. Narration under it. |
| 1:20–1:35 | Terminal: `./run recap <pk> --as-of N --summary` on the same game at two cursors, side by side | The recap is rebuilt from the feed, not canned |
| 1:35–2:00 | `src/engine/rank.py` and `pack.py` on screen while explaining win-probability ranking and run coverage | The engine computes importance; the model never decides it |
| 2:00–2:25 | `narrate/guard.py` plus the failing-guard test | Every spoken figure is checked against engine output |
| 2:25–2:50 | `pytest` green, then the `limitedBy` / `runsExplained` fields in a manifest | It reports its own shortfalls |

## Producing the assets

```bash
./run serve --port 8080
./run serve --port 8443 --https
```

```bash
./run recap 849832 --audio --summary --out demo-manifest.json
```

The mp3 lands in `cache/work/<gamePk>-latest/narration.mp3`. That is the file to
lay under the capture. Its length is the manifest's `totalSeconds`, so align the
start of the audio to the first card appearing and nothing else needs nudging.

## What not to include

No team logos, no game footage, no commercial music — the rules forbid them and
we have no licence. Team identity stays as text. If a shot needs to avoid real
club names entirely, use the committed fixture game (Harbor Gulls at Cedar
Foxes), which is fictional for exactly this reason.
