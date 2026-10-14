# Catch-Up 60 — submission

**Track:** Fire TV · **Categories:** Sports, AI-enhanced viewing
**Mini-challenges:** AWS Builder, Open Source

---

## Inspiration

You sit down forty minutes into a game. The score says 7-4 and you have no
idea how it got there. Your options are to start at the live edge and spend
twenty minutes lost, or scrub backwards through the game you were trying to
skip.

Highlight reels do not fix this. A highlight reel is the best plays of a
*finished* game, cut afterwards, ordered for drama. A late viewer needs
something else: the plays that explain *this* score, in the order they
happened, ending at the present moment — and available mid-game, not tomorrow.

Nobody builds that, because it has to be made on demand and it has to be
right. Those two together are the interesting problem.

## What it does

One button. Sixty seconds. Then you are watching live.

The app lists what is on, live games first. You press **Catch Up** and get a
card per play that actually changed the game, in chronological order, read
aloud, ending with the current score and "back to live."

Two things distinguish it from a recap someone could have pre-made:

**It is built for the moment you ask.** Press Catch Up in the fourth and you
get the game as of the fourth. Press it again in the sixth and the recap is
*different*, because two innings happened. Verified on device — same game, two
presses: at-bat 39 top of the 5th, then at-bat 43 bottom of the 5th.

**It reports what it left out.** Sixty seconds does not always fit everything.
When it does not, the screen says so — `5 of 5 runs · 5 of 26 plays` — and the
manifest carries `limitedBy`, `runsExplained`, `runsTotal`,
`trimmedAfterSynthesis`, `narrationSource` and `narrationFallback`. A recap
that silently drops a run is worse than one that admits it.

## How we built it

**The one rule: which plays mattered is computed, never asked of a model.**

MLB StatsAPI publishes `homeTeamWinProbabilityAdded` per at-bat — how much
that play moved each team's win chance. So ranking is sorting. There is no
prompt and nothing to hallucinate.

**That signal is published live, and we measured it rather than assuming it.**
The whole design rests on the league publishing those per-play numbers *during*
a game rather than backfilling them at the final out, and that had only ever
been confirmed on finished games. So two watchers poll a game and record one
observation per tick — one on a laptop every sixty seconds, one on a scheduled
Lambda every five minutes, because the laptop one kept dying and a premise
confirmed by a record that stops when a lid closes is a premise still
unconfirmed. Their records merge; neither is complete alone. NLCS game 849809,
first pitch to final out:

| | |
|---|---|
| live observations | 419 |
| plays published | 1 → 70, growing 69 separate times |
| largest single jump | 2 plays |
| lag behind the live feed | **0 at-bats**, 1 at the very edge |
| **published after the final out** | **0** |
| errors while live | none |

A feed that backfilled would show one jump from nothing to the whole game at
the whistle. This is the exact opposite twice over: 69 increments of one or
two plays during the game, and then *nothing* added afterwards — the last live
tick and the first Final tick, sixty-two seconds apart, both read 70 plays.
The signal was already complete when the game ended.

Each watcher reaches the same verdict on its own — 378 live observations and
67 increments from the laptop, 41 and 34 from the five-minute Lambda — so the
answer does not depend on the merge, and the merged figure is quoted only
because it is the complete record.

Nor does it depend on the game. The watcher ran over the next two Championship
Series games as well, and all three agree:

| game | live observations | plays published | increments | lag |
|---|---|---|---|---|
| 849809 LAD at MIL | 419 | 1 → 70 | 69 | 0–1 |
| 849812 LAD at MIL | 46 | 1 → 75 | 37 | 0–1 |
| 849820 CLE at TB | 42 | 1 → 77 | 35 | 0–1 |

Three games, two series, 507 live observations, 141 separate increments, and a
lag that never exceeded one at-bat in any of them.

And it is not one game. The same watchers ran across two more Championship
Series games that night, and both returned the same verdict:

| game | live observations | plays published | increments | lag |
|---|---|---|---|---|
| 849809 LAD @ MIL | 419 | 1 → 70 | 69 | 0–1 |
| 849812 LAD @ MIL | 46 | 1 → 75 | 37 | 0–1 |
| 849820 CLE @ TB | 42 | 1 → 77 | 35 | 0–1 |

Three games, two series, no errors while live, and the lag never grew past one
at-bat in any of them.

A lag of zero is the part that matters for the product: the ranking signal
sits *at* the live edge, so a recap built at any moment is complete up to the
at-bat in progress. (One increment was −1, a play withdrawn — most likely a
call overturned on review.)

The verdict is one command, `./run verdict 849809 --url <api>`, and it reports
three outcomes rather than two: a watcher that has not yet seen a live tick
says so, instead of returning the same "no" it would return for a feed that
stood still all game. The record is in the repo, not in a recollection.

This is not caution for its own sake. A model asked which plays mattered
answers fluently and sometimes wrongly — the game turned on a groundout in the
second — and nothing downstream can detect it, because correct and incorrect
output are both well-formed prose.

So the model does a smaller job: it rewords sentences the engine already
wrote. On a real run it only ever subtracted — "out on a sacrifice fly to
right fielder Chase DeLauter" became "out on a sacrifice fly to right", season
totals and a repeated half-inning header went. Every number left was one the
engine produced.

And that is enforced, not trusted. Before synthesis, every number in the
model's text is matched against the engine's payload. An unsupported figure
triggers one corrective retry naming the offending numbers, then falls back to
the deterministic narrator with the reason recorded in the manifest. Speech is
strictly downstream of the guard, so audio can never say a figure the text was
not allowed to.

**The packer is where the real work is.** Taking the top seven plays produces
a recap where the score jumps 2-0 to 4-0 across a strikeout. So selection runs
three passes: rank under a per-half-inning cap that widens only as needed;
then cover every run, accounted per *run* rather than per inning, deliberately
reaching below the noise floor when a dull play drove in two; then re-check
the budget, because coverage displaces. `limitedBy` is decided after all three
passes — reporting the constraint the first pass hit is a convincing lie.

**Sixty seconds is enforced against rendered audio.** The estimator measured
14% low on real speech, which put a 63.94-second recap behind a 60-second
promise on the first device run. Now the system measures what the synthesizer
returned and drops the lowest-swing play until it fits, reporting the count.

**Stack:** Python engine, no framework. React Native on Vega OS for the TV app.
Amazon Bedrock (Claude Haiku 4.5) for phrasing, Amazon Polly for speech,
Lambda + API Gateway + S3 deployed. Kokoro ONNX as a local zero-credential
fallback so the repo runs with no AWS account at all.

The app can be pointed at either backend from a row on the home screen, and
that row is scaffolding rather than a feature. It exists so the deployed stack
can be shown working on a television instead of asserted in a paragraph: press
it and the list repopulates from Lambda, with the replayed game gone because
the deployed stack has no replay server. A viewer has no idea what "Local
server" means and no basis on which to choose, so in a real product this is a
build flag and not a row — one that is currently taking a slot on the home
screen away from an actual game.

## Challenges

**The device could not be seen or driven.** The Vega CLI has no screenshot and
no key injection, so "verifying" meant watching a window. The VVD turned out
to speak the Android emulator console protocol, which has `screenrecord
screenshot`. Key injection there is accepted, answered `OK`, and delivered
nowhere — minutes went into chasing a focus bug that did not exist. `event
mouse` routes, so the app is driven by touch taps. That tool is what caught
the 63.94-second overrun; from across the room it looks like a correct recap.

**Audio on Vega.** The media player refuses `http://` outright and `fetch`
refuses the dev server's self-signed cert that the media pipeline accepts — so
local development runs two listeners on two ports with the app rewriting URLs
between them. Deploying deletes that entirely: API Gateway terminates a real
certificate and S3 answers Range requests natively.

**Four gates to a first Bedrock call,** each reporting failure in a way that
looked like one of the others. The last was not quota or entitlement: the
Anthropic SDK's Bedrock client talks to a gateway entitled separately, which
returned 403 for every model while `bedrock-runtime converse` answered on the
same credentials in the same second. Switching to converse also took 4.8MB out
of the Lambda package.

## Accomplishments

- A recap that is **different every time you ask**, proven on device
- **The premise is measured, not assumed** — 507 live observations across
  three Championship Series games show the ranking signal published at the
  live edge, never more than one at-bat behind, growing 141 separate times,
  with nothing backfilled at the whistle —
  and two more Championship Series games return the same verdict
- **The guard has never been bypassed** — every path is checked, including the
  template narrator that cannot fail it, so it cannot rot
- **Honest self-reporting** throughout: the manifest says which narrator spoke,
  why a fallback happened, what was trimmed, and how many runs went unexplained
- **Sixty seconds means sixty seconds**, enforced against measured audio
- Runs with **no AWS account** — Kokoro locally, the fixture game offline
- **16 friction log entries**, each written while the problem was in front of us

## What we learned

Estimates drift and measurements do not. Three separate bugs here were the
same bug: trusting a computed guess over an observed value — the speech-rate
estimate, `limitedBy` computed too early, and a cached fallback that outlived
its own fix.

Error messages that describe the wrong layer cost more than missing ones. The
Bedrock gateway saying "not available for this account" — Bedrock's own phrase
for an ungranted model — sent us to re-check the gate we had just cleared.

And a device you cannot photograph is a device you have not tested.

## What's next

Other sports. Nothing in the engine is baseball-specific beyond the name of
one field, so the same arithmetic ranks a hockey or basketball game the moment
a comparable per-event signal exists.

A "what did I miss" prompt that follows you into a second game, since the
viewer with two games on is the one this helps most.

And lower latency on the first press. The recap is built on demand, which is
the point, but the engine already knows the game advanced before anyone asks —
warming the next at-bat's recap against the watcher's own tick would make the
button feel instant without making it any less live.

## Links

| | |
|---|---|
| App repo | `https://github.com/pradeeptrain9/catchup60` |
| Open-source project (MIT) | `https://github.com/pradeeptrain9/catchup-engine` |
| Upstream contribution | `https://github.com/toddrob99/MLB-StatsAPI/pull/173` |

## Built with

`vega-os` `react-native` `fire-tv` `python` `amazon-bedrock` `claude`
`amazon-polly` `aws-lambda` `api-gateway` `amazon-s3` `cloudformation`
`mlb-statsapi` `kokoro-tts` `httpx`
