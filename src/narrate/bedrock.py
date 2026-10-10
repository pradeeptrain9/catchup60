"""Narration phrasing through Claude on Amazon Bedrock.

The model's job here is strictly limited: it rewords sentences the engine has
already written. It does not choose which plays mattered, it does not compute a
score, and it may not introduce a figure the engine did not produce. Those are
the parts a confident wrong answer would ruin, and they stay in Python.

Everything this returns passes through narrate/guard.py before it is spoken. A
rejection costs one corrective retry naming the offending numbers, and then the
deterministic template narrator is used instead — the same three-stage shape
agrin settled on.
"""

import json
import os

from .. import config
from . import guard

# Bedrock model ids carry an `anthropic.` prefix.
MODEL = os.environ.get("CATCHUP60_BEDROCK_MODEL", "anthropic.claude-opus-5")

SYSTEM = """\
You rewrite baseball recap lines so they sound natural read aloud on a TV.

Rules, in order of importance:

1. NEVER write a number that does not appear in the JSON you are given. Not an
   inning, not a score, not a count, not a season total. If you cannot support a
   figure, describe it in words or leave it out.
2. Never change who did what. The batter, the pitcher, the outcome and the
   runners are facts, not phrasing.
3. Keep one line per input line, in the same order. Return exactly as many lines
   as you were given.
4. Shorter is better. These are read against a seven-second card. Drop fielding
   detail that does not change the meaning: "singles on a ground ball to center
   field" can become "singles to center".
5. No invented drama. No "stunning", no "electric", no crowd noise. The facts
   carry it.

Return only JSON, in this exact shape, with no commentary:

{"lines": ["first line", "second line", ...]}
"""


def _aws_ready() -> tuple[bool, str]:
    """Whether boto3 can see usable credentials and a region.

    Wrapped because credential resolution *raises* rather than returning None
    in real configurations — `aws login` sessions need botocore[crt], and
    without it get_credentials() throws MissingDependencyException. An
    availability probe that can raise defeats its own purpose: this is the
    function every caller trusts to tell them whether to fall back.
    """
    try:
        import boto3
    except ImportError:
        return False, "boto3 not installed — pip install -r requirements-aws.txt"

    try:
        session = boto3.Session()
        credentials = session.get_credentials()
    except Exception as exc:
        return False, f"AWS credentials unusable: {type(exc).__name__}: {exc}"

    if credentials is None:
        return False, "no AWS credentials — aws login, or aws configure"

    if not _region():
        return False, "no AWS region — aws configure set region us-east-1"
    return True, ""


def available() -> tuple[bool, str]:
    """Whether a Bedrock call could succeed, and if not, why.

    Credentials are not exercised against the network here — that costs a round
    trip, and a recap must never block on one. A failure at call time falls back
    to the template narrator like any other rejection.
    """
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "anthropic not installed — pip install -r requirements-aws.txt"
    return _aws_ready()


def _region() -> str | None:
    """The region boto3 would use, not merely the one in the environment.

    `aws configure set region` writes ~/.aws/config, which boto3 reads and the
    Anthropic SDK does not. Looking only at AWS_REGION meant the availability
    probe passed — it asks boto3 — and the client constructor then failed with
    "No AWS region or base URL found". Both must agree on where region comes
    from, and boto3's resolution is the one the rest of the AWS path uses.
    """
    env = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if env:
        return env
    try:
        import boto3
        return boto3.Session().region_name
    except Exception:
        return None


def _client():
    from anthropic import AnthropicBedrockMantle
    region = _region()
    if not region:
        raise RuntimeError(
            "no AWS region — aws configure set region us-east-1"
        )
    return AnthropicBedrockMantle(aws_region=region)


def _ask(client, messages: list[dict]) -> list[str]:
    """One call. Returns the rewritten lines, or raises."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=SYSTEM,
        # Rewording short sentences does not need deep reasoning, and effort is
        # the first lever on cost.
        output_config={"effort": "low"},
        messages=messages,
    )
    text = "".join(
        block.text for block in response.content if block.type == "text"
    ).strip()
    # The model is told to return only JSON, but a stray fence is cheap to
    # survive and expensive to debug in a demo.
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    lines = parsed["lines"]
    if not isinstance(lines, list) or not all(isinstance(x, str) for x in lines):
        raise ValueError("lines was not a list of strings")
    return lines


def rephrase(segments: list[dict], payload: dict) -> tuple[list[dict], str | None]:
    """Reword segments, or give up and say why.

    Returns (segments, fallback_reason). On any failure the segments come back
    unchanged and the reason is set, so the caller can record what happened
    rather than silently serving a different narrator than it reports.
    """
    ok, reason = available()
    if not ok:
        return segments, reason

    request = {
        "lines": [segment["text"] for segment in segments],
        "facts": payload,
    }
    messages = [{"role": "user", "content": json.dumps(request)}]

    try:
        client = _client()
    except Exception as exc:  # credentials, region, import — all non-fatal
        # The message matters more than the type. "AnthropicError" sent a
        # debugging session looking at credentials when the real answer was a
        # 403 naming an ungranted model.
        return segments, f"bedrock client: {type(exc).__name__}: {exc}"

    for attempt in (1, 2):
        try:
            lines = _ask(client, messages)
        except Exception as exc:
            return segments, f"bedrock call: {type(exc).__name__}: {exc}"

        if len(lines) != len(segments):
            # A dropped line desyncs every card after it, so this is a hard
            # rejection rather than something to patch up.
            return segments, (
                f"bedrock returned {len(lines)} lines for {len(segments)} segments"
            )

        candidate = [
            {**segment, "text": line} for segment, line in zip(segments, lines)
        ]
        violations = guard.check_segments(candidate, payload)
        if not violations:
            return candidate, None

        if attempt == 1:
            # One corrective round that names the offending figures back to the
            # model, exactly as agrin does. Blind retries do not help.
            messages = messages + [
                {"role": "assistant", "content": json.dumps({"lines": lines})},
                {"role": "user", "content": (
                    "Those lines used numbers that are not in the facts:\n"
                    + "\n".join(f"- {v}" for v in violations)
                    + "\n\nRewrite them using only figures that appear in the "
                      "JSON. If you cannot support a quantity, describe it in "
                      "words instead of giving a number."
                )},
            ]
            continue

        return segments, "narration failed the numeric guard twice"

    return segments, "bedrock exhausted retries"
