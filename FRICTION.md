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
