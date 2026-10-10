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
    if getattr(args, "voice", "kokoro") == "polly":
        from .speech import polly
        ok, reason = polly.available()
        if not ok:
            raise SystemExit(f"cannot synthesize with Polly: {reason}")
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
    from .server import serve
    serve(port=args.port, use_tls=args.https)
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
        target.add_argument("--voice", choices=("kokoro", "polly"),
                            default="kokoro",
                            help="speech backend for --audio (default kokoro,"
                                 " local and free)")
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
    server.set_defaults(fn=cmd_serve)

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
