import pytest

from bot import scheduler

from .helpers import Harness


@pytest.fixture(autouse=True)
def _no_delivered_leftovers():
    scheduler._DELIVERED.clear()
    yield
    scheduler._DELIVERED.clear()


@pytest.fixture
def h():
    harness = Harness()
    yield harness
    harness.close()
