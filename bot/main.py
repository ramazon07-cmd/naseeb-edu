import argparse
import asyncio
import logging
import re
import signal

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from .api import ApiClient
from .cache import TtlCache
from .config import load_config
from .handlers import router
from .scheduler import RateLimiter, run_scheduler

log = logging.getLogger('bot')
ALLOWED_UPDATES = ['message', 'callback_query', 'my_chat_member']
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


def setup_logging(config):
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(
        [config.token, config.service_key], '%(asctime)s %(levelname)s %(name)s: %(message)s',
    ))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)


async def run(config, run_for=None):
    http = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=config.http_timeout, connect=3), connector=aiohttp.TCPConnector(limit=30),
    )
    bot = Bot(config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    api = ApiClient(config.backend_url, config.service_key, http)
    cache = TtlCache(config.cache_seconds)
    pages = TtlCache(1800)
    dp = Dispatcher(storage=MemoryStorage(), api=api, cache=cache, pages=pages)
    dp.include_router(router)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    scheduler = None
    polling = None
    try:
        me = await bot.get_me()
        log.info('authenticated with Telegram as @%s', me.username)
        scheduler = asyncio.create_task(run_scheduler(
            stop, bot=bot, api=api, cache=cache, pages=pages, limiter=RateLimiter(),
        ))
        polling = asyncio.create_task(dp.start_polling(
            bot, allowed_updates=ALLOWED_UPDATES, handle_signals=False, close_bot_session=False,
        ))
        if run_for is not None:
            loop.call_later(run_for, stop.set)
        await stop.wait()
        log.info('shutting down')
    finally:
        with_timeout = 10
        if polling is not None:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-for', type=float, default=None, help='exit cleanly after this many seconds (smoke test)')
    args = parser.parse_args()
    config = load_config()
    setup_logging(config)
    asyncio.run(run(config, args.run_for))


if __name__ == '__main__':
    main()
