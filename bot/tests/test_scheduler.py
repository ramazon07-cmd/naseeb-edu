import asyncio

from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from bot.api import ApiError, ApiUnavailable
from bot.scheduler import RateLimiter, run_scheduler, run_tick, seconds_to_next_minute

ITEM = {'chat_id': 1, 'language': 'en', 'slot_date': '2026-11-08'}


class Sleeps:
    def __init__(self):
        self.delays = []

    async def __call__(self, seconds):
        self.delays.append(seconds)


def deps(h, sleeps=None):
    sleeps = sleeps or Sleeps()
    return dict(bot=h.bot, api=h.api, cache=h.cache, pages=h.pages, limiter=RateLimiter(sleep=sleeps), sleep=sleeps)


def students_digest():
    return {'date': '2026-11-08', 'total_students': 1, 'omitted': 0, 'students': [
        {'name': 'Ali', 'grade': '9', 'essays': {'total': 1, 'edited_today': 0, 'words_today': None}},
    ]}


async def test_sends_once_and_marks_sent(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1
    assert h.api.names('mark_sent') == [{'chat_id': 1, 'slot_date': '2026-11-08'}]
    # the backend hands the chat out once: a second tick has nothing to send
    assert await run_tick(**deps(h)) == {}
    assert len(h.session.of('SendMessage')) == 1


async def test_blocked_bot_unlinks_and_does_not_mark_sent(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    h.session.failures['SendMessage'] = [TelegramForbiddenError(method=None, message='Forbidden: bot was blocked by the user')]
    assert await run_tick(**deps(h)) == {1: 'blocked'}
    assert h.api.names('unlink') == [{'chat_id': 1}]
    assert not h.api.names('mark_sent')


async def test_transient_telegram_failure_is_retried_with_backoff(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    h.session.failures['SendMessage'] = [TelegramNetworkError(method=None, message='boom')] * 2
    sleeps = Sleeps()
    assert await run_tick(**deps(h, sleeps)) == {1: 'sent'}
    assert [d for d in sleeps.delays if d >= 1] == [1, 2]
    assert len(h.api.names('mark_sent')) == 1


async def test_flood_control_waits_the_time_telegram_asks(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    h.session.failures['SendMessage'] = [TelegramRetryAfter(method=None, message='flood', retry_after=7)]
    sleeps = Sleeps()
    assert await run_tick(**deps(h, sleeps)) == {1: 'sent'}
    assert 7 in sleeps.delays


async def test_after_the_digest_went_out_only_mark_sent_is_retried(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    state = {'n': 0}
    original = h.api.mark_sent

    async def flaky(chat_id, slot_date):
        state['n'] += 1
        if state['n'] == 1:
            raise ApiUnavailable('timeout')
        return await original(chat_id, slot_date)

    h.api.mark_sent = flaky
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1
    assert state['n'] == 2


async def test_a_failed_mark_sent_never_sends_the_digest_twice(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    h.api.errors['mark_sent'] = ApiUnavailable('timeout')
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1
    # the backend hands the chat out again because last_sent_date never moved
    h.api.due_items = [ITEM]
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1
    h.api.errors.pop('mark_sent')
    h.api.due_items = [ITEM]
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1
    assert h.api.names('mark_sent')[-1] == {'chat_id': 1, 'slot_date': '2026-11-08'}


async def test_a_refused_mark_sent_after_delivery_is_not_reported_as_failed(h):
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    h.api.errors['mark_sent'] = ApiError(400, 'bad_request')
    assert await run_tick(**deps(h)) == {1: 'sent'}
    assert len(h.session.of('SendMessage')) == 1


async def test_backend_down_for_due_is_survived(h):
    h.api.errors['due'] = ApiUnavailable('timeout')
    assert await run_tick(**deps(h)) == {}


async def test_unlinked_chat_is_skipped(h):
    h.api.due_items = [ITEM]
    h.api.errors['digest'] = ApiError(404, 'not_linked')
    assert await run_tick(**deps(h)) == {1: 'unlinked'}
    assert not h.session.of('SendMessage') and not h.api.names('mark_sent')


async def test_one_bad_chat_does_not_stop_the_others(h):
    h.api.due_items = [ITEM, {**ITEM, 'chat_id': 2}]
    h.api.digest_data = students_digest()
    h.session.failures['SendMessage'] = [TelegramForbiddenError(method=None, message='blocked')]
    results = await run_tick(**deps(h))
    assert sorted(results.values()) == ['blocked', 'sent']


async def test_concurrency_is_capped(h):
    items = [{**ITEM, 'chat_id': n} for n in range(1, 31)]
    h.api.due_items = items
    running = {'now': 0, 'max': 0}
    original = h.api.digest

    async def slow(chat_id):
        running['now'] += 1
        running['max'] = max(running['max'], running['now'])
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        running['now'] -= 1
        return students_digest()

    h.api.digest = slow
    results = await run_tick(**deps(h), concurrency=5)
    assert len(results) == 30 and running['max'] <= 5
    h.api.digest = original


async def test_rate_limiter_spaces_sends():
    clock = {'t': 100.0}
    slept = []

    async def fake_sleep(seconds):
        slept.append(round(seconds, 4))
        clock['t'] += seconds

    limiter = RateLimiter(per_second=25, clock=lambda: clock['t'], sleep=fake_sleep)
    for _ in range(26):
        await limiter.wait()
    assert slept[0] == 0.04 and len(slept) == 25
    assert abs(sum(slept) - 1.0) < 0.01


def test_wakes_just_after_the_start_of_the_next_minute():
    assert seconds_to_next_minute(120.0 + 20) == 40.5
    assert seconds_to_next_minute(119.5) == 1.0


async def test_scheduler_loop_ticks_at_start_and_stops_cleanly(h):
    stop = asyncio.Event()
    h.api.due_items = [ITEM]
    h.api.digest_data = students_digest()
    task = asyncio.create_task(run_scheduler(stop, **deps(h)))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert len(h.session.of('SendMessage')) == 1


async def test_an_unexpected_error_asking_for_due_chats_is_survived(h):
    h.api.errors['due'] = KeyError('chats')
    assert await run_tick(**deps(h)) == {}


async def test_the_scheduler_loop_keeps_running_after_a_tick_raises(h, monkeypatch):
    import bot.scheduler as scheduler

    stop = asyncio.Event()
    ticks = []

    async def broken_tick(**_):
        ticks.append(1)
        if len(ticks) == 2:
            stop.set()
        raise RuntimeError('boom')

    monkeypatch.setattr(scheduler, 'run_tick', broken_tick)
    monkeypatch.setattr(scheduler, 'seconds_to_next_minute', lambda now=None: 0)
    await asyncio.wait_for(run_scheduler(stop, **deps(h)), timeout=2)
    assert len(ticks) == 2
