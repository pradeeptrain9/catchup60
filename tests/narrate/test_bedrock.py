"""The model reworded it; the guard decides whether anyone hears it.

No network here. What is tested is the control flow around the model, because
that is what protects the viewer from a fluent wrong recap: a rejection costs
one corrective retry, and a second rejection falls back to the deterministic
narrator with the reason recorded.
"""

import pytest

from src import recap
from src.narrate import bedrock

SEGMENTS = [
    {"kind": "intro", "text": "Bottom of the 7th. Phillies 4, Mets 2."},
    {"kind": "play", "text": "Bo Bichette homers (17) on a fly ball.",
     "playIndex": 40},
]
PAYLOAD = {
    "state": {"inning": 7, "away": 4, "home": 2},
    "plays": [{"inning": 6, "runs": 1,
               "description": "Bo Bichette homers (17) on a fly ball."}],
}


# Captured before the autouse fixture below stubs it out: the region tests at
# the bottom of this file exercise the real constructor, not the stub.
REAL_CLIENT = bedrock._client


@pytest.fixture(autouse=True)
def pretend_available(monkeypatch):
    monkeypatch.setattr(bedrock, "available", lambda: (True, ""))
    monkeypatch.setattr(bedrock, "_client", lambda: object())


def answers(*rounds):
    """A fake _ask that returns each round's lines in turn."""
    calls = {"n": 0}

    def ask(client, messages):
        index = calls["n"]
        calls["n"] += 1
        return rounds[min(index, len(rounds) - 1)]

    ask.calls = calls
    return ask


class TestAccepted:
    def test_a_clean_rewrite_is_used(self, monkeypatch):
        monkeypatch.setattr(bedrock, "_ask", answers(
            ["Bottom of the 7th. Phillies 4, Mets 2.",
             "Bichette homers in the 6th."]))
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert reason is None
        assert segments[1]["text"] == "Bichette homers in the 6th."

    def test_segment_metadata_survives_the_rewrite(self, monkeypatch):
        """playIndex drives the card, so losing it desyncs the recap."""
        monkeypatch.setattr(bedrock, "_ask", answers(
            ["Bottom of the 7th.", "Bichette homers."]))
        segments, _ = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert segments[1]["playIndex"] == 40
        assert segments[0]["kind"] == "intro"


class TestGuardRejection:
    def test_an_invented_figure_triggers_one_retry(self, monkeypatch):
        ask = answers(
            ["Bottom of the 7th.", "Bichette homers, his 23rd, in the 5th."],
            ["Bottom of the 7th.", "Bichette homers in the 6th."],
        )
        monkeypatch.setattr(bedrock, "_ask", ask)
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert ask.calls["n"] == 2
        assert reason is None
        assert "23rd" not in segments[1]["text"]

    def test_the_retry_names_the_offending_figures(self, monkeypatch):
        """A blind retry does not help; the model has to be told what was wrong."""
        seen: list[list[dict]] = []

        def ask(client, messages):
            seen.append(messages)
            if len(seen) == 1:
                return ["Bottom of the 7th.", "Bichette homers (23)."]
            return ["Bottom of the 7th.", "Bichette homers."]

        monkeypatch.setattr(bedrock, "_ask", ask)
        bedrock.rephrase(SEGMENTS, PAYLOAD)
        correction = seen[1][-1]["content"]
        assert "23" in correction
        assert "not in the facts" in correction

    def test_two_rejections_fall_back_to_the_template(self, monkeypatch):
        monkeypatch.setattr(bedrock, "_ask", answers(
            ["Bottom of the 7th.", "Bichette homers (23) in the 5th."]))
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert segments == SEGMENTS
        assert "guard" in reason


class TestStructuralRejection:
    def test_a_dropped_line_is_rejected_outright(self, monkeypatch):
        """One missing line desyncs every card after it."""
        monkeypatch.setattr(bedrock, "_ask", answers(["only one line"]))
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert segments == SEGMENTS
        assert "1 lines for 2 segments" in reason

    def test_a_call_failure_is_not_fatal(self, monkeypatch):
        def explode(client, messages):
            raise RuntimeError("throttled")

        monkeypatch.setattr(bedrock, "_ask", explode)
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert segments == SEGMENTS
        assert "throttled" in reason


class TestUnavailable:
    def test_missing_credentials_leave_the_text_alone(self, monkeypatch):
        monkeypatch.setattr(bedrock, "available", lambda: (False, "no creds"))
        segments, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert segments == SEGMENTS
        assert reason == "no creds"


class TestManifestHonesty:
    def test_a_used_rewrite_is_reported_as_bedrock(self, synthetic):
        context, plays = synthetic
        manifest = recap.build(
            context, plays,
            rephrase=lambda segments, payload: (segments, None))
        assert manifest["narrationSource"] == "bedrock"
        assert manifest["narrationFallback"] is None

    def test_a_rejected_rewrite_is_reported_as_template_with_a_reason(
            self, synthetic):
        """Reporting the requested narrator while serving another is a lie."""
        context, plays = synthetic
        manifest = recap.build(
            context, plays,
            rephrase=lambda segments, payload: (segments, "guard rejected it"))
        assert manifest["narrationSource"] == "template"
        assert manifest["narrationFallback"] == "guard rejected it"


class TestAvailabilityNeverRaises:
    """The probe every caller trusts to decide whether to fall back.

    Credential resolution raises in real configurations rather than returning
    None: an `aws login` session without botocore[crt] throws
    MissingDependencyException from inside get_credentials(). A probe that can
    raise defeats its own purpose, and this one took down the whole CLI.
    """

    def test_survives_a_raising_credential_provider(self, monkeypatch):
        import boto3

        class Exploding:
            def get_credentials(self):
                raise RuntimeError("botocore[crt] missing")

            region_name = "us-east-1"

        monkeypatch.setattr(boto3, "Session", lambda: Exploding())
        ok, reason = bedrock._aws_ready()
        assert ok is False
        assert "botocore[crt] missing" in reason

    def test_survives_a_raising_session_constructor(self, monkeypatch):
        import boto3

        def explode():
            raise RuntimeError("no config file")

        monkeypatch.setattr(boto3, "Session", explode)
        ok, reason = bedrock._aws_ready()
        assert ok is False
        assert "no config file" in reason

    def test_reports_missing_credentials_rather_than_claiming_ready(
            self, monkeypatch):
        import boto3

        class NoCreds:
            def get_credentials(self):
                return None

            region_name = "us-east-1"

        monkeypatch.setattr(boto3, "Session", lambda: NoCreds())
        ok, reason = bedrock._aws_ready()
        assert ok is False
        assert "no AWS credentials" in reason

    def test_a_call_failure_message_survives_not_just_its_type(self,
                                                              monkeypatch):
        """"AnthropicError" sent a debug session after credentials when the
        real answer was a 403 naming an ungranted model."""
        monkeypatch.setattr(bedrock, "available", lambda: (True, ""))

        def explode():
            raise RuntimeError("403 anthropic.claude-opus-5 is not available")

        monkeypatch.setattr(bedrock, "_client", explode)
        _, reason = bedrock.rephrase(SEGMENTS, PAYLOAD)
        assert "not available" in reason


class TestRegionResolution:
    """The probe and the client must agree on where the region comes from.

    `aws configure set region` writes ~/.aws/config. boto3 reads it; the
    Anthropic SDK does not. While _client() consulted only AWS_REGION, every
    machine configured that normal way passed the availability probe and then
    failed construction with "No AWS region or base URL found".
    """

    def test_falls_back_to_the_session_region_when_the_env_is_empty(
            self, monkeypatch):
        import boto3

        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

        class Configured:
            region_name = "us-east-1"

        monkeypatch.setattr(boto3, "Session", lambda: Configured())
        assert bedrock._region() == "us-east-1"

    def test_the_environment_wins_when_both_are_set(self, monkeypatch):
        import boto3

        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        monkeypatch.setattr(
            boto3, "Session", lambda: type("S", (), {"region_name": "us-east-1"})()
        )
        assert bedrock._region() == "eu-west-1"

    def test_no_region_anywhere_is_none_not_an_exception(self, monkeypatch):
        import boto3

        monkeypatch.delenv("AWS_REGION", raising=False)
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)

        def explode():
            raise RuntimeError("no config")

        monkeypatch.setattr(boto3, "Session", explode)
        assert bedrock._region() is None

    def test_the_client_refuses_with_a_fix_rather_than_an_sdk_error(
            self, monkeypatch):
        """The SDK's own message names four env vars and no remedy."""
        monkeypatch.setattr(bedrock, "_region", lambda: None)
        with pytest.raises(RuntimeError, match="aws configure set region"):
            REAL_CLIENT()
