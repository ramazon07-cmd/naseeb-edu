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


async def _unlink(api, cache, pages, chat_id):
    with suppress(ApiError, ApiUnavailable):
        await api.unlink(chat_id)
    cache.drop_chat(chat_id)
    pages.drop_chat(chat_id)


async def deliver(item, *, bot, api, cache, pages, limiter, sleep=asyncio.sleep):
    chat_id, lang = item['chat_id'], item['language']
    sent = False
    for attempt in range(RETRIES + 1):
        try:
            if not sent:
                data = await api.digest(chat_id)
                await limiter.wait()
                await send_digest(bot, chat_id, data, lang, pages)
                sent = True
            await api.mark_sent(chat_id, item['slot_date'])
            return 'sent'
        except ApiError as exc:
            if exc.code != 'not_linked':
                log.warning('digest for a chat failed: backend answered %s', exc.status)
            return 'unlinked' if exc.code == 'not_linked' else 'failed'
        except TelegramForbiddenError:
            await _unlink(api, cache, pages, chat_id)
            return 'blocked'
        except TelegramRetryAfter as exc:
            await sleep(exc.retry_after)
        except TelegramBadRequest as exc:
            if 'chat not found' in str(exc).lower():
                await _unlink(api, cache, pages, chat_id)
                return 'blocked'
            log.warning('telegram refused a digest: %s', type(exc).__name__)
            return 'failed'
        except (TelegramNetworkError, TelegramServerError, ApiUnavailable):
            await sleep(2 ** attempt)
    log.warning('giving up on a digest for now (sent=%s); it is retried while still inside the grace window', sent)
    return 'sent' if sent else 'failed'


async def run_tick(*, bot, api, cache, pages, limiter, sleep=asyncio.sleep, concurrency=CONCURRENCY):
    try:
        items = await api.due()
    except (ApiError, ApiUnavailable) as exc:
        log.warning('could not ask the backend which updates are due: %s', type(exc).__name__)
        return {}
    gate = asyncio.Semaphore(concurrency)
    results = {}

    async def one(item):
        async with gate:
            try:
                results[item['chat_id']] = await deliver(
                    item, bot=bot, api=api, cache=cache, pages=pages, limiter=limiter, sleep=sleep,
                )
            except Exception:
                log.exception('unexpected error while sending a digest')
                results[item['chat_id']] = 'failed'

    await asyncio.gather(*(one(item) for item in items))
    return results


def seconds_to_next_minute(now=None):
    # Tashkent is UTC+5 all year, so its minutes start exactly when UTC minutes do.
    return 60.0 - ((time.time() if now is None else now) % 60.0) + 0.5


async def run_scheduler(stop, **deps):
    """Tick once at startup (the backend's grace window covers a restart), then at every minute start."""
    while not stop.is_set():
        await run_tick(**deps)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=seconds_to_next_minute())
