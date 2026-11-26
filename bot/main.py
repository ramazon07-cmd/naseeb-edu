import argparse
import asyncio
import logging
import re
import signal
import sys
import time
from contextlib import suppress

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from .api import ApiClient
from .cache import TtlCache
from .config import load_config
from .handlers import router
from .i18n import DEFAULT, LANGUAGES, MENU
from .scheduler import RateLimiter, run_scheduler

log = logging.getLogger('bot')
ALLOWED_UPDATES = ['message', 'callback_query', 'my_chat_member']
POLLING_TIMEOUT = 10  # seconds Telegram holds a getUpdates open; also how long a stopped instance still blocks the next one
CONFLICT_GRACE = 60.0  # seconds after start in which a getUpdates conflict is the old instance still shutting down
TOKEN_PATTERN = re.compile(r'\d{6,}:[A-Za-z0-9_-]{20,}')


class RedactingFormatter(logging.Formatter):
    """Masks the bot token and service key in every line, tracebacks included."""

    def __init__(self, secrets, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._secrets = [s for s in secrets if s]

    def format(self, record):
        text = TOKEN_PATTERN.sub('<token>', super().format(record))
        for secret in self._secrets:
            text = text.replace(secret, '<secret>')
        return text


class StartupConflictFilter(logging.Filter):
    """On a deploy the old instance polls for a moment longer: aiogram logs that as an error every few seconds.

    Within `grace` seconds of start the first conflict becomes one info line and the retries are dropped; after
    that (a second instance really is running) everything is logged as usual.
    """

    def __init__(self, grace=CONFLICT_GRACE, clock=time.monotonic):
        super().__init__()
        self._grace = grace
        self._clock = clock
        self._started = clock()
        self._reported = False

    def filter(self, record):
        if self._clock() - self._started > self._grace:
            return True
        message = record.getMessage()
        if 'TelegramConflictError' in message:
            if self._reported:
                return False
            self._reported = True
            record.levelno, record.levelname = logging.INFO, 'INFO'
            record.msg, record.args = 'another instance is still polling (a deploy overlap); retrying quietly: %s', (message,)
            return True
        if self._reported and message.startswith('Sleep for '):
            return False
        return True


async def wait_for_old_instance(stop, delay):
    """Give the previous instance time to stop polling; returns early when asked to stop."""
    if delay <= 0:
        return
    log.info('waiting %.0f s for a previous instance to stop polling', delay)
    with suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=delay)


def setup_logging(config):
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(
        [config.token, config.service_key], '%(asctime)s %(levelname)s %(name)s: %(message)s',
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('aiogram.dispatcher').addFilter(StartupConflictFilter())


async def set_menu(bot):
    """The "Menu" button's command list, in each language Telegram users can have."""
    for lang in LANGUAGES:
        commands = [BotCommand(command=name, description=text) for name, text in MENU[lang]]
        with suppress(TelegramAPIError):
            await bot.set_my_commands(commands, language_code=None if lang == DEFAULT else lang)


async def run(config, run_for=None):
    http = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=config.http_timeout, connect=3), connector=aiohttp.TCPConnector(limit=30),
    )
    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    api = ApiClient(config.backend_url, config.service_key, http)
    cache = TtlCache(config.cache_seconds)
    dp = Dispatcher(storage=MemoryStorage(), api=api, cache=cache)
    dp.include_router(router)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    scheduler = None
    polling = None
    failed = False
    try:
        me = await bot.get_me()
        log.info('authenticated with Telegram as @%s', me.username)
        await set_menu(bot)
        await wait_for_old_instance(stop, 0 if run_for is not None else config.start_delay)
        if stop.is_set():
            return True
        scheduler = asyncio.create_task(run_scheduler(
            stop, bot=bot, api=api, cache=cache, limiter=RateLimiter(),
        ))
        polling = asyncio.create_task(dp.start_polling(
            bot, allowed_updates=ALLOWED_UPDATES, handle_signals=False, close_bot_session=False,
            polling_timeout=POLLING_TIMEOUT,
        ))
        if run_for is not None:
            loop.call_later(run_for, stop.set)
        stopped = asyncio.create_task(stop.wait())
        done, _ = await asyncio.wait({stopped, scheduler, polling}, return_when=asyncio.FIRST_COMPLETED)
        stopped.cancel()
        for task in (scheduler, polling):
            if task in done and not stop.is_set():
                failed = True
                error = None if task.cancelled() else task.exception()
                log.error('a background task ended unexpectedly, exiting so the worker is restarted', exc_info=error)
        log.info('shutting down')
    finally:
        with_timeout = 10
        if polling is not None:
            with suppress(RuntimeError):
                await dp.stop_polling()
            await asyncio.wait({polling}, timeout=with_timeout)
        if scheduler is not None:
            stop.set()
            await asyncio.wait({scheduler}, timeout=with_timeout)
        for task in (polling, scheduler):
            if task is not None and not task.done():
                task.cancel()
        await bot.session.close()
        await http.close()
    return not failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-for', type=float, default=None, help='exit cleanly after this many seconds (smoke test)')
    args = parser.parse_args()
    config = load_config()
    setup_logging(config)
    if not asyncio.run(run(config, args.run_for)):
        sys.exit(1)


if __name__ == '__main__':
    main()
