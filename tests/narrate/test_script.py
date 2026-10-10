"""The deterministic narrator.

It formats engine output, so what is tested here is the text handling: the one
place a real StatsAPI quirk leaks into what a viewer hears.
"""

from src.engine.state import GameContext, GameState
from src.narrate import script

CONTEXT = GameContext(
    game_pk=1, away_abbr="PHI", home_abbr="NYM", away_name="Phillies",
    home_name="Mets", detailed_state="In Progress", abstract_state="Live",
)
STATE = GameState(inning=7, half="bottom", away_score=4, home_score=2, outs=1)


class TestCleanDescription:
    def test_strips_a_challenged_call_preamble(self):
        """A reviewed play is a real play; the review bookkeeping is not.

        Without this, a recap opens with "Mets challenged (tag play), call on
        the field was upheld" instead of the sacrifice fly that scored the run.
        """
        raw = ("Mets challenged (tag play), call on the field was upheld: "
               "Luis Arraez out on a sacrifice fly to left fielder Juan Soto. "
               "Bryce Harper scores.")
        assert script.clean_description(raw) == (
            "Luis Arraez out on a sacrifice fly to left fielder Juan Soto. "
            "Bryce Harper scores.")

    def test_strips_an_overturned_call_preamble(self):
        raw = ("Phillies challenged (force play), call on the field was "
               "overturned: Trea Turner safe at second.")
        assert script.clean_description(raw) == "Trea Turner safe at second."

    def test_strips_an_umpire_review(self):
        raw = "Umpire review (home run): Ada Boateng homers (14)."
        assert script.clean_description(raw) == "Ada Boateng homers (14)."

    def test_leaves_an_ordinary_description_alone(self):
        raw = "Kyle Schwarber walks."
        assert script.clean_description(raw) == raw

    def test_adds_terminal_punctuation(self):
        assert script.clean_description("Kyle Schwarber walks").endswith(".")

    def test_survives_empty_input(self):
        assert script.clean_description("") == ""


class TestLines:
    def test_intro_states_the_current_score(self):
        text = script.intro_text(CONTEXT, STATE)
        assert "Bottom of the 7th" in text
        assert "Phillies 4" in text and "Mets 2" in text

    def test_intro_spells_out_no_counts(self):
        """The guard checks digits, not words, so a spelled count is unverifiable."""
        text = script.intro_text(CONTEXT, STATE)
        for word in ("one", "two", "three", "four", "five", "six", "seven"):
            assert word not in text.lower().split()

    def test_outro_closes_on_the_score(self):
        assert "Back to live" in script.outro_text(CONTEXT, STATE)
