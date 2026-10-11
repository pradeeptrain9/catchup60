"""HTTP server for the TV app. Standard library only.

Deliberately no framework. The app needs two things — a manifest and a wav —
and a judge should be able to run this with `./run serve` after a pip install
that pulled exactly one dependency. FastAPI would buy nothing here and cost
everyone an install.

Binds 0.0.0.0 because the consumer is the Vega Virtual Device, which does not
share the host's loopback.
"""

import json
import socket
import ssl
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import cache, catalog, config, fixtures, mlb, recap
from .replay import Replay


CERT_DIR = config.CACHE / "certs"


def ensure_cert() -> tuple[Path, Path]:
    """Self-signed cert for the dev server.

    Vega's media player rejects plain http:// outright —
    "isUriSchemeSecure Got an insecure protocol/scheme http, return error" —
    so narration cannot be delivered over http at all, whatever the codec.
    Local development therefore needs TLS even though nothing here is secret.

    Covers localhost, 127.0.0.1 and 10.0.2.2, the last being the address the
    Vega Virtual Device uses to reach the host.
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    cert, key = CERT_DIR / "dev.crt", CERT_DIR / "dev.key"
    if cert.exists() and key.exists():
        return cert, key

    address = lan_address()
    names = ["DNS:localhost", "IP:127.0.0.1", "IP:10.0.2.2", f"IP:{address}"]
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
         "-days", "365", "-nodes",
         "-keyout", str(key), "-out", str(cert),
         "-subj", "/CN=catchup60-dev",
         "-addext", f"subjectAltName={','.join(names)}"],
        check=True, capture_output=True,
    )
    return cert, key


def lan_address() -> str:
    """Best guess at an address the virtual device can reach.

    No traffic is sent: connecting a UDP socket only picks the route the OS
    would use, which is how to learn the interface address without parsing
    ifconfig.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "catchup60"

    # --- plumbing --------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The app is served from the device, not from this origin.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict | list) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def log_message(self, fmt, *args) -> None:
        # One readable line per request instead of BaseHTTPRequestHandler's
        # default, which interleaves badly with synthesis progress.
        print(f"  {self.command} {self.path} -> {args[1]}", flush=True)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if route == "/":
                return self._json(200, {
                    "service": "catchup60",
                    "routes": ["/playable", "/games", "/recap/{gamePk}",
                               "/recap/synthetic",
                               "/audio/{label}/narration.mp3", "/log?m="],
                })
            if route == "/log":
                # Telemetry channel for the device. Vega's JS console output
                # reaches `vega device start-log-stream` only intermittently —
                # the w3cmedia library's own lines come through while the app's
                # do not — which makes on-device debugging guesswork. An http
                # GET always arrives, so the app reports here instead.
                message = query.get("m", [""])[0]
                print(f"  [device] {message}", flush=True)
                return self._json(200, {"logged": True})
            if route == "/games":
                return self._json(200, mlb.schedule(
                    date=query.get("date", [None])[0]))
            if route == "/playable":
                # The app asks what it can recap and gets an ordered answer:
                # live games first, then finished ones, then the fixture.
                games = catalog.playable(today=query.get("date", [None])[0])
                return self._json(200, self._with_replay(games))
            if route.startswith("/recap/"):
                return self._recap(route.removeprefix("/recap/"), query)
            if route.startswith("/audio/"):
                return self._audio(route.removeprefix("/audio/"))
            self._json(404, {"error": f"no route {route}"})
        except mlb.GameNotStarted as exc:
            # 409: the request is well formed, the game just has no plays yet.
            # The app uses this to hide the Catch Up button rather than to
            # show an error.
            self._json(409, {"error": str(exc), "reason": "notStarted"})
        except mlb.GameNotFound as exc:
            self._json(404, {"error": str(exc), "reason": "notFound"})
        except mlb.FeedError as exc:
            self._json(502, {"error": str(exc), "reason": "upstream"})
        except Exception as exc:  # never leave the device hanging on a 200
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    # --- routes ----------------------------------------------------------
    def _recap(self, who: str, query: dict) -> None:
        as_of = query.get("as_of", [None])[0]
        as_of = int(as_of) if as_of not in (None, "") else None
        seconds = float(query.get("seconds", [config.TOTAL_SECONDS])[0])
        want_audio = query.get("audio", ["1"])[0] not in ("0", "false", "")

        if who == "synthetic":
            label = f"synthetic-{as_of if as_of is not None else 'latest'}"
            # The fixture path goes through recap.build, which takes no cache —
            # caching lives in from_api, keyed on a live game's cursor. Without
            # this the fixture re-synthesizes on every request, 20 seconds a
            # time, and the device times out waiting for a demo recap.
            key = cache.key(0, as_of, seconds, want_audio)
            manifest = cache.get(key)
            if manifest is None:
                context, plays = fixtures.load_synthetic()
                synth = self._synth(label) if want_audio else None
                manifest = recap.build(context, plays, as_of=as_of,
                                       total_seconds=seconds, synth=synth)
                if recap.cacheable(manifest):
                    cache.put(key, manifest)
        else:
            game_pk = int(who)
            replay = getattr(self.server, "replay", None)
            if replay is not None and replay.game_pk == game_pk and as_of is None:
                if replay.last_index is None:
                    # Where the real game ends, so the clock can hold there
                    # rather than ask for at-bats the feed never had. It has
                    # to come from the feed: taking it from the manifest this
                    # request is about to build reads back the replay's own
                    # cursor, which pins the clock to wherever it already is
                    # and the recap never changes again.
                    replay.last_index = mlb.context(game_pk).cursor
                # The replay clock decides where "now" is. Everything
                # downstream is unchanged: this is the same as_of a live game
                # would produce, so the live path is genuinely exercised
                # rather than imitated.
                as_of = replay.cursor()
            label = f"{game_pk}-{as_of if as_of is not None else 'latest'}"
            synth = self._synth(label) if want_audio else None
            manifest = recap.from_api(game_pk, as_of=as_of,
                                      total_seconds=seconds, synth=synth)
            if replay is not None and replay.game_pk == game_pk:
                manifest["replay"] = replay.describe()

        # A filesystem path is useless to the device. Rewrite it to a URL on
        # this server, which is what the app will actually fetch.
        if manifest.get("audioUrl"):
            name = Path(manifest["audioUrl"]).name
            manifest["audioUrl"] = f"{self._base()}/audio/{label}/{name}"
        self._json(200, manifest)

    def _with_replay(self, games: list[dict]) -> list[dict]:
        """Promote the replayed game to the top and mark it live.

        catalog.playable has already decided the order; this only overrides
        the one game the replay clock is driving, so the ordering rule stays
        in one place.
        """
        replay = getattr(self.server, "replay", None)
        if replay is None:
            return games
        target = str(replay.game_pk)
        rest, found = [], None
        for game in games:
            if game["id"] == target:
                found = {**game, "live": True, "playable": True,
                         "abstract": "Live", "status": "In Progress (replay)"}
            else:
                rest.append(game)
        if found is None:
            # The replayed game is not on today's slate — an old game being
            # played back — so it is prepended rather than reordered, and its
            # names come from the feed. Falling back to "?" put a nameless row
            # at the top of the list, which is the one row the viewer is most
            # likely to pick.
            try:
                context = mlb.context(replay.game_pk)
                # The same names the recap header will show a moment later.
                # The schedule endpoint returns full club names and the feed
                # returns short ones, so this row cannot match both; matching
                # the screen the viewer lands on beats matching the rows they
                # are about to leave.
                away, home = context.away_name, context.home_name
            except mlb.FeedError:
                away = home = "?"
            found = {"id": target, "away": away, "home": home,
                     "status": "In Progress (replay)", "abstract": "Live",
                     "series": "Replay", "playable": True, "live": True}
        return [found, *rest]

    def _synth(self, label: str):
        return recap.kokoro_synth(config.WORK / label, progress=True)

    def _audio(self, relative: str) -> None:
        path = (config.WORK / relative).resolve()
        # Containment check: the path comes off the wire, so a ../ in it must
        # not be able to serve an arbitrary file from this machine.
        if not str(path).startswith(str(config.WORK.resolve())):
            return self._json(403, {"error": "outside the audio directory"})
        if not path.exists():
            return self._json(404, {"error": f"no audio at {relative}"})

        kinds = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}
        content_type = kinds.get(path.suffix, "application/octet-stream")
        data = path.read_bytes()
        total = len(data)

        # Range support is not optional for a media element. Vega's player
        # probes the source before committing to it, and against a server that
        # answers every request with the whole file it reported duration=NaN,
        # paused=true and an error with no timeupdate ever firing — which looks
        # exactly like a codec problem and is not one.
        requested = self.headers.get("Range")
        if requested and requested.startswith("bytes="):
            span = requested.removeprefix("bytes=").split("-", 1)
            try:
                start = int(span[0]) if span[0] else 0
                end = int(span[1]) if len(span) > 1 and span[1] else total - 1
            except ValueError:
                return self._json(400, {"error": f"bad Range {requested}"})
            if start >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.end_headers()
                return
            end = min(end, total - 1)
            chunk = data[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(chunk)
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(total))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _base(self) -> str:
        host = (self.headers.get("Host")
                or f"{lan_address()}:{self.server.server_port}")
        # The scheme has to follow the listener. An http:// audio URL is not
        # merely suboptimal on Vega, it is unplayable.
        scheme = "https" if getattr(self.server, "is_tls", False) else "http"
        return f"{scheme}://{host}"


def serve(port: int = 8080, use_tls: bool = False,
          replay: Replay | None = None) -> None:
    address = lan_address()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    scheme = "http"
    server.is_tls = False
    server.replay = replay

    if use_tls:
        cert, key = ensure_cert()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert, keyfile=key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        server.is_tls = True
        scheme = "https"

    print(f"catchup60 serving on port {port} ({scheme})")
    if replay is not None:
        print(f"  REPLAY: game {replay.game_pk} as live, "
              f"one at-bat every {replay.seconds_per_at_bat:.0f}s, "
              f"starting at at-bat {replay.head_start}")
    print(f"  from this Mac:        {scheme}://localhost:{port}/recap/synthetic")
    print(f"  from the Vega device: {scheme}://10.0.2.2:{port}/recap/synthetic")
    print(f"  on the LAN:           {scheme}://{address}:{port}/recap/synthetic")
    print("  Ctrl-C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
