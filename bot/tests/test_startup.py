import asyncio
import logging

from bot.config import env_seconds
from bot.main import StartupConflictFilter, wait_for_old_instance


def record(message, level=logging.ERROR):
    return logging.LogRecord('aiogram.dispatcher', level, __file__, 1, message, None, None)


def test_the_first_conflict_after_start_is_one_info_line_and_the_retries_are_dropped():
    now = [100.0]
    flt = StartupConflictFilter(grace=60, clock=lambda: now[0])
    first = record('Failed to fetch updates - TelegramConflictError: Conflict: terminated by other getUpdates request')
    assert flt.filter(first)
    assert first.levelno == logging.INFO
    assert 'TelegramConflictError' in first.getMessage()
    assert not flt.filter(record('Failed to fetch updates - TelegramConflictError: Conflict'))
    assert not flt.filter(record('Sleep for 1.000000 seconds and try again...', logging.WARNING))
    other = record('Failed to fetch updates - TelegramNetworkError: timeout')
    assert flt.filter(other) and other.levelno == logging.ERROR


def test_a_conflict_that_outlasts_the_grace_period_is_logged_as_an_error():
    now = [0.0]
    flt = StartupConflictFilter(grace=60, clock=lambda: now[0])
    now[0] = 61.0
    late = record('Failed to fetch updates - TelegramConflictError: Conflict')
    assert flt.filter(late) and late.levelno == logging.ERROR


async def test_the_start_delay_ends_early_on_a_stop_signal():
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(wait_for_old_instance(stop, 30), timeout=1)


def test_start_delay_setting(monkeypatch):
    monkeypatch.delenv('BOT_START_DELAY', raising=False)
    assert env_seconds('BOT_START_DELAY', 15.0) == 15.0
    monkeypatch.setenv('BOT_START_DELAY', '5')
    assert env_seconds('BOT_START_DELAY', 15.0) == 5.0
    monkeypatch.setenv('BOT_START_DELAY', 'soon')
    assert env_seconds('BOT_START_DELAY', 15.0) == 15.0
