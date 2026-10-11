# Product feedback, per tool

What each tool was used for, what worked, and what cost time. Every item here
happened during this build; `FRICTION.md` has the long-form entries with the
exact errors.

---

## Vega SDK and the Virtual Device

**Used for:** the whole TV app. React Native 0.83, `vega build-vega`,
`vega device install-app`, the Vega Virtual Device at 1920×1080.

**Worked well.** The installer is one command and the VVD needs no hardware,
no approval and no allowlist — that is the single biggest reason this project
was possible without a Fire TV stick. `vega device install-app` and
`launch-app` are fast enough to iterate on. `TVFocusGuideView` did the right
thing with focus on the first try.

**What cost time.**

*The device cannot be seen or driven from the CLI.* `vega device` has twenty
subcommands and neither a screenshot nor a key press. So verification means
sitting in front of the window, which cannot go in a test and misses things: a
recap running 63.94 seconds against a 60-second promise looks correct from
across the room. We found the VVD answers the Android emulator console, where
`screenrecord screenshot` works, and that is how this project first saw its own
UI. The port is not fixed — 5554 if the slot is free, 5556 if another emulator
has it — and `vega device list` does not print it, so a tool has to probe.
**Please add `vega device screenshot` and `vega device key`, and print the
console port.**

*Key injection fails silently.* On that same console, `event send
EV_KEY:KEY_CENTER:1` is accepted and answered `OK`, and nothing reaches the
app, because Vega OS is not Android and the key path has nowhere to deliver.
Several minutes went into diagnosing an app focus bug that did not exist.
`event mouse` does route. **A command that cannot act should not answer OK.**

*The device dies silently.* It stopped repeatedly after a few minutes.
`virtual_device.log` records the launch and nothing else — no shutdown line,
no reason. Every later command then fails with "Device not found: ... launch
the virtual device and try again", which reads like you forgot to start it.
A strong suspect is an `adb` server for an unrelated Android project: the VVD
takes emulator ports 5556/5557 and adb scans 5554–5584. After `adb
kill-server` it stayed up for about half an hour where it had never lasted
ten — but it later died again with no adb running, so that is at most part of
it. **Log the shutdown. One line with a reason would have ended this in a
minute, and "Device not found" should distinguish "was running, stopped at
HH:MM" from "was never started."**

*The project generator writes into the current directory.* `vega project
generate` placed files in the repository root and overwrote an existing
`.gitignore`. Recovered from git. **Generate into a named subdirectory, or
refuse to overwrite.**

*Media constraints are undocumented and discovered by failure.* `AudioPlayer`
refuses `wav` silently, and refuses `http://` with "isUriSchemeSecure Got an
insecure protocol/scheme http, return error" — so local development needs TLS
even though nothing is secret, and a self-signed certificate that the media
pipeline accepts is still rejected by `fetch`. The result is two listeners on
two ports and a URL rewrite in the app. **A "media requirements" page —
codecs, schemes, certificate handling, Range support — would save every TV app
author this.**

*`console.log` is unreliable.* The w3cmedia library's own lines reach `vega
device start-log-stream` while the app's do not. We ended up reporting over
HTTP to a local endpoint instead, which is how anything on-device was
observable at all.

---

## MLB StatsAPI

**Used for:** every piece of game data. Schedule, live feed, win probability.

**Worked well.** Public, no key, no auth, no rate limit encountered. The
`fields` parameter is excellent and underused: it cut a `winProbability`
response from **1.08 MB to 39 KB**, a 27× reduction that is the difference
between polling a live game comfortably and not. `homeTeamWinProbabilityAdded`
per at-bat is exactly the right primitive and we have not found it published
this cleanly anywhere else.

**What cost time.**

*A nonexistent gamePk returns 200.* With populated placeholder fields, so a
typo looks like a real game until something downstream behaves strangely. We
detect it with a team id of `0` as a sentinel. **Return 404.**

*A scheduled game and a bad gamePk are indistinguishable.* `winProbability`
404s with "Game data couldn't be found" for both. One means "come back after
the first pitch" and the other means "you sent the wrong id" — the caller
needs to tell them apart and currently has to make a second call to do it.

*Replay by timecode is undocumented.* `winProbability` accepts the live feed's
`timecode` parameter and returns the game as it stood at that moment — 32
plays mid-game against 64 at the final out. This makes any finished game
replayable at any point, which is enormously useful for testing and demos.
**Please document it.** (We contributed the same capability to the main Python
wrapper: `toddrob99/MLB-StatsAPI#173`.)

---

## Amazon Bedrock

**Used for:** rewording narration lines, under a numeric guard. Claude Haiku
4.5 via `bedrock-runtime converse`.

**Worked well.** Once reachable, it was fast and did exactly the constrained
job asked of it — tightening sentences without inventing figures. On the first
successful run it only ever subtracted.

**What cost time.** Four separate gates stand between a new AWS account and a
first call, each reporting failure in a way that resembles the others.

1. `AccessDeniedException: AWS account registration is incomplete or revoked`
   — the account, not Bedrock.
2. `ValidationException: Invocation of model ID ... with on-demand throughput
   isn't supported` — `list-foundation-models` reports every Anthropic model as
   `INFERENCE_PROFILE`-only, so **the id the listing prints is one you can
   never call.** You must consult a second listing for the `us.`/`global.`
   prefixed id. **Return the callable id.**
3. `Model use case details have not been submitted for this account` — a
   console-only form, with **no link in the error**. The console page named
   after it, *Model access*, has been retired and now says access is automatic
   while also saying it is not automatic for Anthropic models, and does not
   link the form. The route that works is Model catalog → a model → Playground
   → invoke. Worse, **only one model's error leads there**: the newest models
   return a flat "not available for this account" and show no form, so the
   model a developer opens first is the one that cannot help them.
4. `ThrottlingException: Too many tokens per day` on an account that has spent
   nothing — and there *is no per-day quota* for that model. The zeroed quotas
   are the four per-minute ones. `get-service-quota` compounds this by
   returning the **default** (5,000,000) where the applied value is 0; only
   `list-service-quotas` shows the zero. And the quota cannot be requested:
   Service Quotas refuses any value at or below the default, so the one number
   that is wrong is the one you cannot change.

**One preflight call — `GET /model-access/{modelId}` returning the callable
id, whether the use-case form is on file, and whether quota is non-zero —
would replace all of that.**

*Finally, the SDK's Bedrock client is entitled separately.*
`AnthropicBedrockMantle` returned 403 "`anthropic.claude-haiku-4-5` is not
available for this account" while `converse` answered "ok" on the same
credentials in the same second, with 5,000,000 TPM granted. That is Bedrock's
own sentence for an ungranted model, so it reads as the gate just cleared.
**Say which service is refusing.**

---

## Amazon Polly

**Used for:** all deployed speech.

**Worked well.** Worked immediately on an activated account with no
entitlement dance — a pointed contrast with Bedrock. Neural quality is good
for this material. SSML speech marks are the feature that made the deployed
design possible: one request returns mark times, so segment boundaries are
measured rather than estimated, and the TV cards stay in step with the voice
with no ffmpeg anywhere.

**What cost time.**

*The generative engine cannot report speech marks.* `The selected speech mark
type - ssml - is not supported for this engine`. So the voice that reads best
is the one that cannot say when it finished, and a timed application has to
choose quality or timing. **Support marks on generative.**

*Marks and audio need two calls on identical text,* and both are billed. A
60-second recap is ~1,000 characters of SSML billed as ~2,000. **One request
returning both would halve it.**

---

## AWS Lambda, API Gateway, S3, CloudFormation

**Used for:** the deployed recap API.

**Worked well.** API Gateway's certificate and S3's native Range support
together deleted an entire class of workaround from the TV app. Lambda's
always-free tier covers this workload completely. Deploy is one script over
the AWS CLI with no extra toolchain.

**What cost time.**

*`ReservedConcurrentExecutions` cannot be used to limit spend on a new
account.* Setting it to 2 was rejected: `decreases account's
UnreservedConcurrentExecution below its minimum value of [10]` — the account
total is 10, not 1000, so reserving any share leaves less than the 10 Lambda
requires stay unreserved. **To restrict concurrency you would first have to
raise the account limit.**

*`aws cloudformation deploy` silently reuses previous parameter values.* It
sends `UsePreviousValue` for anything not passed, so a parameter keeps
whatever an earlier deploy set — indefinitely — while CloudFormation
truthfully reports "No changes to deploy". Two deploys appeared to succeed
while serving an old model. **A line naming parameters carried over from the
previous deploy would make this visible.**

*Lambda creates its log group with no expiry,* so logs accumulate until they
cost more than the function. Declaring the group with `RetentionInDays` fixes
it, but the default should not be "forever".

---

## `aws login` and botocore

**Used for:** credentials, as the CLI itself recommends over static keys.

**What cost time.** `boto3.Session().get_credentials()` **raises** —
`MissingDependencyException: ... requires an additional dependency ... pip
install "botocore[crt]"` — rather than returning no credentials. So a plain
`pip install boto3` cannot read credentials from the CLI's own recommended
sign-in flow, and an availability *probe* takes down the command it was
protecting. **Either depend on the CRT extra when the login provider is
present, or have the provider return no-credentials rather than raise, so a
probe can treat it like any other absent provider.**
