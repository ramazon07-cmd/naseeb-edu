import asyncio
import logging
import time
from contextlib import suppress

from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError,
)

from .api import ApiError, ApiUnavailable
from .delivery import send_digest

log = logging.getLogger('bot.scheduler')

SEND_RATE = 25
CONCURRENCY = 10
RETRIES = 3


class RateLimiter:
    """Spaces sends so the bot stays under Telegram's ~30 messages per second."""

    def __init__(self, per_second=SEND_RATE, clock=time.monotonic, sleep=asyncio.sleep):
        self._gap = 1 / per_second
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = self._clock()
            delay = self._next - now
            self._next = max(now, self._next) + self._gap
        if delay > 0:
            await self._sleep(delay)


async def _unlink(api, cache, chat_id):
    with suppress(ApiError, ApiUnavailable):
        await api.unlink(chat_id)
    cache.drop_chat(chat_id)


_DELIVERED = set()


async def deliver(item, *, bot, api, cache, limiter, sleep=asyncio.sleep):
    chat_id, lang = item['chat_id'], item['language']
    key = (chat_id, item['slot_date'])
    sent = key in _DELIVERED
    for attempt in range(RETRIES + 1):
        try:
            if not sent:
                data = await api.digest(chat_id)
                await limiter.wait()
                await send_digest(bot, chat_id, data, lang)
                sent = True
                if len(_DELIVERED) > 10000:
                    _DELIVERED.clear()
                _DELIVERED.add(key)
            try:
                await api.mark_sent(chat_id, item['slot_date'])
            except ApiError as exc:
                if exc.code == 'not_linked':
                    raise
                log.warning('digest delivered but mark-sent was refused: backend answered %s', exc.status)
                return 'sent'
            _DELIVERED.discard(key)
            return 'sent'
        except ApiError as exc:
            if exc.code != 'not_linked':
                log.warning('digest for a chat failed: backend answered %s', exc.status)
            return 'unlinked' if exc.code == 'not_linked' else 'failed'
        except TelegramForbiddenError:
            await _unlink(api, cache, chat_id)
            return 'blocked'
        except TelegramRetryAfter as exc:
            await sleep(exc.retry_after)
        except TelegramBadRequest as exc:
            if 'chat not found' in str(exc).lower():
                await _unlink(api, cache, chat_id)
                return 'blocked'
            log.warning('telegram refused a digest: %s', type(exc).__name__)
            return 'failed'
        except (TelegramNetworkError, TelegramServerError, ApiUnavailable):
            await sleep(2 ** attempt)
    log.warning('giving up on a digest for now (sent=%s); it is retried while still inside the grace window', sent)
    return 'sent' if sent else 'failed'


async def run_tick(*, bot, api, cache, limiter, sleep=asyncio.sleep, concurrency=CONCURRENCY):
    try:
        items = await api.due()
    except (ApiError, ApiUnavailable) as exc:
        log.warning('could not ask the backend which updates are due: %s', type(exc).__name__)
        return {}
    except Exception:
        log.exception('unexpected error while asking the backend which updates are due')
        return {}
    gate = asyncio.Semaphore(concurrency)
    results = {}

    async def one(item):
        async with gate:
            try:
                results[item['chat_id']] = await deliver(
                    item, bot=bot, api=api, cache=cache, limiter=limiter, sleep=sleep,
                )
            except Exception:
                log.exception('unexpected error while sending a digest')
                results[item['chat_id']] = 'failed'

    await asyncio.gather(*(one(item) for item in items))
    return results


async def _acknowledge(api, unacked):
    """Report sent and blocked messages; on failure they are kept and reported on the next minute."""
    if not (unacked['sent'] or unacked['blocked']):
        return True
    try:
        await api.student_outbox_ack(unacked['sent'], sorted(unacked['blocked']))
    except (ApiError, ApiUnavailable) as exc:
        log.warning('student messages sent but not acknowledged yet: %s', type(exc).__name__)
        return False
    unacked['sent'], unacked['blocked'] = [], set()
    return True


async def deliver_student_messages(*, bot, api, limiter, sleep=asyncio.sleep, unacked=None, **_):
    """Students' meeting messages and reminders: fetched, sent, and reported back every minute.

    A message that fails for a passing reason stays unsent and is handed out again after the
    backend's lease; a chat that blocked the bot is reported so nothing more is queued for it.
    `unacked` lives across minutes: what could not be reported is reported first next time, before
    the backend's lease runs out and hands the same messages out again.
    """
    unacked = {'sent': [], 'blocked': set()} if unacked is None else unacked
    if not await _acknowledge(api, unacked):
        return {'sent': 0, 'blocked': 0}
    try:
        messages = await api.student_outbox()
    except (ApiError, ApiUnavailable) as exc:
        log.warning('could not fetch student messages: %s', type(exc).__name__)
        return {'sent': 0, 'blocked': 0}
    sent, blocked = [], set()
    for message in messages:
        chat_id = message['chat_id']
        if chat_id in blocked:
            continue
        for _ in range(2):
            try:
                await limiter.wait()
                await bot.send_message(chat_id, message['text'], disable_web_page_preview=True)
                sent.append(message['id'])
                break
            except TelegramRetryAfter as exc:
                await sleep(exc.retry_after)
            except TelegramForbiddenError:
                blocked.add(chat_id)
                break
            except TelegramBadRequest as exc:
                if 'chat not found' in str(exc).lower():
                    blocked.add(chat_id)
                else:
                    log.warning('telegram refused a student message: %s', type(exc).__name__)
                    sent.append(message['id'])  # it would be refused again; do not retry it
                break
            except (TelegramNetworkError, TelegramServerError):
                break
    unacked['sent'] += sent
    unacked['blocked'] |= blocked
    await _acknowledge(api, unacked)
    return {'sent': len(sent), 'blocked': len(blocked)}


# The backend's scheduled jobs (queueing meeting reminders hourly; notifications and cleanups
# daily), asked for from here once an hour at minute 5 so no cron service is needed.
# The backend picks what is due and locks each job, so a restart or two instances
# during a deploy never run one twice.
REMINDER_MINUTE = 5


class HourlyJob:
    """Starts `job` at most once per UTC hour, at or after `minute`, in the background."""

    def __init__(self, job, minute=REMINDER_MINUTE, clock=time.time):
        self._job = job
        self._minute = minute
        self._clock = clock
        self._last_hour = None
        self.task = None

    def maybe_start(self):
        now = self._clock()
        hour, minute = int(now // 3600), int(now % 3600 // 60)
        if minute < self._minute or hour == self._last_hour or (self.task and not self.task.done()):
            return None
        # One try per hour: a missed hour is harmless, reminders look a whole day ahead.
        self._last_hour = hour
        self.task = asyncio.create_task(self._run())
        return self.task

    async def _run(self):
        try:
            await self._job()
        except (ApiError, ApiUnavailable) as exc:
            log.warning('scheduled jobs were not run this hour: %s', type(exc).__name__)
        except Exception:
            log.exception('unexpected error while running scheduled jobs')


class BackgroundJob:
    """Starts `job` in the background whenever asked, unless its last run is still going."""

    def __init__(self, job, label):
        self._job = job
        self._label = label
        self.task = None

    def maybe_start(self):
        if self.task and not self.task.done():
            return None
        self.task = asyncio.create_task(self._run())
        return self.task

    async def _run(self):
        try:
            await self._job()
        except (ApiError, ApiUnavailable) as exc:
            log.warning('%s were not handled this minute: %s', self._label, type(exc).__name__)
        except Exception:
            log.exception('unexpected error in %s', self._label)


def seconds_to_next_minute(now=None):
    # Tashkent is UTC+5 all year, so its minutes start exactly when UTC minutes do.
    return 60.0 - ((time.time() if now is None else now) % 60.0) + 0.5


async def run_scheduler(stop, **deps):
    """Tick once at startup (the backend's grace window covers a restart), then at every minute start."""
    reminders = deps.pop('reminders', None) or HourlyJob(deps['api'].scheduled_jobs)
    # Meeting emails are queued by the website and the hourly job; the backend sends them when
    # asked, every minute, in the background so a slow mail server never delays Telegram sends.
    mail = deps.pop('mail', None) or BackgroundJob(deps['api'].send_meeting_emails, 'meeting emails')
    unacked = {'sent': [], 'blocked': set()}
    try:
        while not stop.is_set():
            reminders.maybe_start()
            mail.maybe_start()
            # Meeting messages first: a reminder is due at its minute, a digest can wait for the sends before it.
            try:
                await deliver_student_messages(**deps, unacked=unacked)
            except Exception:
                log.exception('student messages failed; trying again next minute')
            try:
                await run_tick(**deps)
            except Exception:
                log.exception('scheduler tick failed; trying again next minute')
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=seconds_to_next_minute())
    finally:
        for job in (reminders, mail):
            if job.task and not job.task.done():
                job.task.cancel()
                with suppress(asyncio.CancelledError):
                    await job.task
