"""Lambda entry point. Same routes as src/server.py, different plumbing.

The local server exists because Vega refused the simple options: its media
player will not load http, and `fetch` will not accept the self-signed cert
the media pipeline does accept, so src/server.py runs two listeners on two
ports and the TV app carries a rewrite to move audio URLs between them.

Deploying removes that entire problem rather than solving it. API Gateway
terminates a real certificate, so JSON and audio are both plain https from the
app's point of view, and the audio itself is a presigned S3 URL — S3 serves
Range requests natively, which is the other thing the media player insists on
and the other reason src/server.py grew code.

What changes here, and why:

* Speech is speech/polly_ssml.py, one call with speech marks. No ffmpeg exists
  in Lambda and Kokoro's 325MB does not fit the unzipped limit.
* The cache is S3, installed over the filesystem store. /tmp survives a warm
  container and nothing else, so without this every cold start pays Polly
  again for an at-bat already rendered.
* Narration still prefers Bedrock and still falls back to the template, with
  the reason in the manifest. A deploy does not get to be less honest than the
  CLI about which narrator spoke.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import cache, catalog, config, fixtures, mlb, recap, watch  # noqa: E402

BUCKET = os.environ["CATCHUP60_BUCKET"]
# Long enough for a viewer to start a recap and let it finish, short enough
# that a leaked manifest stops working. The app re-requests the manifest to
# play again anyway, and a cache hit re-signs.
AUDIO_TTL = int(os.environ.get("CATCHUP60_AUDIO_TTL", "3600"))
USE_BEDROCK = os.environ.get("CATCHUP60_NARRATOR", "bedrock") == "bedrock"

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        import boto3
        _s3 = boto3.client("s3")
    return _s3


# --- S3-backed manifest cache ------------------------------------------------

def _manifest_key(cache_key: str) -> str:
    return f"manifests/{cache_key}.json"


def cache_get(cache_key: str) -> dict | None:
    try:
        body = s3().get_object(Bucket=BUCKET, Key=_manifest_key(cache_key))
        return json.loads(body["Body"].read())
    except Exception:
        # Any failure is a miss. A cache that can fail a request is worse than
        # no cache: the caller can always rebuild.
        return None


def cache_put(cache_key: str, manifest: dict) -> None:
    try:
        s3().put_object(
            Bucket=BUCKET, Key=_manifest_key(cache_key),
            Body=json.dumps(manifest).encode(),
            ContentType="application/json",
        )
    except Exception:
        pass


cache.install(cache_get, cache_put)


# --- audio -------------------------------------------------------------------

def presign(key: str) -> str:
    return s3().generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=AUDIO_TTL,
    )


def upload_audio(path: Path, label: str) -> str:
    """Put the mp3 where S3 can serve it with Range, and return its key."""
    key = f"audio/{label}/narration.mp3"
    s3().upload_file(
        str(path), BUCKET, key,
        ExtraArgs={"ContentType": "audio/mpeg",
                   "CacheControl": f"max-age={AUDIO_TTL}"},
    )
    return key


def sign(manifest: dict) -> dict:
    """Turn the stored s3:// URI into a URL the device can play.

    Signing on the way out rather than on the way in is what makes the cache
    work. A manifest is cached by recap.from_api, under a key only from_api
    computes; anything written afterwards under a key recomputed by hand here
    missed every time, because the manifest's asOfPlayIndex is the last play
    at or before `as_of`, not `as_of` itself. So nothing is written afterwards:
    the synth stores a durable key and the signature — the one part that
    expires — is applied per response.
    """
    uri = manifest.get("audioUrl") or ""
    if uri.startswith("s3://"):
        manifest["audioUrl"] = presign(uri.split("/", 3)[3])
    return manifest


# --- the watcher ------------------------------------------------------------

# One object per tick rather than appending to a jsonl. S3 has no append, so
# the alternative is read-modify-write, and the one thing a record kept to
# settle a disputed premise must never do is lose rows to a lost race. A
# prefix listing reassembles them in order, and the key is the timestamp, so a
# retried invocation overwrites its own row instead of double-counting it.
def _watch_key(game_pk: int, at: str) -> str:
    return f"watch/{game_pk}/{at}.json"


def _done_key(game_pk: int) -> str:
    return f"watch/{game_pk}/_done"


def _finished(game_pk: int) -> bool:
    """Whether this game's record is already closed.

    A rule on a fixed rate has no idea a game ended, so without this it polls
    a finished game forever: 288 useless objects a day, each one another S3
    GET that the verdict route has to make before it can answer. At 154
    objects that route already takes 5.4 seconds, and eleven days of ticking
    would have pushed it past the function's own timeout — the record would
    have destroyed the ability to read it.
    """
    try:
        s3().head_object(Bucket=BUCKET, Key=_done_key(game_pk))
        return True
    except Exception:
        return False


def watch_tick(game_pks: list[int]) -> dict:
    """One observation per game, from the schedule rather than a laptop.

    The local watcher died at nine and a half hours with no error, almost
    certainly because the lid closed. This path has no lid.
    """
    wrote = {}
    for game_pk in game_pks:
        if _finished(game_pk):
            wrote[game_pk] = "done"
            continue
        row = watch.tick(game_pk)
        at = row.get("at", "unknown")
        if row.get("state") == "Final":
            # Record the Final tick, then close the record. One Final tick is
            # what answers the question this watcher exists for — whether
            # anything is backfilled at the whistle — and every tick after it
            # is noise that makes the answer slower to read.
            try:
                s3().put_object(Bucket=BUCKET, Key=_done_key(game_pk),
                                Body=b"{}", ContentType="application/json")
            except Exception:
                pass
        try:
            s3().put_object(
                Bucket=BUCKET, Key=_watch_key(game_pk, at),
                Body=json.dumps(row).encode(),
                ContentType="application/json",
            )
            wrote[game_pk] = row.get("state", "?")
        except Exception as exc:
            wrote[game_pk] = f"put failed: {type(exc).__name__}: {exc}"
        # Visible in CloudWatch without reading the bucket, which is how you
        # check on this at 1am from a phone.
        print(f"[watch] {game_pk} {at} state={row.get('state')} "
              f"cursor={row.get('cursor')} wpPlays={row.get('wpPlays')} "
              f"lag={row.get('lag')}"
              + (f" {row['error']}" if row.get("error") else ""))
    return wrote


def _fetch_row(key: str) -> dict | None:
    try:
        return json.loads(s3().get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except Exception:
        # A row that will not parse is a row the verdict can live without;
        # refusing to answer at all because of one is worse.
        return None


def watch_rows(game_pk: int) -> list[dict]:
    """Every tick recorded for a game.

    Fetched concurrently because this is one S3 GET per tick and the round
    trip, not the work, is the whole cost: serially, a few hundred ticks took
    over five seconds and a full game's worth would have run the function out
    of time. Ordering is not preserved here and does not need to be —
    watch.verdict_rows sorts, because it also merges records from two
    different watchers.
    """
    from concurrent.futures import ThreadPoolExecutor

    keys = []
    token = None
    while True:
        kwargs = {"Bucket": BUCKET, "Prefix": f"watch/{game_pk}/"}
        if token:
            kwargs["ContinuationToken"] = token
        page = s3().list_objects_v2(**kwargs)
        keys += [item["Key"] for item in page.get("Contents", [])
                 if not item["Key"].endswith("/_done")]
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")

    with ThreadPoolExecutor(max_workers=32) as pool:
        return [row for row in pool.map(_fetch_row, keys) if row is not None]


# --- routes ------------------------------------------------------------------

def _reply(status: int, payload) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json",
                    # The TV app is not a browser origin, but the browser-based
                    # debugging that found every Vega media bug is, and a
                    # deployed endpoint nobody can poke at from a console is
                    # harder to trust than one they can.
                    "access-control-allow-origin": "*"},
        "body": json.dumps(payload),
    }


def _synth(label: str):
    """The deployed synth: speak, then park the mp3 in S3.

    Returns the object's s3:// URI where the local path would go, so the
    manifest that gets cached carries a durable key instead of a /tmp path
    that dies with the container or a signature that expires inside the cache.
    """
    inner = recap.polly_ssml_synth(config.WORK / label)

    def run(segments: list[dict]):
        path, durations = inner(segments)
        return f"s3://{BUCKET}/{upload_audio(Path(path), label)}", durations

    return run


def _rephrase():
    if not USE_BEDROCK:
        return None
    return recap.bedrock_rephrase()


def _recap(who: str, query: dict) -> dict:
    as_of = query.get("as_of") or None
    as_of = int(as_of) if as_of else None
    seconds = float(query.get("seconds") or config.TOTAL_SECONDS)
    want_audio = query.get("audio", "1") not in ("0", "false", "")

    if who == "synthetic":
        label = f"synthetic-{as_of if as_of is not None else 'latest'}"
        # The fixture path does not go through from_api, so it caches here.
        # Without it the demo game re-synthesizes on every request.
        key = cache.key(0, as_of, seconds, want_audio, USE_BEDROCK)
        manifest = cache.get(key)
        if manifest is None:
            context, plays = fixtures.load_synthetic()
            manifest = recap.build(
                context, plays, as_of=as_of, total_seconds=seconds,
                synth=_synth(label) if want_audio else None,
                rephrase=_rephrase(),
            )
            if recap.cacheable(manifest):
                cache.put(key, manifest)
    else:
        game_pk = int(who)
        label = f"{game_pk}-{as_of if as_of is not None else 'latest'}"
        manifest = recap.from_api(
            game_pk, as_of=as_of, total_seconds=seconds,
            synth=_synth(label) if want_audio else None,
            rephrase=_rephrase(),
        )
    return _reply(200, sign(manifest))


def handler(event, context=None):
    # A scheduled invocation, not an HTTP one. EventBridge delivers the rule's
    # Input verbatim, so the games to poll travel in the event rather than in
    # an environment variable — changing which games are watched is then a
    # template parameter, not a redeploy of the function.
    if "watch" in event and "rawPath" not in event:
        pks = event["watch"]
        if isinstance(pks, str):
            pks = [p for p in (x.strip() for x in pks.split(",")) if p]
        return watch_tick([int(p) for p in pks])

    route = (event.get("rawPath") or "/").rstrip("/") or "/"
    query = event.get("queryStringParameters") or {}
    try:
        if route == "/":
            return _reply(200, {
                "service": "catchup60",
                "routes": ["/playable", "/games", "/recap/{gamePk}",
                           "/recap/synthetic", "/watch/{gamePk}",
                           "/log?m="],
            })
        if route == "/log":
            # The device's only way to say what it rendered. The local server
            # has had this from the start; without it here, switching the app
            # to the deployed origin silently turns off on-device debugging —
            # every report 404s and the screen becomes unobservable again.
            # print() is the CloudWatch channel.
            print(f"[device] {query.get('m', '')}")
            return _reply(200, {"logged": True})
        if route == "/games":
            return _reply(200, mlb.schedule(date=query.get("date")))
        if route == "/playable":
            return _reply(200, catalog.playable(today=query.get("date")))
        if route.startswith("/watch/"):
            game_pk = int(route.removeprefix("/watch/"))
            rows = watch_rows(game_pk)
            if query.get("rows") in ("1", "true"):
                return _reply(200, rows)
            # The verdict arithmetic is src/watch.py's, not a second copy
            # here. Two implementations of this answer is two answers.
            return _reply(200, watch.verdict_rows(rows))
        if route.startswith("/recap/"):
            return _recap(route.removeprefix("/recap/"), query)
        return _reply(404, {"error": f"no route {route}"})
    except mlb.GameNotStarted as exc:
        return _reply(409, {"error": str(exc), "reason": "notStarted"})
    except mlb.GameNotFound as exc:
        return _reply(404, {"error": str(exc), "reason": "notFound"})
    except mlb.FeedError as exc:
        return _reply(502, {"error": str(exc), "reason": "upstream"})
    except Exception as exc:
        # Never a bare 500 with no body: the device has no other way to find
        # out what went wrong, and CloudWatch is not on the TV.
        return _reply(500, {"error": f"{type(exc).__name__}: {exc}"})
