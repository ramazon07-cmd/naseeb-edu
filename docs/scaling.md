# Scaling the backend toward 50,000 concurrent students

This document explains what the code does for scale, what a local load test
measured, and what infrastructure 50,000 concurrent students need. Numbers
marked *measured* come from the run described below; everything else is
extrapolated from them and says so. Re-run `scripts/loadtest/` on staging
hardware before buying capacity.

## What the code does now

| Area | Change |
|---|---|
| App server | gunicorn `gthread`: `WEB_CONCURRENCY` processes × `GUNICORN_THREADS` threads (conservative default 2 × 8, sized for a 512 MB instance and a small Postgres). A slow request, such as a 35 s AI stream, holds one thread instead of a whole worker. |
| Database connections | Django 5.2's built-in psycopg pool with one pool per process. `DB_POOL_MAX_SIZE` defaults to 8 (= the default thread count) and `CONN_MAX_AGE=0`. Setting `DB_POOL_MAX_SIZE=0` turns the pool off. Behind PgBouncer, `PGBOUNCER=1` turns off the pool, server-side cursors and prepared statements (see [PgBouncer](#pgbouncer)). |
| Cache | Uses `RedisCache` when `REDIS_URL` is set, otherwise per-process memory. Throttles, login lockouts, the AI budgets and the catalogue cache are only correct across processes when Redis is set. `manage.py check --deploy` warns (`naseeb.W001`) when it isn't. Every Redis call gives up after `REDIS_CONNECT_TIMEOUT`/`REDIS_SOCKET_TIMEOUT` (0.25 s) with no retry, so a hung Redis can't stall request threads; callers then fail open. |
| Rate limits | `apps/users/throttles.py`: one integer counter per client and window (sliding-window counter), updated in one atomic Redis round trip (`MULTI`: `SET NX EX`, `INCR`, `GET`), instead of DRF's list of up to 1,200 timestamps per user rewritten on every request. The Essay Lab uses the same module. Rejected requests are not counted, `Retry-After` is exact, cache errors fail open. |
| Shared IPs | Sign-in is limited per account and IP (`AUTH_LOGIN_RATE`) with only a generous per-IP ceiling (`AUTH_LOGIN_IP_RATE`, 300/min) and an account-wide ceiling across IPs (`AUTH_LOGIN_ACCOUNT_RATE`, 60/min) that addresses which already signed in to the account skip; token refresh per refresh token (`AUTH_REFRESH_RATE`) with a per-IP ceiling of 600/min. A class behind one school or carrier IP no longer shares one allowance. Password change and credential issuing are per user. |
| Proxies | `NUM_PROXIES` (default 1 in production) decides which `X-Forwarded-For` hop counts as the client IP. |
| Migrations | Run once per deploy as the Render pre-deploy command (`migrate_locked`), not in the web start command. The command holds a PostgreSQL advisory lock and, behind PgBouncer, uses `DIRECT_DATABASE_URL`. `MIGRATE_ON_START=1` restores migrating on boot (docker-compose sets it). |
| Compression | JSON responses under `/api/` are gzipped when the client accepts it (list pages of 10–170 KB shrink ~5–10×). Streams (the assistant) and file downloads are not. |
| Health | `/api/health/` is liveness only (no DB or cache). `/api/health/ready/` checks the database (2 s statement timeout; 503 when down) and the cache (`degraded`, still 200, when down, because the app keeps working without Redis). |
| AI cost and threads | Assistant and Essay Coach calls count against daily caps: platform-wide, per school and per user, in one atomic step. While Redis is down each process allows only `AI_FALLBACK_PROCESS_DAILY_BUDGET` paid calls. At most `AI_MAX_STREAMS_PER_PROCESS` streams per process and `AI_USER_MAX_CONCURRENT_STREAMS` per user; a reply is cut off after `AI_STREAM_MAX_SECONDS`, and no database connection is held while it streams. |
| Scheduled jobs | `flush_expired_tokens`, `purge_screen_time` and `generate_notifications` run from Render cron jobs (`render.yaml`). Each takes an advisory lock (an overlapping run skips) and works in batches of 5,000 rows in short transactions; `generate_notifications` runs a fixed number of queries per batch of students. |
| Errors | Sentry when `SENTRY_DSN` is set (no personal data; auth headers, cookies, passwords and tokens are scrubbed). |
| Queries | Student, account, essay, application, channel and message lists, the dashboard and schools run a fixed number of queries per page, however many rows there are. Tests check this (`test_audit_query_counts.py`, `test_perf_regressions.py`). |
| Indexes | Composite indexes for the hot filters: tasks, applications, documents, notifications and the activity log (migration `0043_audit_indexes`). |
| List pages | List endpoints accept `?page_size=` up to 200 (the default is still 25). `api.list()` asks for 200, so a sign-in loads each collection in one or a few requests instead of one per 25 rows. |
| Catalogue cache | The university, scholarship and programme lists are cached for 5 minutes after the permission checks. Saving or deleting a catalogue row changes the cache version, so edits show at once. |
| Polling | The Messages page polls an open conversation every 8 s and slows down to every 30 s while nothing changes; a new message, a send or refocusing the window resets it. |
| Logging | Log lines go to stdout and include the process and thread. `LOG_LEVEL` sets the level. |

## How it was measured

One laptop cannot open 50,000 real sessions. The method is: measure what one
open tab costs, measure how many tabs one app instance serves, and multiply.

* **Machine**: Apple M2 (4 performance + 4 efficiency cores), 8 GB RAM.
  Locust, gunicorn and PostgreSQL 14 (default `shared_buffers` of 128 MB) ran
  on the same machine. Redis was not installed, so the cache was per-process
  memory (LocMem): Redis round trips are *not* in these numbers.
* **Server**: the Procfile command (gunicorn `gthread`, 2 workers × 8
  threads, `--max-requests 2000`) with `APP_ENV=production`, `DEBUG=False`
  and the psycopg pool (8 per worker), started through
  `scripts/loadtest/querystats_wsgi.py`, which reports the query count, DB
  time and CPU time of every request in response headers. The login and API
  throttles were raised for the test.
* **Data** (`scripts/loadtest/seed.py`): 5,000 students in 20 schools, 100
  counselors, 80 teachers, 20 school accounts, 2,000 parents; 60,000 tasks,
  40,000 roadmap missions, 30,000 applications, 35,000 documents, 20,000 essays
  with rich Essay Lab documents (~600 words each) and 120,000 checkpoints,
  450,000 screen-time rows, 5,200 channels with 112,000 messages. 1.2 GB.
* **Traffic** (`scripts/loadtest/locustfile.py`): each Locust user is one
  open tab of one role (90% students, then counselors, parents, teachers and
  school accounts). It signs in and loads the workspace exactly like
  `useWorkspaceData` (every collection of the role, following pagination),
  then changes page every 20–90 s. The timers match the frontend: screen-time
  upload every 30 s while active and on each page change, the dashboard
  summary every 60 s, the Messages poll, Essay Lab autosave (3 s after typing
  stops, at most every 20 s while typing) with history, checkpoints and the
  depth check (local fallback, no external provider), a token refresh every 30 min,
  and a new sign-in after a session of ~30 min on average. A student spends
  about 30% of the time writing in the Essay Lab.
* **Runs**: 50, 200 and 500 tabs for 6 minutes each (sign-in ramp included),
  before and after the fixes. Then `NASEEB_TIME_SCALE=0.1` runs every timer
  ten times faster, so 200–800 Locust users send the traffic of 2,000–8,000
  tabs with the same mix; those runs use `--reset-stats` to measure the steady
  state after the sign-in ramp.

## Results

### Same tabs, before and after (measured)

| Tabs | Requests | p50 / p95 / p99 (ms) | Failed | App CPU (s) | DB time (s) | Queries |
|---|---|---|---|---|---|---|
| 50 | 4,434 → 2,702 | 8/39/120 → 6/32/140 | 14 → 0 | 31 → 22 | 51 → 9 | 19,558 → 9,970 |
| 200 | 16,137 → 10,452 | 9/44/140 → 7/35/140 | 44 → 3 | 108 → 81 | 235 → 36 | 66,965 → 38,694 |
| 500 | 37,257 → 26,390 | 72/1,100/1,400 → 11/71/180 | 756 → 24 | 272 → 205 | 1,053 → 206 | 153,091 → 98,153 |

"Failed" before includes 500s from the depth check (fixed). The rest, in both
columns, are connection resets: `--max-requests 2000` recycles a worker every
10–40 s at these rates and closes its keep-alive connections, and macOS caps
the listen backlog at 128. Locust's client does not retry those; browsers do.
There were no application errors after the fixes.

### Tabs per instance (measured, steady state, one instance = 2 workers × 8 threads)

| Simulated tabs | Before: req/s, p95, p99 | After: req/s, p95, p99 | After: app CPU | After: Postgres CPU |
|---|---|---|---|---|
| 2,000 | 205, 200 ms, 2.0 s | 191, 30 ms, 96 ms | 0.9 core | 0.2 core |
| 4,000 | 283 (saturated), 1.4 s, 3.7 s | 360, 170 ms, 330 ms | 1.7 cores | 0.35 core |
| 6,000 | – | 438 (saturated), 860 ms, 1.3 s | 2.2 cores | 0.4 core |
| 8,000 | – | 454 (saturated), 1.8 s, 2.8 s | 2.4 cores | 0.5 core |

Before the fixes PostgreSQL used 1.6 cores at 2,000 tabs (a counselor's
channel list took 3.7 s); after, 0.2 core. One instance on M2 cores now serves
about **3,000 tabs at a p95 under ~100 ms** (interpolated between the 2,000-
and 4,000-tab runs) and saturates at ~450 req/s.

### Where the traffic comes from (measured, current frontend, steady state)

One open tab sends **0.095 requests/s** on average, one every ~10.5 s (the
previous frontend: 0.103). 50,000 tabs therefore send about **4,800 req/s** to
Django. Static files come on top and belong on a CDN.

| Source | Requests per tab per hour | At 50,000 tabs (req/s) | Share of requests | Share of app CPU |
|---|---|---|---|---|
| Essay Lab autosave | 112 | 1,560 | 33% | 26% |
| Screen-time upload | 76 | 1,060 | 22% | 6% |
| Sign-in and reloads (token, me, dashboard, collection lists) | 54 | 750 | 16% | 40% |
| Other Essay Lab (library, open essay, history, checkpoints, depth check) | 42 | 580 | 12% | 6% |
| Messages (poll, channel list, read receipts, send) | 41 | 570 | 12% | 15% |
| Dashboard screen-time summary | 14 | 190 | 4% | 4% |
| Other page loads, saves, token refresh | 4 | 50 | 1% | 2% |

On average a request costs 3.8 ms of app CPU, 3.7 queries and 3.7 ms of DB
time. Password hashing (PBKDF2, ~135 ms of CPU per sign-in) is about 18% of
app CPU with 30-minute sessions; shorter sessions or a sign-in storm at the
start of a class raise that share.

A student's sign-in now takes about 26 requests (was 39), a counselor's with
50 students about 30 (was ~140), and a school account's with 250 students
about 70 (was ~450). These counts follow from the seeded row counts and the
page sizes.

### Cost per endpoint (measured)

p95 at 500 tabs (6-minute run with the sign-in ramp) and queries per request,
before → after; then app CPU, DB time and response size per request after the
fixes (CPU and DB from the 50-tab run, without contention). List endpoints
return up to 200 rows per request after the fixes and 25 before, so their
per-request cost grew while their request count fell.

| Endpoint | p95 ms | Queries | CPU ms | DB ms | KB |
|---|---|---|---|---|---|
| `GET /achievements/` | 1100 → 53 | 3.0 → 3.0 | 3.7 | 2.6 | 13.2 |
| `GET /activities/` | 1100 → 55 | 2.9 → 3.0 | 4.2 | 2.8 | 15.1 |
| `GET /applications/` | 1100 → 110 | 5.0 → 5.0 | 13.3 | 3.2 | 53.5 |
| `POST /auth/token/` | 1400 → 250 | 2.0 → 2.0 | 132.7 | 2.2 | 0.6 |
| `GET /bookings/` | 1100 → 57 | 3.6 → 3.9 | 3.9 | 1.9 | 5.2 |
| `POST /bookings/` | 9 → 9 | 5.0 → 5.0 | 4.1 | 2.7 | 0.5 |
| `GET /bookings/participants/` | 10 → 12 | 3.0 → 3.0 | 4.0 | 1.6 | 1.7 |
| `GET /challenge-attempts/` | 200 → 17 | 2.6 → 2.5 | 7.5 | 3.6 | 0.3 |
| `GET /channel-messages/` (poll) | 170 → 23 | 4.0 → 4.0 | 11.7 | 3.7 | 7.5 |
| `POST /channel-messages/` | 78 → 14 | 7.0 → 7.0 | 5.4 | 6.4 | 0.4 |
| `GET /college-research/` | 620 → 61 | 9.3 → 9.3 | 16.6 | 2.4 | 44.4 |
| `GET /counselor-roadmap-templates/` | 470 → 31 | 2.9 → 4.0 | 2.4 | 2.8 | 1.8 |
| `GET /counselor-roadmaps/` | 870 → 70 | 4.3 → 6.0 | 4.0 | 4.8 | 3.4 |
| `GET /dashboard/stats/` | 1200 → 75 | 10.8 → 10.9 | 4.7 | 11.2 | 0.6 |
| `GET /documents/` | 960 → 64 | 3.0 → 3.0 | 5.2 | 1.6 | 18.4 |
| `GET /essay-lab/essays/` | 540 → 16 | 2.0 → 2.0 | 6.8 | 1.9 | 2.4 |
| `GET /essay-lab/essays/:id/` | 190 → 6 | 2.0 → 2.0 | 2.8 | 0.9 | 7.9 |
| `PUT /essay-lab/essays/:id/autosave/` | 21 → 18 | 4.1 → 4.1 | 9.3 | 4.0 | 0.1 |
| `GET /essay-lab/essays/:id/checkpoints/` | 14 → 12 | 10.0 → 10.3 | 5.7 | 3.0 | 0.8 |
| `POST /essay-lab/essays/:id/checkpoints/` | 8 → 9 | 4.0 → 4.0 | 5.3 | 2.6 | 0.1 |
| `GET /essay-lab/essays/:id/checkpoints/:id/` | 5 → 7 | 3.0 → 3.0 | 3.0 | 1.2 | 7.5 |
| `POST /essay-lab/essays/:id/depth-check/` | 19 (500s) → 13 | 2.0 → 6.0 | 7.0 | 3.4 | 0.6 |
| `GET /essay-lab/essays/:id/depth-check/latest/` | 270 → 7 | 3.0 → 3.0 | 2.8 | 1.4 | 0.3 |
| `GET /essay-lab/folders/` | 300 → 9 | 2.0 → 2.0 | 3.7 | 2.0 | 0.1 |
| `GET /essays/` | 1100 → 100 | 15.7 → 4.0 | 7.8 | 9.9 | 78.2 |
| `GET /honors/` | 1000 → 56 | 2.9 → 3.0 | 3.4 | 1.8 | 8.0 |
| `GET /internships/` | 1100 → 58 | 2.9 → 3.0 | 2.3 | 1.4 | 3.8 |
| `GET /message-channels/` | 4100 → 86 | 7.5 → 6.9 | 8.7 | 12.3 | 4.9 |
| `POST /message-channels/:id/mark-read/` | 240 → 12 | 7.0 → 6.0 | 4.9 | 2.5 | 0.0 |
| `GET /message-channels/overview/` | 1900 → 45 | 7.0 → 7.0 | 7.0 | 23.8 | 0.2 |
| `GET /opportunity-programs/` | 1100 → 49 | 3.0 → 1.1 | 2.1 | 0.2 | 137.0 |
| `GET /parent-portal/` | 1300 → 100 | 11.0 → 11.0 | 7.3 | 12.3 | 4.9 |
| `GET /program-services/` | 1100 → 61 | 2.8 → 3.0 | 2.7 | 1.6 | 2.3 |
| `GET /projects/` | 1100 → 60 | 2.9 → 3.0 | 2.9 | 2.3 | 8.4 |
| `GET /recommendations/` | 1100 → 53 | 2.9 → 3.0 | 3.1 | 1.9 | 5.1 |
| `GET /researches/` | 1100 → 48 | 2.9 → 3.0 | 2.3 | 2.0 | 4.4 |
| `GET /roadmap-missions/` | 1100 → 71 | 2.9 → 3.0 | 6.1 | 2.4 | 29.5 |
| `PATCH /roadmap-missions/:id/` | 1100 → 18 | 1.9 → 3.0 | 9.1 | 4.3 | 0.6 |
| `GET /scholarships/` | 1100 → 46 | 2.9 → 1.1 | 1.0 | 0.2 | 36.4 |
| `GET /schools/` | 620 → 40 | 3.8 → 5.0 | 2.6 | 17.3 | 0.5 |
| `GET /screen-time/summary/` | 850 → 50 | 5.1 → 5.4 | 7.4 | 4.0 | 2.1 |
| `POST /screen-time/track/` | 480 → 16 | 3.7 → 2.0 | 3.6 | 1.6 | 0.0 |
| `GET /store-items/` | 1100 → 53 | 3.7 → 4.0 | 1.9 | 0.7 | 2.4 |
| `GET /student-team/` | 1000 → 62 | 4.6 → 5.0 | 1.7 | 1.0 | 0.3 |
| `GET /students/` | 1200 → 78 | 7.9 → 8.0 | 6.4 | 2.2 | 16.5 |
| `GET /students/:id/data-visibility/` | 41 → 55 | 22.0 → 22.0 | 32.1 | 16.5 | 24.5 |
| `GET /support-tickets/` | 1100 → 40 | 2.0 → 2.2 | 1.6 | 0.6 | 0.2 |
| `GET /tasks/` | 1100 → 88 | 3.0 → 3.0 | 10.9 | 9.4 | 65.4 |
| `PATCH /tasks/:id/` | 1300 → 21 | 3.0 → 3.0 | 7.0 | 7.2 | 0.9 |
| `GET /universities/` | 1100 → 44 | 4.0 → 1.1 | 2.5 | 0.2 | 171.0 |
| `GET /users/accounts/me/` | 1100 → 39 | 3.9 → 3.9 | 2.2 | 1.1 | 0.4 |

Query counts include the one query that authenticates the request. Before the
fixes, 500 tabs saturated the instance during the sign-in ramp, so every
endpoint's p95 was ~1.1 s there; the table shows what the queueing hid.

Measured with single requests on the same data: an admin's account list (200
rows) went from 341 to 3 queries and 132 to 25 ms, a school account's from 602
to 3 queries and 205 to 17 ms; a counselor's legacy essay list from 27 to 3
queries and 2.3 MB to 1.2 MB per 200 essays. `EXPLAIN ANALYZE` of the hot
queries found no missing index at this size; the slowest remaining statement
is the OFFSET page of a school's tasks (~25 ms at page 8, a sort over ~3,000
rows).

## What 50,000 concurrent students need

Measured on the laptop: ~4,800 req/s of traffic for 50,000 tabs, ~140 req/s
per M2 core at a p95 under ~100 ms, and ~0.1 M2 core of PostgreSQL per 100
req/s. The rest of this section is extrapolation from those numbers.

| Tier | Size | Reasoning |
|---|---|---|
| App servers | ~70–90 vCPUs in total, for example 20–24 instances of 4 vCPU (`WEB_CONCURRENCY=4`, `GUNICORN_THREADS=8`, 1–2 GB RAM each), autoscaling on CPU at ~60% | 4,800 req/s ÷ 140 req/s per M2 core ≈ 35 M2 cores. A cloud vCPU (one hyperthread) runs single-threaded Python at roughly 50–60% of an M2 performance core (not measured here), so ≈ 60–70 busy vCPUs, plus ~30% headroom for sign-in bursts and deploys. Each worker used 75–120 MB of RSS. |
| PostgreSQL | One primary with 16 vCPU and ≥ 32 GB RAM on fast SSD, plus a standby for failover | ≈ 5 M2 cores of database CPU at 4,800 req/s, so ≈ 8–10 busy vCPUs. ~17,500 queries/s and ~2,600 row writes/s (autosave ~1,560/s, each rewriting a ~6 KB document and its text; screen time ~1,060/s), so tens of MB/s of WAL (estimate). The data grew linearly with students: ~12 GB at 50,000, which should fit in memory. |
| Connections | PgBouncer in transaction mode with ~100 server connections | 22 instances × 4 workers × 8 threads = 704 client connections, twice that during a deploy. Set `PGBOUNCER=1` and `DIRECT_DATABASE_URL` (see [PgBouncer](#pgbouncer)). |
| Redis | 1–2 GB, same region | Needed for shared throttles, lockouts, budgets and the catalogue cache. One round trip per throttle check (a few small integer keys per client), so roughly 1–2 round trips per request, ~5–10k ops/s. Not measured: the local runs used in-process memory. |
| CDN | All frontend assets | The landing page makes no API calls. A first visit downloads ~270 KB gzipped of JS and CSS; other pages load their own chunk. |

Before these fixes the same traffic needed about 0.8 M2 core of PostgreSQL per
100 req/s, i.e. ~40 cores for 50,000 tabs, which no single primary provides;
the message-channel queries alone made the database the limit.

### Verified locally vs extrapolated

* Verified: query count, DB time, CPU time and payload of every endpoint on a
  5,000-student dataset; latency before and after at 50–500 tabs; tabs per
  2-worker instance on M2 cores (2,000–8,000 simulated tabs); identical
  response bodies for the changed endpoints, except the documented revision
  fields.
* Extrapolated: cloud vCPU speed relative to M2, linear growth of data and
  query cost from 5,000 to 50,000 students, Redis load and latency, WAL volume,
  PgBouncer, and the traffic model itself (30-minute sessions, ~30% of the time
  writing essays, ~15% of page visits to Messages). Autosave traffic scales
  directly with the share of students typing at the same time.

### Still to do

1. **Autosave** is now the largest cost: a third of requests, a quarter of app
   CPU and 38% of DB time. Every save rewrites the whole document and its
   text. Skipping the checkpoint lookup on most saves, sending only the changed
   blocks, or a longer debounce would each cut it.
2. **Admin pages at scale**: an admin still loads every task, application and
   document of every student. `api.list()` stops after 100 pages (20,000 rows),
   which 5,000 students already exceed for tasks. These pages need server-side
   search and pagination.
3. **Worker recycling**: the load test ran with `--max-requests 2000`, which
   restarted a worker every 10–40 s at 100–400 req/s per instance and caused
   the connection resets above. The default is now 20,000
   (`GUNICORN_MAX_REQUESTS`); lower it if worker memory keeps growing.
4. **Message polls** serialize 50 messages (~12 ms of CPU) even when nothing
   changed; an ETag or a `since` parameter would make quiet polls almost free.
5. **Applications** nest the full university with its programmes in every row;
   the UI reads only the name.
6. **Translations** (265 KB, 85 KB gzipped, all languages) load on every first
   visit; loading only the active language would cut the first load by ~20%.
7. Measure on staging hardware with Redis and PgBouncer in place before buying
   the full fleet.

## Database connections

Connections per instance = `WEB_CONCURRENCY × DB_POOL_MAX_SIZE`, and during
a zero-downtime deploy the old and new instances overlap, so budget for
**twice** that:

| Setting (per instance) | Steady state | During a deploy |
|---|---|---|
| Defaults: 2 workers × pool 8 | 16 | 32 |
| 4 workers × pool 8 | 32 | 64 |
| 22 instances × 4 × 8 | 704 | 1,408 (needs PgBouncer) |

Keep `2 × instances × WEB_CONCURRENCY × DB_POOL_MAX_SIZE` plus ~10 for
migrations and admin shells under the plan's `max_connections`, or put
PgBouncer in front.

**Scaling up from the defaults:** raise `WEB_CONCURRENCY` toward the vCPU
count of the instance (each worker used 75–120 MB of RSS in the load test);
keep `GUNICORN_THREADS` at 8 and `DB_POOL_MAX_SIZE` ≤ `GUNICORN_THREADS` (a
thread never needs more than one connection). Python runs one request at a
time per process, so throughput grows with processes (cores), not threads.

If the fleet needs more connections than the plan allows:

- Run **PgBouncer** in transaction mode (below).
- Or lower `GUNICORN_THREADS`/`DB_POOL_MAX_SIZE`. Threads only help while requests wait on I/O.

Pick a Postgres plan with enough RAM to keep the hot tables and indexes in
memory. Watch `pg_stat_statements` and the slow-query log after launch.

### PgBouncer

Run PgBouncer in **transaction** mode as a Render private service in front of
the database, then on the web service and the cron jobs:

| Variable | Value | Why |
|---|---|---|
| `DATABASE_URL` | PgBouncer's address | All request traffic goes through the pooler. |
| `PGBOUNCER` | `1` | Turns off Django's in-process pool, named server-side cursors and prepared statements, which all need one server session and break when consecutive transactions land on different server connections. |
| `DIRECT_DATABASE_URL` | The database itself (Render's internal URL) | Used by `migrate_locked` and the cron jobs' advisory locks, which must hold one session for minutes. Without it those commands refuse to run behind PgBouncer rather than leak a lock. |
| `CONN_MAX_AGE` | `60` (default) | Django keeps its client connection to PgBouncer between requests (with health checks), which saves a handshake per request. |

Size PgBouncer with `max_client_conn` ≥ 2 × instances × `WEB_CONCURRENCY` ×
`GUNICORN_THREADS` + 20 (each request thread keeps one client connection; ×2
covers a deploy's overlap) and `default_pool_size` ≈ 2–4 × the database's
vCPUs, keeping the total under the plan's `max_connections` minus ~10 for
migrations and the cron jobs, which connect directly.

### Gunicorn and pool sizing

| Setting | Default | Production (4 vCPU instance) | Notes |
|---|---|---|---|
| `WEB_CONCURRENCY` | 2 | 4 (≈ vCPUs) | Throughput grows with processes; 75–120 MB RSS each. |
| `GUNICORN_THREADS` | 8 | 8 | Threads only help while requests wait on I/O (database, Redis, AI). |
| `DB_POOL_MAX_SIZE` | 8 | 8 without PgBouncer (≤ threads); ignored with `PGBOUNCER=1` | One connection per thread is the most a process can use. |
| `AI_MAX_STREAMS_PER_PROCESS` | 4 | ≤ half of `GUNICORN_THREADS` | Keeps threads free for ordinary requests during a burst of chats. |
| `AI_STREAM_MAX_SECONDS` | 60 | 60 | Must stay below gunicorn's `--timeout 120`. |
| `GUNICORN_MAX_REQUESTS` | 20,000 | 20,000 | Lower only if worker memory keeps growing. |

## Environment variables added for scale

| Variable | Default | Meaning |
|---|---|---|
| `REDIS_CONNECT_TIMEOUT`, `REDIS_SOCKET_TIMEOUT` | 0.25 | Seconds before a Redis call gives up (the caller then fails open). |
| `REDIS_HEALTH_CHECK_INTERVAL` | 30 | Seconds between PINGs on idle pooled Redis connections. |
| `AUTH_LOGIN_RATE` | 10/minute | Sign-in attempts per account from one IP. |
| `AUTH_LOGIN_ACCOUNT_RATE` | 60/minute | Sign-in attempts per account across IPs; addresses that signed in to it in the last `LOGIN_KNOWN_DEVICE_SECONDS` (30 days) are exempt. |
| `AUTH_LOGIN_IP_RATE` | 300/minute | Sign-in attempts per IP (flood ceiling only). |
| `AUTH_REFRESH_RATE` | 30/hour | Refreshes per refresh token. |
| `AUTH_REFRESH_IP_RATE` | 600/minute | Refreshes per IP (flood ceiling only). |
| `PGBOUNCER` or `DB_POOLER` | unset | Set when `DATABASE_URL` points at PgBouncer in transaction mode. |
| `DIRECT_DATABASE_URL` | unset | Direct database URL for migrations and job locks (needed with PgBouncer). |
| `MIGRATE_ON_START` | 0 | `1` runs `migrate_locked` before gunicorn starts (docker-compose; not for Render). |
| `SENTRY_DSN` | unset | Turns on Sentry. |
| `SENTRY_TRACES_SAMPLE_RATE` | 0 | Share of requests traced for performance (0–1); start at 0.01–0.05. |
| `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE` | `APP_ENV`, `RENDER_GIT_COMMIT` | Labels on each event. |
| `AI_ASSISTANT_SCHOOL_DAILY_BUDGET` | 1000 | Paid assistant calls per school per day (0 = no cap). |
| `ESSAY_COACH_SCHOOL_DAILY_BUDGET` | 1000 | Paid coach checks per school per day (0 = no cap). |
| `ESSAY_COACH_USER_DAILY_LIMIT` | 40 | Paid coach checks per student per day (0 = no cap). |
| `AI_FALLBACK_PROCESS_DAILY_BUDGET` | 20 | Paid AI calls each process may make per day while Redis is down (0 = none). Worst case per day = processes × this. |
| `AI_STREAM_MAX_SECONDS` | 60 | Total time for one streamed assistant reply. |
| `AI_MAX_STREAMS_PER_PROCESS` | 4 | Concurrent assistant streams per gunicorn process. |
| `AI_USER_MAX_CONCURRENT_STREAMS` | 2 | Concurrent assistant streams per user. |

The existing `AI_ASSISTANT_DAILY_BUDGET` / `AI_ASSISTANT_USER_DAILY_LIMIT` keep
their meaning (0 = no cap); `ESSAY_COACH_DAILY_BUDGET=0` still turns AI coach
checks off.

## Render setup checklist

1. **Redis**: add Render Key Value in the same region and set `REDIS_URL` on the web service and the cron jobs. Required before running more than one process or instance.
2. **Environment group**: put the shared backend variables (`APP_ENV`, `SECRET_KEY`, `DATABASE_URL`, `DIRECT_DATABASE_URL`, `REDIS_URL`, `MEDIA_ROOT`, `DOCUMENT_STORAGE_ROOT`, `NUM_PROXIES`, `SENTRY_DSN`, the AI keys and budgets) in an environment group named `naseeb-backend` and link it to the web service; `render.yaml` links the cron jobs to it.
3. **Build and start**: build command `./build.sh`; start command the `Procfile` `web:` line (it no longer migrates).
4. **Pre-deploy command**: `cd backend && python manage.py migrate_locked --noinput`. Render runs it once per deploy, before new instances take traffic; a failed migration stops the deploy while the old version keeps serving. (`build.sh` also migrates; with the pre-deploy command in place that step finds nothing to do.)
5. **Health check path**: `/api/health/` (liveness). Point uptime monitoring at `/api/health/ready/`.
6. **Files off the disk**: a service with a persistent disk cannot scale beyond one instance. Create a private S3 or Cloudflare R2 bucket, copy existing files with `migrate_files_to_object_storage` and switch to `STORAGE_BACKEND=s3`, following [File storage](#file-storage) below. Production refuses to start on the local disk unless `FILE_STORAGE_SINGLE_INSTANCE=True` is set.
7. **PgBouncer** once the connection budget above exceeds the plan: add it as a private service and set `PGBOUNCER=1`, `DATABASE_URL` (PgBouncer) and `DIRECT_DATABASE_URL` (direct).
8. **Scale the web service** (several instances or CPU autoscaling at ~60%), starting from the sizing table above and checking RAM and the connection budget.
9. **Cron jobs**: sync `render.yaml` as a Blueprint (Render dashboard → Blueprints → New). It creates three cron jobs: `flush_expired_tokens` (daily), `purge_screen_time` (daily) and `generate_notifications` (daily, 07:00 Tashkent). Each skips if the previous run is still going.
10. **Sentry** (optional): set `SENTRY_DSN` and `SENTRY_TRACES_SAMPLE_RATE=0.02`.
11. **CDN** in front of the frontend (a Render static site or Cloudflare). Keep `NUM_PROXIES` equal to the real number of proxies in front of Django: usually 2 with Cloudflare in front of Render.
12. **Load-test staging** with `scripts/loadtest/` (below) at 5–10% of the target, with Redis and PgBouncer in place, and compare the per-instance numbers with the tables above before launch.

The backend and frontend of this change can be deployed in either order: an
older backend ignores `page_size` and keeps returning 25 rows per page, which
the frontend still follows.

## Running the load test

Never against production. On a local or staging database:

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt locust
createdb loadtest   # seed.py only accepts a local database whose name starts with "loadtest"
export DATABASE_URL=postgres://postgres@127.0.0.1:5432/loadtest   # plus the production-like settings
(cd backend && ../.venv/bin/python manage.py migrate --noinput)
.venv/bin/python scripts/loadtest/seed.py --students 5000 --schools 20   # writes scripts/loadtest/.accounts/

# The API the production way, with per-request cost headers:
(cd backend && ../.venv/bin/gunicorn --pythonpath ../scripts/loadtest querystats_wsgi:application \
  --worker-class gthread --workers 2 --threads 8 --bind 127.0.0.1:8000)

# Real timings, then the steady state of 400 / 0.1 = 4,000 tabs:
mkdir -p results/u200 results/tabs4000
NASEEB_RESULTS=results/u200 .venv/bin/locust -f scripts/loadtest/locustfile.py --host http://127.0.0.1:8000 \
  --headless --users 200 --spawn-rate 3 --run-time 6m --csv results/u200/run
NASEEB_TIME_SCALE=0.1 NASEEB_RESULTS=results/tabs4000 .venv/bin/locust -f scripts/loadtest/locustfile.py \
  --host http://127.0.0.1:8000 --headless --users 400 --spawn-rate 4 --run-time 5m --reset-stats \
  --csv results/tabs4000/run
.venv/bin/python scripts/loadtest/report.py results/tabs4000   # add a second directory to compare
```

`NASEEB_WEIGHT_<ROLE>` sets the role mix, `NASEEB_SESSION_MINUTES` the session
length, and `NASEEB_PAGE_SIZE=0` / `NASEEB_ADAPTIVE_POLL=0` replay the previous
frontend. The login throttles (`AUTH_LOGIN_RATE`, `AUTH_LOGIN_IP_RATE`), the
per-user API throttle (`API_USER_RATE`) and the login lockout apply to the load
generator too; raise them on the test server only.

## File storage

Uploads (student documents, honour/achievement evidence, task submissions,
recommendation letters, student photos, account avatars) live in a private
S3-compatible bucket when `STORAGE_BACKEND=s3`, so every instance sees the same
files and none needs a disk. Development and tests keep the local disk
(`STORAGE_BACKEND=filesystem`, the default).

### How files reach the browser

Nothing in the bucket is public and no list response contains a bucket URL.
Every file is still requested through its scoped API endpoint
(`/api/documents/<id>/file/`, `/api/<resource>/<id>/proof-file/`,
`/api/tasks/<id>/submission-file/`, `/api/recommendations/<id>/file/`), which
runs the same authorisation as before. Then:

| Storage | Endpoint answer |
|---|---|
| Object storage | `302` to a presigned GET URL valid for `PRIVATE_FILE_URL_EXPIRE_SECONDS` (60 s). The signature fixes `Content-Disposition` (inline for PDF/images/text, attachment otherwise or with `?download=1`), `Content-Type` and `Cache-Control: private, no-store`. With `?mode=url` the answer is JSON `{url, expires_at, file_name, content_type}` (media type `application/vnd.naseeb.file-link+json`) instead. |
| Local disk | The file itself, streamed by Django, as before. `?mode=url` is ignored. |

The SPA always asks with `?mode=url` (`frontend/src/lib/protectedFile.js`):
it reads the link from the API with its bearer token, then fetches the bucket
URL with `credentials: 'omit'`, no custom headers and no referrer, and shows
the result through a `blob:` URL. This was chosen over letting `fetch` follow
the 302: only recent browsers drop the `Authorization` header on a
cross-origin redirect, and a CORS request redirected to another origin arrives
with `Origin: null`, which a bucket CORS rule cannot allow safely. With the
link the bucket sees a plain CORS `GET` from the app's origin, and the CSP only
needs the bucket in `connect-src` (`img-src` and `frame-src` already allow
`blob:`). Other API clients can simply follow the 302.

Student photos and avatars are small and shown everywhere, so they are
streamed through the API instead (`/api/students/<id>/photo/`,
`/api/users/accounts/<id>/avatar/`, with the same scoping). Their URLs carry
`?v=<version>` (a hash of the stored name, which changes with every upload);
versioned responses are `Cache-Control: private, max-age=86400, immutable`
with an `ETag`, and a matching `If-None-Match` gets a `304` without reading the
bucket. The SPA keeps one `blob:` URL per (student, version) in a 64-entry LRU
and revokes evicted ones.

Uploads are checked while they stream in: a file larger than its limit
(`DOCUMENT_MAX_UPLOAD_SIZE`, 5 MB for photos, `AVATAR_MAX_UPLOAD_SIZE`) is
refused with `413` before the rest of it is read. Accepted files spool to a
temporary file and are uploaded to the bucket in chunks (multipart above
8 MB). Deleting a row, or a cascade such as deleting an account, deletes its
objects after the transaction commits; a storage error there is logged rather
than failing the request.

### Environment variables (backend)

| Variable | Default | Meaning |
|---|---|---|
| `STORAGE_BACKEND` | `filesystem` | `s3` for object storage. |
| `AWS_STORAGE_BUCKET_NAME` | — | Bucket (required with `s3`). Avatars go under `media/`, everything else under `private/`. |
| `AWS_PRIVATE_STORAGE_BUCKET_NAME` | same bucket | Optional separate bucket for the `private/` files. |
| `AWS_S3_ENDPOINT_URL` | AWS | R2: `https://<account-id>.r2.cloudflarestorage.com`. Empty for AWS. |
| `AWS_S3_REGION_NAME` | — | R2: `auto`. AWS: the bucket's region, e.g. `eu-central-1`. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | — | Keys scoped to the bucket. Leave both empty to use an instance role. |
| `AWS_S3_ADDRESSING_STYLE` | botocore's choice | `path` or `virtual`; changes the host of presigned URLs (see `FILE_STORAGE_ORIGINS`). |
| `AWS_DEFAULT_ACL` | empty | Empty means objects inherit the private bucket policy. R2 and AWS buckets with ACLs disabled (the AWS default) reject ACL headers, so leave it empty unless the bucket still uses ACLs; then set `private`. |
| `AWS_MEDIA_LOCATION`, `AWS_PRIVATE_LOCATION` | `media`, `private` | Key prefixes. |
| `PRIVATE_FILE_URL_EXPIRE_SECONDS` | `60` | Lifetime of presigned URLs. |
| `FILE_STORAGE_SINGLE_INSTANCE` | `False` | Only with `STORAGE_BACKEND=filesystem` in production: acknowledges a single instance on a persistent disk (`MEDIA_ROOT`, `DOCUMENT_STORAGE_ROOT` then required). Without it production refuses to start on the local disk. |

A custom domain is deliberately not used for private files: presigned URLs
are signed for the S3 API host, and an R2 custom domain cannot serve them.

Frontend image build: `FILE_STORAGE_ORIGINS` (Docker build argument, comma
separated) is added to the nginx CSP `connect-src`. It must be the exact
origin of the presigned URLs; copy it from a `?mode=url` answer. Typical
values are `https://<account-id>.r2.cloudflarestorage.com` (R2, path style)
or `https://<bucket>.s3.<region>.amazonaws.com` (AWS). The build fails on
anything that is not a bare `https://host` origin.

### Bucket setup

**Cloudflare R2**: create the bucket, keep "Public access" disabled (no
r2.dev URL, no public custom domain), and create an R2 API token with
"Object Read & Write" limited to that bucket.

**AWS S3**: create the bucket with "Block all public access" on and object
ownership "Bucket owner enforced". Give the app's IAM user or role
`s3:GetObject`, `s3:PutObject` and `s3:DeleteObject` on `arn:aws:s3:::<bucket>/*`
and `s3:ListBucket` on `arn:aws:s3:::<bucket>` (so a missing key answers 404,
not 403).

**CORS** (both): allow the frontend origins to `GET` objects. R2 dashboard
JSON / `aws s3api put-bucket-cors` rule:

```json
[
  {
    "AllowedOrigins": ["https://naseebedu.com"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": [],
    "ExposeHeaders": ["Content-Type", "Content-Disposition", "Content-Length"],
    "MaxAgeSeconds": 3600
  }
]
```

(for `aws s3api` wrap it as `{"CORSRules": [ ... ]}`). No other method or
header is needed: uploads go through the API, never straight to the bucket.

### Moving the existing files

The command copies every file a row references, under the same key, so no
row changes. It checks each object first (size, plus the MD5 ETag for
single-part uploads) and skips what is already there, so it can be re-run or
resumed at any time.

1. Create the bucket and CORS rule, and set the variables above on the web
   service **without** changing `STORAGE_BACKEND` yet. A release containing
   this change refuses to start in production on the local disk, so until the
   switch in step 3 also set `FILE_STORAGE_SINGLE_INSTANCE=True` (and keep one
   instance).
2. In a shell on the current instance (it still has the disk), preview and copy:

   ```bash
   cd backend
   STORAGE_BACKEND=s3 python manage.py migrate_files_to_object_storage --dry-run
   STORAGE_BACKEND=s3 python manage.py migrate_files_to_object_storage --batch-size 200
   ```

   `--media-root` / `--private-root` override the source directories
   (default `MEDIA_ROOT` / `DOCUMENT_STORAGE_ROOT`). Progress is printed and
   logged per batch; rows whose file is missing on disk are counted and
   logged, and any failed copy makes the command exit non-zero.
3. Rebuild the frontend with `FILE_STORAGE_ORIGINS`, then deploy the backend
   with `STORAGE_BACKEND=s3` (and remove `FILE_STORAGE_SINGLE_INSTANCE`).
4. Run step 2's command once more from a shell that still has the disk, to
   pick up files uploaded between the first copy and the switch.
5. Open a few documents, photos and a download in the app, check the browser
   console for CSP or CORS errors, then detach the disk and scale out.
