# Counselor Telegram bot

`@naseeb_counselor_bot` sends counselors and counselor assistants a daily progress update and answers `/now`, `/students`, `/add`, `/settings`, `/logout`, `/help`. Only counselors and assistants can log in, and only from a Telegram account a superadmin allowed (see below); every other role is refused and nothing is stored.

## How it is built

- `bot/` is a separate process (aiogram 3, long polling). It has **no database access and holds no passwords**. It talks to the backend over HTTPS with the header `X-Bot-Service-Key`.
- `backend/apps/telegram_bot/` is the small API under `/api/bot/`. Every endpoint checks `BOT_SERVICE_KEY` in constant time; a missing or wrong key (or an unset `BOT_SERVICE_KEY`) gives a bare `401`.
- The password is sent once, in the `login` call, and is checked with Django's `authenticate` (the website's backend). It is never stored or logged. The bot deletes the username and password messages before doing anything else.
- All scoping happens in the backend: students come from `active_visible_students(user)` (built on `visible_students`), the same scope the website uses. A counselor sees all of their own students, including those given to an assistant; an assistant sees only the students assigned to them; nobody sees another counselor's students. The bot never filters or joins student data.
- A link (one Telegram chat <-> one account) is valid only while the account is active, still a counselor or assistant, its school is active, an assistant still has an active counselor, and its password version (bumped by every password change made through the app) is unchanged. Otherwise the link is deleted on the next call. A new login replaces the chat's old link, and linking an account to a second chat replaces its first chat (newest wins).
- Login attempts are limited per chat (5 failures in 15 minutes, then `locked`), never per username alone, so nobody can lock an owner out of the bot. Failures also count in the website's lockout counter with the chat standing in for the IP, and an account-wide ceiling (`BOT_LOGIN_ACCOUNT_CEILING`, default 30 per window) slows chats that never signed in to that account, like known devices on the website. An unknown user and a wrong password give the same answer.

## Endpoints (all `POST` with JSON unless noted; all need the service key)

| Path | Purpose |
|---|---|
| `login/` | `chat_id, username, password, telegram_username` -> `pending_token, full_name, email, phone, role`, or `401 invalid_credentials`, `403 telegram_not_allowed / role_not_allowed / password_change_required / account_unavailable`, `429 locked` |
| `whoami/` | `chat_id, telegram_username` -> `kind` (`staff_linked`, `staff_allowed`, `student`, `unknown`), `name` when linked, and `site_url` (the Meetings page). Drives what `/start` does |
| `student-link/` | `chat_id, token, language` -> `full_name, language`; the token comes from the student's bot link. `400 invalid_token` (unknown, expired or used; carries `site_url`), `429 too_many` |
| `confirm/` | `chat_id, pending_token, language` -> creates the link (token lives 10 minutes, single use) |
| `students/` | students grouped by `StudentProfile.grade`; at most 300 are listed, `total` is the true count and `omitted` how many were left out |
| `digest/` | the update for the chat's enabled parts |
| `settings/` | `GET ?chat_id=` and `PUT` (`language`, `notify_time` as `HH:MM` Tashkent, `prefs`, `enabled`) |
| `add-student/` | `chat_id, full_name, email, phone` -> `201` with `full_name, username, phone, temporary_password, expires_at, login_url`; or `400 invalid_name / invalid_email / invalid_phone`, `409 student_exists` (with `full_name, username`) / `student_exists_elsewhere`, `403 seat_limit`, `429 too_many` |
| `scheduled-jobs/` (alias `meeting-reminders/`) | runs the backend jobs that are due (`apps/telegram_bot/jobs.py`): `send_meeting_reminders` every hour; `flush_expired_tokens` and `purge_screen_time` once a day from 03:00 Tashkent; `generate_notifications` once a day from 07:00. The bot calls it once an hour at minute 5, so production needs no cron service. A daily job counts as done only after an `ok` run, so a failure is tried again the next hour. Each job keeps its advisory lock and is recorded in JobRun for the health page |
| `due/` | chats whose update is due now; each is leased for 2 minutes |
| `mark-sent/` | `chat_id, slot_date`: once per chat and day |
| `logout/`, `unlink/` | delete the link and any pending login (`unlink/` is used when the user blocks the bot) |

Errors carry `code`; an unlinked or invalidated chat gets `404 not_linked`.

`due/` returns a chat when its `notify_time` equals the current Asia/Tashkent minute or one of the previous `BOT_DUE_GRACE_MINUTES` (default 5, so a bot restart does not lose the update) and it was not sent for that day yet. Setting a time that has already passed today starts tomorrow, and so does changing the time on a day whose update was already sent: an update goes out at most once a day.

## Adding a student (`/add`)

A counselor or assistant sends the new student's name, email and phone in one message, with `/add` or simply pasted into the chat (for example `Saydazimova Sofiya` / `saidazimova.safiiya@gmail.com` / `+998 91 007 68 25`, labels like `Email:` and a leading `@` are fine). `bot/students.py` splits the text; the bot shows a card and adds nothing until **Add** is tapped. The card's state is cleared before the call, so a double tap adds once.

The backend (`apps/telegram_bot/students.py`) uses `create_student_account`, the same function as the website's quick-create, so the student lands in the actor's school with a profile, the plan's seat check and a temporary password (10 characters, valid `TEMPORARY_CREDENTIAL_TTL_HOURS`, single use). A counselor becomes the assigned counselor; an assistant's student goes to their supervising counselor with the assistant assigned, so both see it in the bot. Phones are stored as `+998XXXXXXXXX` (9 local digits get the country code, an old `8`/`0` trunk prefix is dropped). A student of the same school with the same email, or the same phone and the same name (phones compared on digits only, so `+998 99 167 46 30` matches; siblings often share a parent's number), is not created again: the counselor gets the existing login when it is their student, and only `student_exists_elsewhere` when it is another counselor's. One exception: when the same person added that student in the last 30 minutes and the student has not signed in yet (the bot timed out and they tapped again), a fresh temporary password is issued for that account and returned as a normal add. The whole add runs in one transaction with the school row locked, so two quick taps cannot create two accounts and a later failure leaves no half-made student. As on the website, an email registered elsewhere gets a placeholder and the answer never says so; the reply always gives the username to log in with. Each add writes the `student.created_via_bot` audit event; at most 60 adds per chat per hour.

The reply shows the login, the temporary password, its expiry (Tashkent time) and the website link, and asks the counselor to delete the message once it is passed on.

## What the update looks like

Built for counselors with 50+ students: one summary and a paged list, never a wall of text.

- **Summary** (top of the message): date and student count; how many students were last seen today / in the last 6 days / 7+ days ago / never; essays edited today, students with a streak and the average application readiness (the last three follow the essays / streak / application toggles in `/settings`).
- **List**, 8 students per page, two lines each: name and grade, then last seen (`today`, `yesterday`, `3 days ago`, `never opened`), a readiness bar (`▰▰▱▱▱ 40%`), essays edited today and streak days when above zero.
- **Buttons under the list**: the student numbers on the page (tap one for the card), `⬅ / page / ➡`, and two toggles: `A-Z` / `Needs attention` sorting and the `Inactive 7+ days` filter. *Needs attention* (default for `/now` and the scheduled update) lists students who never opened the app first, then the longest away, ties by lowest readiness. `/students` opens the same list sorted A-Z.
- **Student card**: last seen with time or date, grade, essays (shared count, edited today), streak, application readiness with the six checklist items, counts of activities, honors, documents, applications and letters, and a *Back to list* button that returns to the same page, sort and filter.

Paging is stateless: every button's callback data carries the view (`l:<page>:<sort>:<filter>` or `d:<student id>:<page>:<sort>:<filter>`, under 64 bytes) and a tap re-reads the data from the backend (the bot keeps a reply for 5 seconds so a double tap costs one call). Nothing expires after 30 minutes any more, and the list survives a bot restart. A tap for a student who left the list answers "no longer in your list".

The backend digest adds to each student `id`, `last_seen_at` (newest screen-time write, UTC, one query for all students) and `last_seen_expired`. Screen-time rows are deleted after `SCREEN_TIME_RETENTION_DAYS` (365), so a student with no row who joined before that window shows `no recent activity` instead of `never opened`; both count as inactive. Last-seen dates are shown in Asia/Tashkent time.

Per student the essays count only essays the student shared with the counselor. The streak length comes from `apps/telegram_bot/activity.py: essay_activity_for(user_ids, today)`, which reads `EssayWritingDay` (one query for all students) and counts it with the same `streak_numbers` the Essay Lab card uses; it is shown only for students without private essays, trashed ones included (the daily record cannot tell shared writing from private), a student with no essays shows no streak, and it counts at most the last 400 days. Words typed per day are not sent, because `EssayWritingDay` cannot tell shared essays from private ones. At most 300 students are sent; the summary line says how many more were not shown.

## Environment

| Variable | Where | Meaning |
|---|---|---|
| `BOT_SERVICE_KEY` | backend env group **and** the bot worker | shared secret, at least 32 random characters, identical in both |
| `BOT_TOKEN` | bot worker only | from BotFather |
| `BACKEND_URL` | bot worker only | `https://api.naseebedu.com` |
| `TELEGRAM_BOT_USERNAME` | backend | the bot's username without `@`. Set: students connect Telegram on Meetings (one-tap link `t.me/<bot>?start=s_<token>`) and get meeting messages and reminders there; a student needs it to request a meeting. Unset: Meetings works without it |
| `BOT_LOGIN_MAX_ATTEMPTS`, `BOT_LOGIN_WINDOW_SECONDS`, `BOT_DUE_GRACE_MINUTES`, `BOT_LOGIN_ACCOUNT_CEILING` | backend, optional | defaults 5, 900, 5, 30 |

Login lockouts need the shared cache (Redis) to be correct across backend instances, like the website's own lockouts.

## Deploy (Render dashboard)

1. Generate a key, for example `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Add `BOT_SERVICE_KEY` to the `naseeb-backend` environment group.
3. Deploy the backend first. Its pre-deploy command (`migrate_locked`) applies the `telegram_bot` migrations (`0003_staff_access_student_link_token` creates `StaffTelegramAccess` and `StudentLinkToken` and drops the old `StudentLinkCode` table); no other table is touched.
4. Apply the blueprint (`render.yaml`) so the `naseeb-telegram-bot` worker exists, then set `BOT_TOKEN` and the same `BOT_SERVICE_KEY` on that worker (both are `sync: false`).
5. Check the worker log for `authenticated with Telegram as @naseeb_counselor_bot`.
6. Give each counselor and assistant access (next section), then they send `/start` to the bot.

Run a single worker instance. A second one is safe (the backend leases each due chat) but wasteful. The worker keeps login state in memory, so a restart during someone's login only asks them to press `/start` again.

## Local run

```bash
cd backend && BOT_SERVICE_KEY=dev-key python manage.py runserver 127.0.0.1:8000
cd bot && cp env.sample .env   # fill BOT_TOKEN, BACKEND_URL=http://127.0.0.1:8000, BOT_SERVICE_KEY=dev-key
python -m bot.main
```

`bot/.env` is gitignored. Tests: `cd backend && python manage.py test apps.telegram_bot`, and `cd bot && pytest`.


## Who may log in: the counselor allowlist

The counselor login in the bot is closed by default. A superadmin (role admin with the superadmin tier, or `is_superuser`) enters each counselor's or assistant's Telegram `@username` on the website: **Admin > Counselors > Edit counselor > Telegram username** (set, change or "Remove access"; the list shows `@username` next to the counselor). The API behind it is `GET /api/telegram/staff-access/` (list), and `GET`, `PUT {telegram_username}` and `DELETE` on `/api/telegram/staff-access/<user id>/`; the entries are also in the Django admin (`StaffTelegramAccess`). Only counselor and assistant accounts can have one.

- A username is stored lowercase without `@`, must be 5-32 characters of `a-z 0-9 _`, and belongs to one account (`400 invalid_username`, `409 username_taken`).
- The bot sends the chat's Telegram username with `whoami/` and `login/`. Only a username on the list gets the language picker and the username/password steps; every handler on that path checks again, so stale buttons or an old conversation state cannot reach them. Other people get a friendly "this bot is for Naseeb students and counselors" message (with a hint to set a Telegram username when they have none).
- `login/` also refuses (`403 telegram_not_allowed`) when the credentials belong to a different account than the one assigned to that username, and a chat whose username is not on the list is refused before the password is even checked, so it burns no attempts.
- Chats that are already linked keep working exactly as before, even if their entry is later removed or never existed; removal only blocks new logins. `/logout` and password changes behave as before.

## Students: Meetings and Telegram

Students never log in to the bot and type nothing. On Meetings the website shows one "Connect Telegram" button. It calls `POST /api/telegram/student/link/` (signed-in student, `telegram_link` throttle, 10 an hour by default), which creates a one-time token and returns `{url, expires_in}` with `url = https://t.me/<bot>?start=s_<token>`. The page opens that link in a new tab and polls `GET /api/telegram/student/` every 3 seconds (paused while the tab is hidden) until it says `linked`, or until the token's 15 minutes are over ("Link expired, try again").

- The token is `secrets.token_urlsafe(32)` (43 characters, so the start payload stays under Telegram's 64), stored only as an HMAC with `SECRET_KEY`; a student has one token, the newest replaces the older, and it works once.
- When the student presses Start, the bot calls `student-link/`, which consumes the token atomically and links the chat (one chat per student and one student per chat: the newest link replaces the older either way). The bot answers directly ("Connected: name. Meeting messages and reminders will come here."), so no message is queued for the link itself. An expired, used or unknown token gives "This link has expired or was already used" with the site address.
- A plain `/start` is looked up with `whoami/`: a linked student is told who they are connected as, a counselor on the list gets the login, and everyone else gets the "who is this bot for" message. Students see only `/start` in their command menu (a chat-scoped menu set when they link); the default menu is the counselor commands.
- `GET` (status: `enabled`, `linked`) and `DELETE` (disconnect) stay on `/api/telegram/student/`. The 6-digit code flow (`/code`, `student-code/`, typing a code on the site, `StudentLinkCode`) is gone.

That chat then receives:

- meeting events: confirmed, declined, cancelled, moved, a new time proposed, a meeting requested by staff;
- reminders for a confirmed meeting: 1 day, 5, 4, 3, 2 and 1 hours and 30 minutes before, and when it starts.

The backend writes these to `TelegramOutbox`; the bot fetches them every minute (`/api/bot/student-outbox/`),
sends them and acknowledges (`/api/bot/student-outbox/ack/`). A step whose moment passed more than 15 minutes ago
is skipped, so a late booking or a restart sends only the latest step. A chat that blocks the bot is unlinked.
