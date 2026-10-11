"""Command line. `./run <command>`.

Failures are SystemExit with the fix in the message, never tracebacks: the
person running this is mid-build and wants the next command, not a stack.
"""

import argparse
import json
import shutil
import sys
from datetime import date

from . import config, fixtures, recap
from .mlb import FeedError, GameNotFound, GameNotStarted


def _synth_for(args, label: str):
    """Build the synth callable, or None when audio was not asked for."""
    if not getattr(args, "audio", False):
        return None
    workdir = config.WORK / label
    voice = getattr(args, "voice", "kokoro")
    if voice in ("polly", "polly-ssml"):
        module = "polly_ssml" if voice == "polly-ssml" else "polly"
        from importlib import import_module
        speech = import_module(f".speech.{module}", __package__)
        ok, reason = speech.available()
        if not ok:
            raise SystemExit(f"cannot synthesize with Polly: {reason}")
        if voice == "polly-ssml":
            return recap.polly_ssml_synth(workdir)
        return recap.polly_synth(workdir, progress=True)
    from .speech import kokoro
    ok, reason = kokoro.available()
    if not ok:
        raise SystemExit(f"cannot synthesize: {reason}")
    return recap.kokoro_synth(workdir, progress=True)


def _rephrase_for(args):
    """Build the rephrase callable, or None to keep the deterministic text."""
    if getattr(args, "narrator", "template") != "bedrock":
        return None
    from .narrate import bedrock
    ok, reason = bedrock.available()
    if not ok:
        raise SystemExit(f"cannot use Bedrock: {reason}")
    return recap.bedrock_rephrase()


def cmd_doctor(args) -> int:
    """Check everything needed to produce a recap, with the fix inline."""
    problems = 0

    def report(ok: bool, label: str, fix: str = "") -> None:
        nonlocal problems
        if ok:
            print(f"ok    {label}")
        else:
            problems += 1
            print(f"MISS  {label}" + (f"  ->  {fix}" if fix else ""))

    report(sys.version_info >= (3, 11), f"python {sys.version.split()[0]}",
           "install Python 3.11 or newer")

    try:
        import httpx  # noqa: F401
        report(True, "httpx")
    except ImportError:
        report(False, "httpx", "./setup.sh")

    report(fixtures.SYNTHETIC.exists(), "synthetic fixture",
           f"missing {fixtures.SYNTHETIC}")

    from .speech import kokoro
    ok, reason = kokoro.available()
    report(ok, "kokoro speech", reason)

    from .speech import encode
    ok, reason = encode.available()
    report(ok, "ffmpeg (mp3 for Vega)", reason)

    # The AWS path is optional by design: everything works without it.
    from .narrate import bedrock
    ok, reason = bedrock.available()
    print(f"{'ok   ' if ok else 'opt  '} bedrock narration"
          + (f"  ->  {reason}" if not ok else f"  ({bedrock.MODEL})"))

    from .speech import polly
    ok, reason = polly.available()
    print(f"{'ok   ' if ok else 'opt  '} polly speech"
          + (f"  ->  {reason}" if not ok else f"  ({polly.VOICE})"))

    try:
        from . import mlb
        games = mlb.schedule(date=date.today().isoformat())
        report(True, f"statsapi reachable ({len(games)} games today)")
    except FeedError as exc:
        report(False, "statsapi reachable", str(exc))

    print()
    if problems:
        print(f"{problems} problem(s). Fix those and re-run ./run doctor.")
        return 1
    print("All good. Try: ./run synthetic")
    return 0


def cmd_games(args) -> int:
    from . import mlb
    when = args.date or date.today().isoformat()
    try:
        games = mlb.schedule(date=when)
    except FeedError as exc:
        raise SystemExit(f"could not load the schedule: {exc}")
    if not games:
        print(f"No games on {when}.")
        return 0
    for game in games:
        series = f"  [{game['series']}]" if game.get("series") else ""
        print(f"{game['gamePk']}  {game['away']} @ {game['home']}"
              f"  — {game['state']}{series}")
    return 0


def _emit(manifest: dict, args) -> int:
    text = json.dumps(manifest, indent=1)
    if args.out:
        out = config.OUT / args.out if not args.out.startswith("/") else args.out
        with open(out, "w") as handle:
            handle.write(text + "\n")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)
    if args.summary:
        engine = manifest["engine"]
        print(
            f"\n{manifest['away']} {manifest['gameState']['away']} — "
            f"{manifest['home']} {manifest['gameState']['home']}, "
            f"{manifest['gameState']['half']} {manifest['gameState']['inning']}\n"
            f"{manifest['totalSeconds']}s, {engine['selected']} of "
            f"{engine['considered']} plays, runs "
            f"{engine['runsExplained']}/{engine['runsTotal']}, "
            f"limited by {engine['limitedBy']}, "
            f"timings from {manifest['timingSource']}, "
            f"words from {manifest['narrationSource']}",
            file=sys.stderr,
        )
        if manifest.get("audioUrl"):
            print(f"audio: {manifest['audioUrl']}", file=sys.stderr)
        if manifest.get("speechSkipped"):
            print(f"speech skipped: {manifest['speechSkipped']}", file=sys.stderr)
        if manifest.get("narrationFallback"):
            print(f"narrator fell back: {manifest['narrationFallback']}",
                  file=sys.stderr)
        for segment in manifest["segments"]:
            print(f"  {segment['start']:6.2f} +{segment['dur']:5.2f}  "
                  f"[{segment['kind']}] {segment['text']}", file=sys.stderr)
    return 0


def cmd_recap(args) -> int:
    label = f"{args.game_pk}-{args.as_of if args.as_of is not None else 'latest'}"
    try:
        manifest = recap.from_api(args.game_pk, as_of=args.as_of,
                                  total_seconds=args.seconds,
                                  synth=_synth_for(args, label),
                                  rephrase=_rephrase_for(args),
                                  use_cache=not args.no_cache)
    except GameNotStarted as exc:
        raise SystemExit(f"{exc}. Try ./run games to find one in progress.")
    except GameNotFound:
        raise SystemExit(
            f"no game {args.game_pk}. Run ./run games to list today's gamePks.")
    except FeedError as exc:
        raise SystemExit(f"could not load game {args.game_pk}: {exc}")
    except ValueError as exc:
        raise SystemExit(str(exc))
    return _emit(manifest, args)


def cmd_synthetic(args) -> int:
    context, plays = fixtures.load_synthetic()
    label = f"synthetic-{args.as_of if args.as_of is not None else 'latest'}"
    manifest = recap.build(context, plays, as_of=args.as_of,
                           total_seconds=args.seconds,
                           synth=_synth_for(args, label),
                           rephrase=_rephrase_for(args))
    return _emit(manifest, args)


def cmd_serve(args) -> int:
    from .replay import Replay
    from .server import serve
    replay = None
    if args.replay:
        replay = Replay(game_pk=args.replay,
                        seconds_per_at_bat=args.replay_rate,
                        head_start=args.replay_from)
    serve(port=args.port, use_tls=args.https, replay=replay)
    return 0


def cmd_clean(args) -> int:
    """Drop intermediates. Never touches out/."""
    from . import cache as recap_cache
    for target in (config.WORK, recap_cache.DIR):
        if target.exists():
            shutil.rmtree(target)
            print(f"removed {target}")
    config.WORK.mkdir(parents=True, exist_ok=True)
    print("out/ left alone.")
    return 0


def cmd_watch(args) -> int:
    from . import watch
    dest = watch.watch(args.game_pk, every=args.every,
                       idle_every=args.idle_every, hours=args.hours)
    print(dest)
    return 0


def cmd_verdict(args) -> int:
    import json

    from . import watch

    if args.url:
        # The deployed watcher's record, read over plain https with no AWS
        # credentials. That is the point of the route: the answer should be
        # legible from a phone, which is where you are when the game ends.
        import httpx
        base = args.url.rstrip("/")
        reply = httpx.get(f"{base}/watch/{args.game_pk}", timeout=30)
        reply.raise_for_status()
        result = reply.json()
        if args.merge:
            # Both records answer the same question, and neither is complete:
            # the laptop one has the early idle ticks, the scheduled one has
            # whatever happened after the lid closed. Merging is the honest
            # read. Duplicate timestamps are fine — growth is counted on
            # consecutive pairs, and a repeated count is not growth.
            rows = httpx.get(f"{base}/watch/{args.game_pk}",
                             params={"rows": "1"}, timeout=30).json()
            local = config.OUT / f"watch-{args.game_pk}.jsonl"
            if local.exists():
                rows = rows + watch.parse(local.read_text())
            result = watch.verdict_rows(rows)
            result["sources"] = ["deployed", "local"]
    else:
        path = config.OUT / f"watch-{args.game_pk}.jsonl"
        if not path.exists():
            raise SystemExit(
                f"no watch file at {path} — ./run watch {args.game_pk}, "
                f"or --url <api> to read the deployed record")
        result = watch.verdict(path)
    print(json.dumps(result, indent=1))
    # Non-zero while the premise is unproven, so this can gate a checklist
    # rather than be read and forgotten. Exit 2 separates "no data yet" from
    # exit 1's "watched it and the answer is no" — only one of those means
    # the project needs rethinking.
    if result["updatesMidGame"]:
        return 0
    return 1 if result["liveTicks"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catchup60",
        description="Build a 60-second catch-up recap of a live baseball game.",
    )
    sub = parser.add_subparsers(dest="command")

    doctor = sub.add_parser("doctor", help="check the setup")
    doctor.set_defaults(fn=cmd_doctor)

    games = sub.add_parser("games", help="list games for a date")
    games.add_argument("--date", help="YYYY-MM-DD (default: today)")
    games.set_defaults(fn=cmd_games)

    def add_recap_flags(target) -> None:
        target.add_argument("--as-of", type=int, dest="as_of",
                            help="atBatIndex to stop at (replays a past moment)")
        target.add_argument("--seconds", type=float,
                            default=config.TOTAL_SECONDS,
                            help=f"recap budget (default {config.TOTAL_SECONDS})")
        target.add_argument("--out", help="write to out/<name> instead of stdout")
        target.add_argument("--summary", action="store_true",
                            help="print a human-readable breakdown to stderr")
        target.add_argument("--audio", action="store_true",
                            help="synthesize narration; timings become real")
        target.add_argument("--no-cache", action="store_true", dest="no_cache",
                            help="rebuild even if this at-bat is cached")
        target.add_argument("--voice",
                            choices=("kokoro", "polly", "polly-ssml"),
                            default="kokoro",
                            help="speech backend for --audio (default kokoro,"
                                 " local and free; polly-ssml is the one-call"
                                 " deployed path, no ffmpeg)")
        target.add_argument("--narrator", choices=("template", "bedrock"),
                            default="template",
                            help="who writes the words (default template,"
                                 " deterministic; bedrock rewords it under the"
                                 " numeric guard)")

    live = sub.add_parser("recap", help="recap a real game by gamePk")
    live.add_argument("game_pk", type=int)
    add_recap_flags(live)
    live.set_defaults(fn=cmd_recap)

    synthetic = sub.add_parser(
        "synthetic", help="recap the offline fixture game (no network)")
    add_recap_flags(synthetic)
    synthetic.set_defaults(fn=cmd_synthetic)

    server = sub.add_parser("serve", help="serve manifests and audio over HTTP")
    server.add_argument("--port", type=int, default=8080)
    server.add_argument("--https", action="store_true",
                        help="serve over TLS; Vega's player refuses http:// audio")
    server.add_argument("--replay", type=int, metavar="GAMEPK",
                        help="play a finished game back as if it were live, so"
                             " the live path runs with no live game")
    server.add_argument("--replay-rate", type=float, default=10.0,
                        dest="replay_rate", metavar="SECONDS",
                        help="wall-clock seconds per at-bat (default 10)")
    server.add_argument("--replay-from", type=int, default=20,
                        dest="replay_from", metavar="ATBAT",
                        help="at-bat the replay opens on (default 20)")
    server.set_defaults(fn=cmd_serve)

    watcher = sub.add_parser(
        "watch",
        help="poll a game and record whether winProbability advances live")
    watcher.add_argument("game_pk", type=int)
    watcher.add_argument("--every", type=float, default=60.0,
                         help="seconds between polls once the game is live")
    watcher.add_argument("--idle-every", type=float, default=600.0,
                         dest="idle_every",
                         help="seconds between polls before first pitch")
    watcher.add_argument("--hours", type=float, default=26.0,
                         help="give up after this long")
    watcher.set_defaults(fn=cmd_watch)

    said = sub.add_parser(
        "verdict", help="read a watch file and answer what it was opened for")
    said.add_argument("--url", default=None,
                      help="read the deployed watcher instead of out/")
    said.add_argument("--merge", action="store_true",
                      help="with --url, also fold in the local watch file")
    said.add_argument("game_pk", type=int)
    said.set_defaults(fn=cmd_verdict)

    clean = sub.add_parser("clean", help="drop cache/work")
    clean.set_defaults(fn=cmd_clean)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "fn", None):
        parser.print_help()
        return 1
    try:
        return args.fn(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
