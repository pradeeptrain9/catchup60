# Devpost fields — paste targets

Generated from SUBMISSION.md. Edit there, regenerate, never edit this by hand.

---

## Project name

```
Catch-Up 60
```

Currently entered as "Catchup60". The hyphenated form is what the app, the
repo and the video all say, and a name that does not match the product on
screen reads as carelessness.

---

## Elevator pitch  (184 characters, limit 200)

```
Join a live game late, press one button, get a 60-second recap of the game as it stands right now, then land at the live edge. Which plays mattered is computed, never asked of a model.
```

---

## Built with  (15 tags, limit 25)

```
Vega OS, React Native, Fire TV, Python, Amazon Bedrock, Claude, Amazon Polly, AWS Lambda, Amazon API Gateway, Amazon S3, AWS CloudFormation, MLB StatsAPI, Kokoro TTS, httpx, boto3
```

---

## Try it out links

```
https://github.com/pradeeptrain9/catchup60
https://github.com/pradeeptrain9/catchup-engine
https://github.com/toddrob99/MLB-StatsAPI/pull/173
```

The first is **private** and returns 404 to anyone who is not a collaborator.
Add the judges before submitting or that link is dead on the page:

```
chris-trag  knmeiss  giolaq  anishamalde  mosesroth  emersonsklar
```

Invitations expire after seven days, so this is a submission-day step, not an
earlier one.

---

## AWS Builder Mini Challenge — "Which AWS services did you incorporate and how?"

Answer: **Yes**.

```
Amazon Bedrock — Claude Haiku 4.5, called through bedrock-runtime Converse
with a us. inference profile. Its job is deliberately small: it rewords
sentences the engine has already written, and it is never asked which plays
mattered. Every number it returns is matched against the engine's payload
before anything is spoken; an unsupported figure costs one corrective retry
naming the offending numbers, then the deterministic narrator takes over and
the manifest records that it did. On a real run the model only ever
subtracted — "out on a sacrifice fly to right fielder Chase DeLauter" became
"out on a sacrifice fly to right".

Amazon Polly — neural engine, one SynthesizeSpeech call per recap with SSML
<mark> speech marks. The marks are the segment boundaries, so the TV cards are
synced to measured audio rather than to a word-count estimate. That estimate
measured 14% low on real speech and put a 63.94-second recap behind a
60-second promise; the system now trims the lowest-swing play until the
rendered audio fits, and reports the count in the manifest.

AWS Lambda — hosts the whole API. Python 3.12, 1024 MB, 60-second timeout
because a cold request fetches the feed, calls Bedrock through the guard's
retry, then calls Polly.

Amazon API Gateway (HTTP API) — the certificate is the point, not the routing.
Vega's media player refuses http:// outright and its fetch refuses the dev
server's self-signed cert, so local development runs two listeners on two
ports with the app rewriting URLs between them. API Gateway terminates a real
certificate and that entire workaround disappears.

Amazon S3 — narration mp3s, the manifest cache keyed on (gamePk, at-bat), and
the win-probability watcher's records. Private bucket; audio reaches the device
as a presigned GET, signed per response rather than stored, so a cached
manifest never carries an expired URL. S3 answers Range requests natively,
which is the other thing Vega's player insists on.

Amazon EventBridge — a scheduled rule ticks the Lambda every five minutes to
record whether MLB publishes win probability during a live game. This exists
because the laptop watcher kept dying silently, and a premise confirmed by a
record that stops when a lid closes is a premise still unconfirmed. 507 live
observations across three Championship Series games came from it and its
laptop counterpart.

Amazon CloudWatch Logs — the TV app posts what it rendered to a /log route, so
on-device behaviour is observable from a phone. Seven-day retention, because
Lambda creates the group with no expiry and logs eventually cost more than the
function.

AWS CloudFormation — the entire stack is one template deployed by one script
using only the AWS CLI. No SAM, no CDK: the friction log was long enough
without adding a toolchain to it.

AWS IAM — least-privilege execution role. Bedrock needs both the inference
profile ARN and the foundation-model ARN, because the profile invokes the
model on your behalf and a policy naming only the profile is denied at the
second hop.
```

---

## Open Source Mini Challenge

Answer: **Yes**.

**Contribution URL**
```
https://github.com/toddrob99/MLB-StatsAPI/pull/173
```

**Project Repository URL**
```
https://github.com/pradeeptrain9/catchup-engine
```

**GitHub Username**
```
pradeeptrain9
```

**Description — what you did, how it works, why it matters**
```
Two contributions.

1. catchup-engine (new MIT-licensed project). The ranking and packing engine
extracted from the app as a standalone Python library with no Amazon
dependency: given a game, it answers "which plays actually changed this, and
which of them fit in sixty seconds". It works because MLB publishes
homeTeamWinProbabilityAdded per at-bat, so ranking is arithmetic on a
published number rather than a judgement call. Selection then runs three
passes — rank under a per-half-inning cap, cover every run accounted per run
rather than per inning, then re-check the budget because coverage displaces.
It matters because "what did I miss" is not baseball-specific: nothing in the
engine is, beyond the name of one field, and anyone with a per-event
importance signal can rank a game the same way without adopting our stack.

2. toddrob99/MLB-StatsAPI PR #173 — timecode support for scoring plays.
linescore and boxscore_data already accepted a timecode, and the underlying
game endpoint already declared it, but game_scoring_plays did not: the scoring
plays were the one part of a game you could not ask about as of a moment. That
is where it is most useful, because "what scoring have I missed" is exactly
what someone joining a game late is asking. The change follows the existing
pattern — build the params dict, add the timecode only when one is given — so
the request is byte-for-byte unchanged for callers who do not pass one. Four
tests mock statsapi.get in the style of the existing suite, covering both
directions. Verified against game 849832's own game_timestamps: 0 scoring
plays, then 4, then 11, then 12 at the final out.
```

---

## [Optional] Feature Requests

```
1. vega device screenshot and vega device key — CRITICAL.
   The CLI has twenty-odd device subcommands and neither a screenshot nor a
   key press, so "verifying" a TV app means watching a window by eye. We found
   the VVD answers the Android emulator console, which has screenrecord
   screenshot, and built our own tooling on it. That tool is what caught a
   recap running 63.94 seconds against a 60-second promise — from across the
   room it looked correct. Without a way to capture the screen, a TV app is
   tested by recollection.

2. vega virtual-device start should exit non-zero when it fails — CRITICAL.
   It prints "Deadline reached (60s) but virtual device unresponsive." and
   returns 0. Every start && install && launch chain therefore runs against a
   device that is not there, and the first real failure arrives two commands
   later as "Device not found", which reads like operator error. An exit code
   is the one thing a script can act on, and this one is wrong in the failing
   direction.

3. vega device record — IMPORTANT.
   The emulator console can record the framebuffer at true 1920x1080, which is
   the only way we found to capture the device at its real resolution: a
   laptop whose desktop is smaller than 1920 wide shows the VVD window shrunk,
   and a screen recording captures the shrunk copy. Every entrant making a
   demo video hits this and nothing points to it.

4. Print the emulator console port in vega device list — IMPORTANT.
   The port is not fixed. We read 5556 for weeks and were right by accident —
   an unrelated Android emulator held 5554. Stopping it moved the VVD and
   every tool failed as an unanswered socket, which is indistinguishable from
   the device having died.

5. MLB StatsAPI: return 404 for a nonexistent gamePk — IMPORTANT.
   It returns 200 with populated placeholder fields, so a typo looks like a
   real game until something downstream behaves strangely.

6. MLB StatsAPI: document the timecode parameter and the feed's live latency —
   IMPORTANT. timecode makes any finished game replayable at any moment, which
   is enormously useful for testing and demos, and is undocumented. Separately,
   the docs describe the endpoint's shape and not its latency, so we had to
   spend a night measuring whether win probability publishes during a game.
   It does, at the live edge. One sentence would have saved that.

7. Amazon Polly: accept SSML speech marks on the generative engine —
   NICE-TO-HAVE. Generative rejects them, so we pinned the deployed path to
   neural. Speech marks are how we sync cards to audio.
```

---

## [Optional] Friction Log

**URL**
```
https://github.com/pradeeptrain9/catchup60/blob/main/FRICTION.md
```

16 entries, each written while the problem was in front of us rather than
reconstructed afterwards, with task attempted, steps, expected vs actual,
severity, workaround and an actionable suggestion.

> The app repo is private. This link 404s for anyone who is not a
> collaborator, so the judges have to be added before it is submitted.

---

## [Optional] Project Testing Link

**URL**
```
https://vbww5kcz7l.execute-api.us-east-1.amazonaws.com
```

**Testing instructions**
```
The deployed API is public and needs no credentials. Verified answering at the
time of submission.

  curl https://vbww5kcz7l.execute-api.us-east-1.amazonaws.com/playable

Lists today's games with a playable flag.

  curl "https://vbww5kcz7l.execute-api.us-east-1.amazonaws.com/recap/synthetic"

Builds a full recap of a fictional committed fixture game — no live game
needed, works any day of the year. The response is the manifest the TV app
consumes: timed segments, a presigned mp3 URL, and the honesty fields
(narrationSource, narrationFallback, guardViolations, limitedBy,
runsExplained, runsTotal, trimmedAfterSynthesis).

  curl ".../recap/776579"          a real game, latest at-bat
  curl ".../recap/776579?as_of=40" the same game as it stood at at-bat 40

Press the same gamePk twice with different as_of values and the recap differs:
that is the central claim of the project, testable from a terminal.

  curl ".../watch/849809"

The win-probability measurement: 419 live observations of an NLCS game,
reported as one verdict.

To run it locally with no AWS account at all:

  git clone <repo> && cd catchup60 && ./setup.sh
  ./run doctor
  ./run synthetic

Kokoro runs the speech locally and the fixture game needs no network.
```

---

## Feedback Question 1 — which tools, APIs and SDKs, and for what?

```
Vega SDK + Vega Virtual Device + React Native for Vega — the Fire TV app and
  every frame of testing. No physical device was used at any point.
Amazon Bedrock (bedrock-runtime Converse, Claude Haiku 4.5) — rewording
  narration lines, under a numeric guard.
Amazon Polly (neural, SSML speech marks) — speech, and the per-segment
  timings the TV cards are synced to.
AWS Lambda, API Gateway, S3, CloudFormation, EventBridge, CloudWatch, IAM —
  the deployed backend and the scheduled win-probability watcher.
boto3 — every AWS call.
MLB StatsAPI — schedule, live feed, win probability. The whole ranking signal.
Kokoro ONNX TTS — local speech, so the repo runs with no AWS account.
httpx — the only bundled dependency in the Lambda package.
```

---

## Feedback Question 2 — what worked well?

```
Vega Virtual Device: that it exists at all, and on both Intel and Apple
silicon, is the single reason this project was possible without hardware. One
installer, no allowlist, no approval.

MLB StatsAPI: public, no key, no auth, no rate limit encountered. The fields
parameter is excellent and underused — it cut a winProbability response from
1.08 MB to 39 KB, a 27x reduction that is the difference between polling a
live game comfortably and not. homeTeamWinProbabilityAdded per at-bat is
exactly the right primitive and we have not found it published this cleanly
anywhere else. It is also published live, at the live edge, which we measured.

Bedrock Converse: once reachable, completely unremarkable in the best sense.
Same shape across models, and taking the Anthropic SDK out removed 4.8 MB of
compiled dependencies from the Lambda package.

Polly: one call returns audio and speech marks together, so timing comes from
the synthesizer rather than from an estimate. That is the right API shape.

CloudFormation + the AWS CLI: the whole stack is one template and one script.
No extra toolchain to learn or to document.
```

---

## Feedback Question 3 — what needs work?

```
Vega CLI has no screenshot and no key injection. See Feature Requests 1-4;
this was the largest single cost in the project.

Key injection on the emulator console is accepted, answered OK, and delivered
nowhere. Several minutes went into believing the app had a focus bug that did
not exist. Either reject the command or route it.

virtual-device start exits 0 on failure, and the device dies on its own,
repeatedly, with nothing written anywhere saying that it did — not to the log,
not to stdout. Hours went into this and the cause is still not known, because
there is no evidence to reason from.

Vega's media player refuses http:// and its fetch refuses the self-signed cert
the media pipeline accepts. Two listeners on two ports with URL rewriting
between them is a lot of code to exist because two components in the same OS
disagree about a certificate.

Bedrock model access took four gates, each reporting failure in a way that
looked like one of the others. The last was the worst: the Anthropic SDK's
Bedrock client talks to a gateway entitled separately, which returned 403 "is
not available for this account" — Bedrock's own phrase for an ungranted model
— for every model, while bedrock-runtime Converse answered on the same
credentials in the same second. We re-checked the gate we had just cleared.

Service Quotas showed an applied value of 0 against a default of 5,000,000 for
a model, with "no requests found", which is not a state the console explains.

aws login sessions need botocore[crt], and without it get_credentials() raises
instead of returning None. An availability probe that can raise defeats its own
purpose; ours took down the CLI until it was wrapped.

Polly's generative engine rejects SSML speech marks with no indication in the
error that the engine is the reason.

MLB StatsAPI returns 200 for a nonexistent gamePk, and winProbability 404s
identically for a scheduled game and a bad id — one means "come back after
first pitch" and the other means "you sent the wrong id".
```

---

## Feedback Question 4 — onboarding, zero to hello world?

```
Vega: genuinely good. One curl-pipe installer, source ~/vega/env, vega project
generate --template helloWorld, and a running app on a virtual device. Under
an hour with no hardware and no approval queue. The cliff is immediately after
hello world: the moment you want to verify what is on screen, the tooling
stops and you are writing your own.

MLB StatsAPI: minutes. Public, no key, no signup. Paste a URL in a browser and
the data is there.

Bedrock: the slowest of everything here, and the only one where the obstacle
was access rather than code. Four gates, and the final one was a client
library choice rather than a permission. The call itself, once reachable, took
one function.

Polly: one call to working audio.

Lambda + API Gateway + CloudFormation: one template, one script, one deploy.
The only surprise was that CloudFormation updates the function's code
*location* and not its code, so an unchanged S3 key means the old zip keeps
serving — a deploy that silently does nothing.
```

---

## Feedback Question 5 — would you build with these again?

```
Yes.

Vega and the Virtual Device, without reservation, with one condition: that
screenshot and input capture arrive. Everything about the platform was
workable except seeing what it was doing, and that single gap cost more than
every other problem in the project combined. The device is pleasant to build
for, React Native is the right choice for it, and the virtual device removing
the hardware requirement is the reason an independent entrant could attempt
this at all.

Bedrock and Polly, yes. The constrained use we made of Bedrock — rewording
only, every number checked — is a pattern we would reach for again, and
Converse is the right API. Polly returning audio and speech marks in one call
is what made sixty seconds enforceable rather than aspirational.

MLB StatsAPI, emphatically. It is the most generous public sports data we
found, and the per-at-bat win probability is the entire reason this product
can be computed rather than guessed.
```

---

## Which AI tools did you leverage?

```
Claude Code (Claude Opus 5) throughout: engine design, the Vega app, the
deployed stack, the test suite, and the tooling built to drive and photograph
the virtual device. Used as a working collaborator with everything verified
against real output rather than accepted — several of the entries in the
friction log are mistakes caught by running the thing and reading what came
back.
```

---

## The three attestation checkboxes

Age of majority, eligible jurisdiction, not an employee of the promotion
entities. These are legal statements about you personally — tick them
yourself; they are not mine to answer.

---

## About the project

Everything below this line goes in the "About the project" box.

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
  with nothing backfilled at the whistle
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

- **App repo** — [pradeeptrain9/catchup60](https://github.com/pradeeptrain9/catchup60)
- **Open-source project (MIT)** — [pradeeptrain9/catchup-engine](https://github.com/pradeeptrain9/catchup-engine)
- **Upstream contribution** — [toddrob99/MLB-StatsAPI#173](https://github.com/toddrob99/MLB-StatsAPI/pull/173)
