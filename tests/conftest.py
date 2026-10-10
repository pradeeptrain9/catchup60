import pytest

from src import fixtures


@pytest.fixture
def synthetic():
    """The offline game. No network, so every test below can run anywhere."""
    return fixtures.load_synthetic()
