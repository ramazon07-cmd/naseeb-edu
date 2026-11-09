# Counselor Telegram bot

`@naseeb_counselor_bot` sends counselors and counselor assistants a daily progress update and answers `/now`, `/students`, `/settings`, `/logout`, `/help`. Only counselors and assistants can log in; every other role is refused and nothing is stored.

## How it is built

- `bot/` is a separate process (aiogram 3, long polling). It has **no database access and holds no passwords**. It talks to the backend over HTTPS with the header `X-Bot-Service-Key`.
- `backend/apps/telegram_bot/` is the small API under `/api/bot/`. Every endpoint checks `BOT_SERVICE_KEY` in constant time; a missing or wrong key (or an unset `BOT_SERVICE_KEY`) gives a bare `401`.
- The password is sent once, in the `login` call, and is checked with Django's `authenticate` (the website's backend). It is never stored or logged. The bot deletes the username and password messages before doing anything else.
- All scoping happens in the backend: students come from `active_visible_students(user)` (built on `visible_students`), the same scope the website uses. A counselor sees all of their own students, including those given to an assistant; an assistant sees only the students assigned to them; nobody sees another counselor's students. The bot never filters or joins student data.
- A link (one Telegram chat <-> one account) is valid only while the account is active, still a counselor or assistant, its school is active, an assistant still has an active counselor, and the password hash is unchanged. Otherwise the link is deleted on the next call. A new login replaces the chat's old link, and linking an account to a second chat replaces its first chat (newest wins).
- Login attempts are limited per chat and per username (5 failures in 15 minutes, then `locked`); an unknown user and a wrong password give the same answer.

## Endpoints (all `POST` with JSON unless noted; all need the service key)

| Path | Purpose |
|---|---|
| `login/` | `chat_id, username, password` -> `pending_token, full_name, email, phone, role`, or `401 invalid_credentials`, `403 role_not_allowed / password_change_required / account_unavailable`, `429 locked` |
| `confirm/` | `chat_id, pending_token, language` -> creates the link (token lives 10 minutes, single use) |
| `students/` | students grouped by `StudentProfile.grade` |
| `digest/` | the update for the chat's enabled parts |
| `settings/` | `GET ?chat_id=` and `PUT` (`language`, `notify_time` as `HH:MM` Tashkent, `prefs`, `enabled`) |
| `due/` | chats whose update is due now; each is leased for 2 minutes |
| `mark-sent/` | `chat_id, slot_date`: once per chat and day |
| `logout/`, `unlink/` | delete the link and any pending login (`unlink/` is used when the user blocks the bot) |

Errors carry `code`; an unlinked or invalidated chat gets `404 not_linked`.

`due/` returns a chat when its `notify_time` equals the current Asia/Tashkent minute or one of the previous `BOT_DUE_GRACE_MINUTES` (default 5, so a bot restart does not lose the update) and it was not sent for that day yet. Setting a time that has already passed today starts tomorrow.

## What the update contains

Per student: essays (count of essays the student shared with the counselor, how many were edited today), writing streak, and the application (profile readiness percent from `onboarding.profile_readiness`, filled / not filled for personal, academics, tests, goal, extracurriculars and honors, plus counts of activities, honors, documents, applications and recommendation letters). Words typed today and the streak length come from `apps/telegram_bot/activity.py: essay_activity_for(user_ids, today)`, which reads `EssayWritingDay` (two queries for all students) and counts the streak with the same `streak_numbers` the Essay Lab card uses.

## Environment

| Variable | Where | Meaning |
|---|---|---|
| `BOT_SERVICE_KEY` | backend env group **and** the bot worker | shared secret, at least 32 random characters, identical in both |
| `BOT_TOKEN` | bot worker only | from BotFather |
| `BACKEND_URL` | bot worker only | `https://api.naseebedu.com` |
| `BOT_LOGIN_MAX_ATTEMPTS`, `BOT_LOGIN_WINDOW_SECONDS`, `BOT_DUE_GRACE_MINUTES` | backend, optional | defaults 5, 900, 5 |

Login lockouts need the shared cache (Redis) to be correct across backend instances, like the website's own lockouts.

## Deploy (Render dashboard)

1. Generate a key, for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Add `BOT_SERVICE_KEY` to the `naseeb-backend` environment group.
3. Deploy the backend first. Its pre-deploy command (`migrate_locked`) applies `telegram_bot.0001_initial`, which only creates the two new tables; no existing table is touched.
4. Apply the blueprint (`render.yaml`) so the `naseeb-telegram-bot` worker exists, then set `BOT_TOKEN` and the same `BOT_SERVICE_KEY` on that worker (both are `sync: false`).
5. Check the worker log for `authenticated with Telegram as @naseeb_counselor_bot`, then send `/start` to the bot.

Run a single worker instance. A second one is safe (the backend leases each due chat) but wasteful. The worker keeps login state in memory, so a restart during someone's login only asks them to press `/start` again.

## Local run

```bash
cd backend && BOT_SERVICE_KEY=dev-key python manage.py runserver 127.0.0.1:8000
cd bot && cp .env.example .env   # fill BOT_TOKEN, BACKEND_URL=http://127.0.0.1:8000, BOT_SERVICE_KEY=dev-key
python -m bot.main
```

`bot/.env` is gitignored. Tests: `cd backend && python manage.py test apps.telegram_bot`, and `cd bot && pytest`.
