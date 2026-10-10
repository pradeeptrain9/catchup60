# Friction log

Kept as it happened, not reconstructed afterwards.

---

## 1. Vega prerequisites read as "you need the hardware"

**Task:** Decide whether the Fire TV track was enterable with no Amazon device
before committing to it.

**Steps:** Read *Getting started with Vega OS development*, then the Vega FAQ in
the developer community.

**Expected:** A clear statement near the top of the prerequisites that a
simulator ships with the SDK.

**What happened:** The prerequisites list reads:

> * Mac or Linux machine (Windows and WSL are not currently supported)
> * Visual Studio Code (VS Code) installed
> * Fire TV Stick 4K Select for testing on real hardware
>   (If you don't have the Fire TV Stick 4K Select handy, you can use the Vega
>   Virtual Device (VVD) that is installed with the SDK...)

The device is a top-level prerequisite bullet and the VVD is a parenthetical
inside it. Skimming the list — which is what you do when deciding whether you
can enter at all — the honest read is "a Fire TV Stick is required." The
unambiguous answer was in a community FAQ post, not the getting-started guide.

**Severity:** Important. This is the first page a prospective entrant reads, and
the wrong read loses the entrant, not just the hour.

**Workaround:** Found the FAQ, which states plainly that the VVD "is a virtual
development platform, also known as a simulator or emulator," and that the SDK
supports Macs (Intel and M-series).

**Suggestion:** Promote the VVD to its own prerequisite bullet and demote the
stick: "Vega Virtual Device (installed with the SDK) — or a Fire TV Stick 4K
Select to test on real hardware." One line, and the track reads as open to
anyone with a Mac.

---

## 2. MLB StatsAPI: `fields` filtering is undocumented and worth 27x

**Task:** Pull per-play win probability for a full game inside a Lambda budget.

**Steps:** `GET /api/v1/game/{gamePk}/winProbability`.

**Expected:** A response proportional to the ~80 plays in a game.

**What happened:** 1,076,990 bytes for 79 plays — most of it per-play
`playEvents`, `hotColdZones` and `splits` the caller never asked for. Adding the
API's `fields` parameter with an explicit name list brought the same 79 plays
down to 39,863 bytes. **27x smaller**, which is the difference between a feed you
can poll during a live game and one you cannot.

The `fields` parameter is not mentioned on the endpoint, and its semantics are
not obvious: it is a flat list of field *names*, not paths, so a name is kept
wherever it appears in the tree. That had to be established by experiment.

**Severity:** Important for anyone building on this feed; harmless if you only
ever fetch one game by hand.

**Workaround:** `src/mlb.py` keeps the field lists as named constants with the
measurement in a comment, so nobody re-derives it.

**Suggestion:** Document `fields` on the endpoints where the payload is large,
with one worked example. The feature already exists and is excellent; it is just
invisible.

---

## 3. `schedule` silently omits team abbreviations

**Task:** Show "PHI @ NYM" in a game list.

**Steps:** `GET /api/v1/schedule?sportId=1&date=...`, read
`teams.away.team.abbreviation`.

**Expected:** Either the abbreviation, or an error saying it needs hydrating.

**What happened:** `KeyError: 'abbreviation'`. The team object in a schedule
response carries `id` and `name` but not `abbreviation`, and asking for it in
`fields` does not add it — `fields` can only narrow what is already there. No
error, no warning; the key is simply absent.

**Severity:** Minor. Cost about ten minutes.

**Workaround:** A second call to `/api/v1.1/game/{pk}/feed/live`, narrowed with
`fields` to 403 bytes, which carries the abbreviations and the game status
together.

**Suggestion:** Either include `abbreviation` in the schedule's team object, or
name it in the `hydrate` documentation for that endpoint.

---

## 4. Ring: the docs and the hackathon rules disagree on whether a device is required

**Task:** Evaluate the Ring track before choosing Fire TV. Recorded because it
shaped the decision.

**What happened:** *Getting Started with Ring Developer Experience* lists under
Requirements: "At least one Ring device for testing (camera or doorbell)". The
hackathon rules say a physical Ring device is not required. Both are arguably
true — the same docs describe a "Sandbox Environment with synthetic Ring devices
and events" and "No rate limits apply in sandbox" — but the Requirements section
does not mention the sandbox at all, and the sandbox is defined only in a
terminology table much further down.

Combined with developer registration requiring identity verification and
business details of unstated duration, the track read as too risky for a
13-day window with no hardware. That may have cost the track an entrant.

**Severity:** Important.

**Suggestion:** Add the sandbox to the Requirements section as the no-hardware
path, and publish the expected turnaround for developer registration. Both facts
are what someone deciding between tracks actually needs.

---

## 5. `winProbability` 404s on a scheduled game, with a message that reads like a bad id

**Task:** Handle a viewer opening the app before first pitch.

**Steps:** `GET /api/v1/game/849831/winProbability` on a game in `Scheduled`
state.

**Expected:** `200` with an empty array. There are no plays yet; that is a
normal, expected state, not an error.

**What happened:** `404` with

> ```
> {"messageNumber":2,"message":"Game data couldn't be found",...}
> ```

which is byte-for-byte what a nonexistent gamePk returns. So the two cases a
client most needs to tell apart — "come back after the first pitch" and "your
game id is wrong" — are indistinguishable from the response.

**Severity:** Important. Pregame is not an edge case; it is the state every game
is in for most of the day, and a naive client shows an error screen during it.

**Workaround:** Ask the cheap `feed/live` endpoint first (403 bytes with
`fields`) and branch on `abstractGameState` before touching the play feed. That
turned out to be the right shape anyway — the same call carries the current
at-bat index, which became the cache key.

**Suggestion:** Return `200` with `[]` for a game that exists but has no plays.
Failing that, use a distinct `messageNumber` for "game exists, no data yet", so
clients can tell the two apart without a second request.

---

## 6. A nonexistent gamePk returns `200` with fully populated placeholder data

**Task:** Validate a gamePk before building a recap.

**Steps:** `GET /api/v1.1/game/12345/feed/live`.

**Expected:** `404`.

**What happened:** `200`, with `gameData` populated well enough to look real:

> ```
> "status": {"abstractGameState": "Other", "detailedState": "Unknown",
>            "codedGameState": "X", "statusCode": "X"}
> "teams": {"away": {"id": 0, "link": "/api/v1/teams/0"},
>           "home": {"id": 0, "link": "/api/v1/teams/0"}}
> ```

`gameData` also carries `game`, `datetime`, `players`, `weather`, `gameInfo`,
`flags`, `alerts` and `probablePitchers` keys, so an emptiness check on
`gameData` does not catch it. Our first attempt at a guard checked exactly that
and let the placeholder through — the CLI reported "AWY @ HOM is unknown — no
plays yet", sending the reader hunting for a game-state problem instead of a
typo.

The only unambiguous sentinel is `teams.away.id == 0`.

**Severity:** Minor, but the failure is misleading rather than loud, which is
the expensive kind.

**Workaround:** Treat a team id of `0` as "no such game".

**Suggestion:** Return `404` for an unknown gamePk. If the `200` is load-bearing
for some other consumer, document `codedGameState: "X"` as the sentinel.

---

## 7. The Vega Virtual Device cannot play audio at all

**Task:** Play a narration track in a Vega app and animate UI against it.

**Steps:** `AudioPlayer` from `@amazon-devices/react-native-w3cmedia`:
`setMediaControlFocus(componentInstance)`, `initialize()`, set `src` to an
https mp3, `play()`.

**Expected:** Audio, and a `currentTime` that advances.

**What happened:** The media element reaches `playing` — the full event sequence
`loadstart → play → waiting → progress → loadedmetadata → loadeddata → canplay
→ playing` arrives — and then fires `error` with code 4
(`MEDIA_ERR_SRC_NOT_SUPPORTED`). `currentTime` reads `NaN`, `duration` reads
`NaN`, `readyState` is 3 while `networkState` is 0.

Error code 4 says "your content is unsupported", so the first day went into
the content: re-encoded wav to mp3, then 24 kHz to 48 kHz, mono to stereo,
added HTTP Range support, checked `canPlayType` for every audio type. The
device log says what is actually wrong:

> ```
> leaudiosink, bkvleaudiosink.c, 537, bkv_leaudiosink_prepare,
>   Failed to create streamhelper object
> sink not negotiated.
> Audio Stream handle not available
> ```

The audio **sink** never initializes. There is no codec error anywhere in the
log. A plain mp3 from a public, publicly-trusted origin fails identically, which
rules out our content and our certificate.

**Severity:** Critical for any app with audio. Audio simply cannot be
exercised on the simulator, and the error code actively points away from the
cause — a developer with no physical device will spend their time re-encoding
assets that were always fine.

**Workaround:** Drive UI animation from our own timeline rather than from
`currentTime`, and let audio attach opportunistically where the hardware
supports it. This turned out to be better design regardless, but it was forced
rather than chosen.

**Suggestion:** Two things, in order of value. First, surface a distinct error
when the sink fails to initialize rather than `MEDIA_ERR_SRC_NOT_SUPPORTED` —
the current code sends developers to debug the one thing that is not broken.
Second, state plainly in the Vega Virtual Device documentation that audio output
is unavailable there. One sentence in the VVD page would have saved a day.

---

## 8. Media requires https; `fetch` rejects the certificate that media accepts

**Task:** Serve a manifest and an audio file from a development server on the
host Mac to an app on the Vega Virtual Device.

**What happened:** Three separate constraints, discovered one at a time.

1. The host is not on loopback from the device. `localhost` and `127.0.0.1`
   both fail; `10.0.2.2` works, matching the Android emulator convention. This
   is not in the Vega docs.
2. The media player refuses plain http outright:
   `isUriSchemeSecure Got an insecure protocol/scheme http, return error`,
   then `openMedia Invalid URI`. Audio over http is impossible, whatever the
   codec. Nothing in the `AudioPlayer` documentation mentions this.
3. `fetch()` rejects our self-signed development certificate
   ("Network request failed") while the **media pipeline accepts it**. The two
   subsystems disagree about trust, so a development setup needs http for JSON
   and https for audio simultaneously.

**Severity:** Important. Each one individually costs an hour of guessing,
because all three present as "nothing happens".

**Workaround:** Run two listeners, http on 8080 for manifests and https on 8443
for audio, and generate a self-signed certificate covering `10.0.2.2`. In
production both are https from one trusted origin and the problem disappears —
it is purely a local-development tax.

**Suggestion:** Document the https requirement on the `AudioPlayer` page, and
document `10.0.2.2` on the Vega Virtual Device page. Ideally, let the VVD trust
a developer-supplied certificate so one origin can serve both.

---

## 9. The app's own `console.log` reaches the log stream only intermittently

**Task:** Debug on-device behaviour with `vega device start-log-stream`.

**What happened:** Our `console.log` lines appeared in some runs and were
entirely absent in others — `grep -c CATCHUP60` returning 0 across a 2,671-line
capture — while in the same capture the w3cmedia library's own JavaScript logs
came through reliably. Nothing distinguished the runs; the code was unchanged.

**Severity:** Important. It is not a missing feature, it is an unreliable one,
which is worse: it was reasonable to conclude the app had crashed before
reaching the code.

**Workaround:** Stopped trusting the log stream. The app now reports progress
by HTTP GET to the development server, which always arrives.

**Suggestion:** If JS console output is sampled or rate-limited, say so in the
docs. An unreliable log is worse than no log, because the absence of a line
reads as the absence of the event.

---

## 10. Bedrock lists models you cannot invoke, and the 403 does not name the fix

**Task:** Call Claude on Bedrock from a fresh AWS account.

**Steps:** `aws bedrock list-foundation-models --by-provider anthropic`, pick
`anthropic.claude-opus-5` (listed, `modelLifecycle.status: ACTIVE`), invoke it.

**Expected:** Either a working call, or a listing that does not include models
this account cannot use.

**What happened:** The model is listed and ACTIVE, and the call returns 403:

> `anthropic.claude-opus-5 is not available for this account. You can explore
> other available models on Amazon Bedrock. For additional access options,
> contact AWS Sales`

That message reads like an entitlement or sales problem. It is neither. The real
state is visible only from a different API:

> ```
> authorizationStatus:     AUTHORIZED
> entitlementAvailability: AVAILABLE
> regionAvailability:      AVAILABLE
> agreementAvailability:   NOT_AVAILABLE   <- the only gap
> ```

The missing step is accepting the model's end-user agreement. Three of the four
fields say yes, the error message mentions none of them, and the pointer to AWS
Sales actively suggests the account needs something bought.

**Severity:** Important. Every first Bedrock call from a new account hits this,
and the error sends people to the wrong place — we went looking at credentials
and IAM first.

**Workaround:**

```bash
aws bedrock create-foundation-model-agreement --model-id anthropic.claude-opus-5 \
  --offer-token "$(aws bedrock list-foundation-model-agreement-offers \
    --model-id anthropic.claude-opus-5 --query 'offers[0].offerToken' --output text)"
```

**Suggestion:** Put the cause in the error: "the end-user agreement for this
model has not been accepted for this account — accept it in Model access, or
call CreateFoundationModelAgreement". One sentence replaces a half-hour. Better
still, mark agreement status in `list-foundation-models`, so a listing reflects
what is callable.

---

## 11. `aws login` credentials are unreadable by boto3 without an undeclared extra

**Task:** Use the credentials `aws login` just wrote, from Python.

**Steps:** `aws login` (which the CLI itself recommends over static keys),
then `boto3.Session().get_credentials()`.

**Expected:** Credentials, or `None`.

**What happened:** It **raises**:

> `botocore.exceptions.MissingDependencyException: Using the login credential
> provider requires an additional dependency. You will need to pip install
> "botocore[crt]" before proceeding.`

The message names the fix, which is good. The problem is the shape: a plain
`pip install boto3` cannot read credentials from the CLI's own recommended
sign-in flow, and the failure is an exception from a getter rather than a
missing-credentials return. Our availability probe called that getter to decide
whether to use AWS or fall back to the local path, so a credential *check* took
down the command it was protecting.

**Severity:** Minor in isolation, important in aggregate — `aws login` is what
the CLI promotes, so this is on the default path for new projects.

**Suggestion:** Either make `boto3` depend on the CRT extra when the login
provider is present, or have the provider return no-credentials rather than
raise, so a probe can treat it like any other absent provider. Mentioning the
extra in the `aws login` output would also help.

---

## 12. Bedrock access has three independent gates, each reported as the same kind of error

**Task:** Call an Anthropic model on Bedrock from a brand-new AWS account.

**Steps:** `aws configure`, then `client.messages.create(...)` through the
Anthropic SDK's `AnthropicBedrockMantle`. When that failed, probed the account
directly with `aws bedrock-runtime converse` across several model IDs.

**Expected:** One clear "you do not have access, do X" the first time.

**What happened:** Four failures in sequence, each one revealed only after
fixing the one before it:

1. `AccessDeniedException: AWS account registration is incomplete or revoked.`
   — the account itself was not activated. Nothing to do with Bedrock.
2. `ValidationException: Invocation of model ID ... with on-demand throughput
   isn't supported. Retry with inference profile ID` — `list-foundation-models`
   reports every Anthropic model as `INFERENCE_PROFILE`-only, so the model ID
   printed by the listing is never the ID you can call. You must look up a
   second listing, `list-inference-profiles`, and use the `us.`/`global.`
   prefixed ID.
3. `AccessDeniedException: Model use case details have not been submitted for
   this account. Fill out the Anthropic use case details form` — a console-only
   form, with no CLI equivalent and no link in the error.
4. For the newest models, `AccessDeniedException: anthropic.claude-opus-5 is
   not available for this account`, while `list-foundation-models` reports that
   same model as `ACTIVE`. "ACTIVE" describes the model's lifecycle, not your
   access; `agreementAvailability` is the field that answers the question
   anyone reading the listing is actually asking.

The costly part is that (2) and (4) are the same exception class with messages
that look alike, so the first instinct is to re-check credentials — which were
fine the whole time. Polly, on the same credentials, worked immediately.

**Severity:** Major. This is the first ten minutes of every new AWS account
that wants Bedrock, and the information needed to get through it is spread
across two listings, one console form, and four error strings.

**Suggestion:** One preflight API — `GET /model-access/{modelId}` — returning
the callable ID, whether the use-case form is on file, and whether the
agreement is accepted, so a client can tell a developer all of it at once.
Failing that: put the console URL in the use-case-form error, and make
`list-foundation-models` return the inference-profile ID that actually works
rather than an ID that is guaranteed to fail.
