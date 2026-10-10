"""End-to-end pipeline invariants.

These are the properties the TV app is built against. A breach here shows up on
screen as a card that changes mid-sentence or a recap that outruns its slot.
"""

import json

import pytest

from src import recap
from src.engine import pack as packer

PROMISE_SECONDS = 60.0


@pytest.fixture
def manifest(synthetic):
    context, plays = synthetic
    return recap.build(context, plays)


class TestManifestShape:
    def test_keeps_the_sixty_second_promise(self, manifest):
        assert manifest["totalSeconds"] <= PROMISE_SECONDS

    def test_segments_are_contiguous(self, manifest):
        """The app animates against one audio track; a gap is a visible defect."""
        segments = manifest["segments"]
        for earlier, later in zip(segments, segments[1:]):
            assert later["start"] == pytest.approx(
                earlier["start"] + earlier["dur"], abs=0.01)

    def test_starts_at_zero(self, manifest):
        assert manifest["segments"][0]["start"] == 0.0

    def test_opens_with_an_intro_and_closes_with_an_outro(self, manifest):
        assert manifest["segments"][0]["kind"] == "intro"
        assert manifest["segments"][-1]["kind"] == "outro"

    def test_estimated_timings_are_labelled_as_estimates(self, manifest):
        """The app is entitled to know it was handed a guess, not real audio."""
        assert manifest["timingSource"] == "estimate"

    def test_play_segments_carry_their_play_index(self, manifest):
        plays = [s for s in manifest["segments"] if s["kind"] == "play"]
        assert plays and all("playIndex" in s for s in plays)

    def test_is_json_serialisable(self, manifest):
        json.loads(json.dumps(manifest))


class TestGuardOnTheTemplatePath:
    def test_the_deterministic_narrator_never_invents_a_figure(self, manifest):
        """It formats engine output, so this must hold for every fixture game."""
        assert manifest["guardViolations"] == []


class TestAsOf:
    def test_truncates_to_the_cursor(self, synthetic):
        context, plays = synthetic
        result = recap.build(context, plays, as_of=10)
        assert result["asOfPlayIndex"] <= 10
        for segment in result["segments"]:
            if segment["kind"] == "play":
                assert segment["playIndex"] <= 10

    def test_state_matches_the_cursor_not_the_final_score(self, synthetic):
        context, plays = synthetic
        early = recap.build(context, plays, as_of=4)
        final = recap.build(context, plays)
        assert early["gameState"]["inning"] <= final["gameState"]["inning"]
        assert early["gameState"]["away"] <= final["gameState"]["away"]

    def test_a_later_cursor_can_change_the_recap(self, synthetic):
        """The product claim: launch it again later and you get a new recap."""
        context, plays = synthetic
        early = recap.build(context, plays, as_of=8)
        later = recap.build(context, plays, as_of=25)
        assert early["segments"] != later["segments"]

    def test_rejects_a_cursor_before_the_first_play(self, synthetic):
        context, plays = synthetic
        with pytest.raises(ValueError):
            recap.build(context, plays, as_of=-1)


class TestDeterminism:
    def test_the_same_cursor_gives_the_same_manifest(self, synthetic):
        """Guards the cache key: a drifting manifest makes caching unsafe."""
        context, plays = synthetic
        first = recap.build(context, plays, as_of=20)
        second = recap.build(context, plays, as_of=20)
        assert json.dumps(first, sort_keys=True) == json.dumps(
            second, sort_keys=True)


class TestRunCoverage:
    def test_reports_how_many_runs_it_explained(self, manifest):
        engine = manifest["engine"]
        assert engine["runsTotal"] > 0
        assert engine["runsExplained"] <= engine["runsTotal"]

    def test_explains_most_of_the_scoring(self, synthetic):
        """Full coverage is not always physically possible inside 60 seconds.

        The fixture game scores 11 runs. Explaining all of them needs roughly
        eight scoring plays, and eight plays at about seven seconds each does
        not fit alongside an intro and an outro. The budget wins, and the
        manifest reports the shortfall rather than hiding it — that honesty is
        what this asserts, together with a floor on how bad it may get.
        """
        context, plays = synthetic
        result = recap.build(context, plays)
        engine = result["engine"]
        assert engine["runsExplained"] / engine["runsTotal"] >= 0.75

    def test_says_truthfully_what_limited_it(self, synthetic):
        """Whoever tunes this needs to be sent to the right knob.

        The fixture game at 60 seconds leaves a run unexplained because there is
        no room for another scoring play, not because it ran out of candidates.
        """
        context, plays = synthetic
        result = recap.build(context, plays)
        engine = result["engine"]
        if engine["runsExplained"] < engine["runsTotal"]:
            assert engine["limitedBy"] in {"budget", "count"}


class TestBudgetFlexibility:
    def test_a_shorter_budget_produces_a_shorter_recap(self, synthetic):
        context, plays = synthetic
        short = recap.build(context, plays, total_seconds=30.0)
        full = recap.build(context, plays, total_seconds=60.0)
        assert short["totalSeconds"] <= 30.0
        assert short["totalSeconds"] < full["totalSeconds"]
