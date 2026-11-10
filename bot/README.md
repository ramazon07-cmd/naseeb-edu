# Naseeb Edu counselor bot

aiogram 3 long-polling bot for counselors and counselor assistants. It has no database and holds no passwords; everything goes through the backend's `/api/bot/` with a shared key. Setup, deploy and the API are described in [docs/telegram-bot.md](../docs/telegram-bot.md).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r bot/requirements.txt
cp bot/env.sample bot/.env      # BOT_TOKEN, BACKEND_URL, BOT_SERVICE_KEY
python -m bot.main                # from the repo root; --run-for 10 exits cleanly after 10 s
```

Tests (no network): `pip install pytest pytest-asyncio && cd bot && pytest`.

Layout: `handlers.py` (commands, login flow, settings, `/add`), `students.py` (reads name, email and phone from a pasted message), `scheduler.py` (minute loop, flood limit, retries), `render.py` (digest text, pages under 4096 characters), `i18n.py` (all strings, uz/ru/en), `api.py` (shared aiohttp client), `keyboards.py`, `delivery.py`, `cache.py`, `config.py`.

Never log tokens, passwords or login message text; the handlers log nothing from message bodies and `main.py` masks the token and key in every log line.
