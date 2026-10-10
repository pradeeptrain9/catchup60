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
from .mlb import FeedError


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
            f"limited by {engine['limitedBy']}",
            file=sys.stderr,
        )
        for segment in manifest["segments"]:
            print(f"  {segment['start']:6.2f} +{segment['dur']:5.2f}  "
                  f"[{segment['kind']}] {segment['text']}", file=sys.stderr)
    return 0


def cmd_recap(args) -> int:
    try:
        manifest = recap.from_api(args.game_pk, as_of=args.as_of,
                                  total_seconds=args.seconds)
    except FeedError as exc:
        raise SystemExit(f"could not load game {args.game_pk}: {exc}")
    except ValueError as exc:
        raise SystemExit(str(exc))
    return _emit(manifest, args)


def cmd_synthetic(args) -> int:
    context, plays = fixtures.load_synthetic()
    manifest = recap.build(context, plays, as_of=args.as_of,
                           total_seconds=args.seconds)
    return _emit(manifest, args)


def cmd_clean(args) -> int:
    """Drop intermediates. Never touches out/."""
    for target in (config.WORK,):
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

    live = sub.add_parser("recap", help="recap a real game by gamePk")
    live.add_argument("game_pk", type=int)
    add_recap_flags(live)
    live.set_defaults(fn=cmd_recap)

    synthetic = sub.add_parser(
        "synthetic", help="recap the offline fixture game (no network)")
    add_recap_flags(synthetic)
    synthetic.set_defaults(fn=cmd_synthetic)

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
