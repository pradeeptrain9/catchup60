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
