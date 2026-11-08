import pytest

from .helpers import Harness


@pytest.fixture
def h():
    harness = Harness()
    yield harness
    harness.close()
