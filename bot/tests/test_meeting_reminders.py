import asyncio
import logging

from bot.api import ApiUnavailable
from bot.scheduler import HourlyJob

HOUR = 3600


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at


async def finished(job):
    task = job.maybe_start()
    if task:
        await task
    return task is not None


async def test_runs_once_an_hour_from_minute_five():
    calls = []

    async def remind():
        calls.append(1)

    clock = Clock(10 * HOUR + 4 * 60)  # 10:04
    job = HourlyJob(remind, clock=clock)
    assert not await finished(job)
    clock.at = 10 * HOUR + 5 * 60  # 10:05
    assert await finished(job)
    clock.at = 10 * HOUR + 40 * 60  # still 10:xx
    assert not await finished(job)
    clock.at = 11 * HOUR + 7 * 60  # next hour
    assert await finished(job)
    assert len(calls) == 2


async def test_a_backend_error_is_logged_and_waits_for_the_next_hour(caplog):
    calls = []

    async def remind():
        calls.append(1)
        raise ApiUnavailable('timeout')

    clock = Clock(10 * HOUR + 6 * 60)
    job = HourlyJob(remind, clock=clock)
    with caplog.at_level(logging.WARNING):
        assert await finished(job)
    assert 'meeting reminders were not run' in caplog.text
    clock.at += 60
    assert not await finished(job)
    assert calls == [1]


async def test_a_slow_run_is_not_started_twice():
    gate = asyncio.Event()

    async def remind():
        await gate.wait()

    clock = Clock(10 * HOUR + 6 * 60)
    job = HourlyJob(remind, clock=clock)
    first = job.maybe_start()
    clock.at = 11 * HOUR + 6 * 60
    assert job.maybe_start() is None  # the 10:xx run is still going
    gate.set()
    await first
    assert job.maybe_start() is not None
    await job.task


async def test_the_scheduler_starts_the_reminders(h):
    from bot.scheduler import RateLimiter, run_scheduler

    stop = asyncio.Event()
    reminders = HourlyJob(h.api.meeting_reminders, clock=Clock(10 * HOUR + 6 * 60))
    task = asyncio.create_task(run_scheduler(
        stop, bot=h.bot, api=h.api, cache=h.cache, limiter=RateLimiter(per_second=1000), reminders=reminders,
    ))
    for _ in range(100):
        await asyncio.sleep(0.01)
        if h.api.names('meeting_reminders') and h.api.names('due'):
            break
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert h.api.names('meeting_reminders') == [{}]
    assert h.api.names('due')


async def test_the_reminders_call_gets_a_long_timeout():
    from bot.api import REMINDERS_TIMEOUT, ApiClient

    seen = {}

    class Response:
        status = 200

        async def json(self, content_type=None):
            return {'ok': True}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class Session:
        def request(self, method, url, **kwargs):
            seen.update(kwargs)
            return Response()

    assert await ApiClient('https://api.example', 'key', Session()).meeting_reminders() == {'ok': True}
    assert seen['timeout'].total == REMINDERS_TIMEOUT
