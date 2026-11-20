# Assistant chat: handling many users at once

Status: steps A and B are implemented (this branch); C (Render environment
variables), D, E and the load test are still to do. What was built: a stream slot
is taken only for real gateway calls (policy, `local`, `cache`, budget and
fallback replies take none); a full process waits `AI_STREAM_SLOT_WAIT_SECONDS`
(default 1, not 2) and then answers `200` with the local guidance and
`X-Assistant-Source: busy-fallback`, refunding the budget unit and counting no
tokens; the per-user 429 is unchanged. Local answers (`assistant_local.py`) and the
shared answer cache (short, general, first-person-free questions, stored on the
2nd identical ask, 24 h) cut provider calls further; the output cap is now 350
tokens, so a full reply is shorter (about 4-9 s est.) than the 450-token numbers
below. Daily token caps (`AI_ASSISTANT_USER_DAILY_TOKENS`, `AI_ASSISTANT_DAILY_TOKENS`)
were added next to the count caps. Scope: `POST /api/assistant/chat/` on the
single Render web service (0.5 CPU, 512 MB, one instance, persistent disk).

Goal (interpreted): no artificial "busy" refusals at realistic peaks (about
2,000 students online, a few hundred chats in the same minute), and ordinary
site requests never wait because of chat streams. Daily cost caps
(`AI_ASSISTANT_*_DAILY_*`) stay exactly as they are: they protect money, not
capacity.

**Recommendation in one line:** keep gunicorn `gthread`; take a stream slot
only for real provider calls (local, cached, policy and budget answers never
hold one); raise threads to 24 and the per-process stream cap to 16; turn the
"busy" 503 into a short wait followed by a local answer; then, for the
2,000-student page load (not chat), move files to S3 and run 2+ instances.
ASGI or a separate chat service is a later step, only if measurements ask for it.

Facts below marked **(code)** were read from this repo; **(est.)** are estimates
to confirm with the load test in section 4.

---

## 1. Current capacity

| Item | Value | Source |
|---|---|---|
| Processes × threads | `WEB_CONCURRENCY=2` × `GUNICORN_THREADS=8` = **16 request threads** | Procfile, Dockerfile **(code)** |
| Streams per process | `AI_MAX_STREAMS_PER_PROCESS=4` → **8 concurrent streams per instance** | settings.py, streaming.py **(code)** |
| Streams per user | 2 (Redis counter, fails open) | streaming.py **(code)** |
| Threads always left for ordinary requests | 16 − 8 = **8** | **(code)** |
| DB pool | 8 per process (16 total); a stream returns its connection before the provider wait (`release_db_connection`) | settings.py, assistant.py **(code)** |
| Stream length | first token ~1–3 s, full 450-token reply ~6–12 s, hard limit 60 s | **(est.)** / `AI_STREAM_MAX_SECONDS` **(code)** |

**Where it breaks.** The slot is taken in `AssistantChatView.post` *before*
`_stream` decides whether the answer is a policy block, a budget refusal, a
local fallback or a real gateway call **(code)**. So every chat, even one that
never touches the provider, uses one of the 8 slots.

By Little's law, concurrent streams = arrivals per second × seconds per stream:

| Load | Today (every chat holds a slot, ~8 s) | After redesign (40% reach the provider) |
|---|---|---|
| 60 chats/min | 1/s × 8 s = 8 → at the cap | 0.4 × 8 = 3 |
| 300 chats/min | 5/s × 8 s = **40 → 32 refused with 503** | 2 × 8 = **16** |
| 600 chats/min | 80 | 32 |

So today the instance starts answering "busy" at roughly **60 chats/min**. A
slow provider (20 s replies) halves that.

**The other bottleneck is not chat.** At ~140 req/s per M2 core
(docs/scaling.md), 0.5 vCPU serves roughly **30–40 ordinary req/s (est.)**.
2,000 students online, each clicking every 10–20 s, is 100–200 req/s. No chat
design fixes that; only more CPU does (step 3.C). Memory: 2 workers at
75–120 MB RSS each plus the master ≈ 200–270 MB of 512 MB **(est., from
docs/scaling.md)**, so a third worker does not fit safely, but more threads do.

---

## 2. Options

| | What | Capacity gain | Risk | Render cost |
|---|---|---|---|---|
| **a. More gthread threads** | `GUNICORN_THREADS=24`, `AI_MAX_STREAMS_PER_PROCESS=16` | 8 → 32 streams per instance; idle threads are cheap (a stream waits on a socket and releases the GIL; ~0.2–0.5 MB RSS each incl. TLS buffers, est.) | Low: env vars only. More threads contend for 0.5 CPU, but streams use little CPU (one `json.loads` per token, est. < 10% of a core at 32 streams). | $0 |
| **b. ASGI for chat, sync elsewhere** | uvicorn worker, async Django view, `httpx.AsyncClient` stream | Thousands of streams per process | **High in the same process.** Under ASGI every sync DRF view runs through `sync_to_async(thread_sensitive=True)`, i.e. on one shared thread per process, so the rest of the API loses its parallelism. DRF `APIView` has no async support: auth (`VersionedJWTAuthentication`), throttles, `require_feature` must be re-done by hand. `ai_usage` keeps its sink in `threading.local` **(code)**, which breaks across awaits. | $0, but days of work and a risky deploy |
| **c. Separate chat service** | Second Render web service from the same repo, only the chat route (sync gthread or async), on `chat.naseebedu.com` | Isolates chat completely; scales on its own | Medium: new CORS origin, frontend base URL for one call, second deploy. Auth is easy: the access token is a Bearer header; the refresh cookie is only on `/api/auth/` **(code)**, so no cookie-domain change. No disk needed. | +$7/mo (Starter) to +$25/mo (Standard) |
| **d. Non-streaming short answers** | Local/cached/policy/budget answers returned at once, no slot | Removes most slot use (the big win) | Low. For *provider* answers, non-streaming does not help: the thread still waits the full reply, and the user sees nothing for 8 s. | $0 |
| **e. Horizontal scaling** | 2+ instances, CPU autoscaling | Linear for both chat and ordinary requests; zero-downtime deploys | Blocked today: a service with a persistent disk cannot have more than one instance and deploys stop-then-start (docs/scaling.md "Files off the disk"; production refuses local disk unless `FILE_STORAGE_SINGLE_INSTANCE=True` **(code)**). render.yaml does **not** define the web service (dashboard-managed, comment at its top **(code)**), so the disk setting must be checked in the dashboard. S3/R2 storage and `migrate_files_to_object_storage` already exist. | Standard 1 CPU/2 GB ≈ $25/mo per instance + R2/S3 (cents–few $/mo) |

**Redis-wide slots?** No. The per-process semaphore protects a *local*
resource (this process's threads), so it must stay per process; a global Redis
cap would refuse chats on an idle instance while another is full. Keep the
per-user Redis counter (abuse control). The provider's own rate limit is
handled by the daily budgets and the fallback model, not by a slot count.

---

## 3. Recommended path

Each step ships and is verified on its own. Steps A and B are for the
builders working in `assistant.py` / `streaming.py`; this doc does not change code.

### A. Slots only for provider calls (code, low risk)

1. `backend/apps/admissions/assistant.py`, `AssistantChatView.post`: move
   `acquire_stream_slot(user)` from before `_stream` to inside `_stream`,
   *after* `blocked` / `consume_provider_budget` / the local-or-cache decision
   and only when `use_gateway` is true. Local, cached, policy and
   budget-exhausted replies take no slot and no provider stream.
2. Return those non-provider answers as one plain response (or a stream of an
   already-built string; either way no thread waits). Keep
   `X-Assistant-Source` so the frontend and logs are unchanged.
3. Release order stays as now (`GuardedStream` → `finish` → `slot.release`),
   and `release_db_connection()` stays before the provider wait.
4. Refund the budget unit (`consume_provider_budget`) if no slot is obtained
   and the reply is served locally, so a busy moment does not cost a user's
   daily quota. (Check with the `ai_budget.py` owner.)
5. Tests: a local/cached reply succeeds while the semaphore is fully taken; the
   slot count returns to zero after normal, error and client-disconnect paths.

### B. No hard "busy" (code, low risk)

`backend/apps/admissions/streaming.py`, `acquire_stream_slot`:

1. Acquire the process semaphore with `blocking=True, timeout=AI_STREAM_SLOT_WAIT_SECONDS`
   (new setting, default 2). A 2 s wait holds one thread for at most 2 s.
2. If the wait fails, do **not** return 503: answer with the local guidance plus
   one line ("Naseeb AI is very busy; here is the short answer, ask again for
   more detail"), status 200, `X-Assistant-Source: busy-fallback`, and log
   `assistant_busy_fallback` so it shows up in metrics.
3. `user_limit` (2 streams per user) stays a 429; that is abuse control, not capacity.
4. Frontend: no change needed for the 200 path. The existing `busy` message in
   `AssistantCenter.jsx` stays for real 503s (assistant switched off).

### C. Threads and caps (config only, after A and B are deployed)

Render dashboard → web service → Environment:

| Variable | Now | New | Why |
|---|---|---|---|
| `WEB_CONCURRENCY` | 2 | 2 | A third worker does not fit 512 MB safely. |
| `GUNICORN_THREADS` | 8 | 24 | Threads are cheap while waiting on sockets. |
| `AI_MAX_STREAMS_PER_PROCESS` | 4 | 16 | 32 streams per instance; 8 threads per process always left for the site. |
| `DB_POOL_MAX_SIZE` | 8 | 8 | Streams hold no connection; more than ~8 DB-busy requests per process won't run faster on 0.5 CPU. Pool waits (`DB_POOL_TIMEOUT=10`) queue the rest. Connections stay 2 × 8 = 16. |
| `AI_USER_MAX_CONCURRENT_STREAMS` | 2 | 2 | |

Memory budget per worker: ~110 MB base + 24 threads × ~0.5 MB ≈ 125 MB; two
workers + master ≈ 300 MB of 512 MB. Alert at 420 MB (Render metrics). The
start command does not change (Procfile already reads both variables), so this
is a plain env change plus restart. `--timeout 120` is fine: gthread
heartbeats come from the main thread, not from the request threads.

Optional, same step: reuse one TLS connection pool to the gateway (a module-level
`httpx.Client` or `urllib3.PoolManager` instead of a new `urlopen` per reply)
to save a TLS handshake per chat on the 0.5 CPU.

### D. More CPU for the 2,000-student peak (infra, medium risk)

Chat after A–C fits; ordinary page load at 2,000 students does not fit 0.5 CPU.

1. Move files off the disk exactly as in docs/scaling.md "File storage"
   (`STORAGE_BACKEND=s3`, `migrate_files_to_object_storage`, verify, detach disk).
2. Switch the service to Standard (1 CPU, 2 GB), `WEB_CONCURRENCY=3`,
   `GUNICORN_THREADS=24`, `AI_MAX_STREAMS_PER_PROCESS=16`, then 2 instances
   (autoscale 2–4 on CPU 60%). Per-process caps scale with instances by themselves.
3. Connections: 2 × instances × 3 × 8 during an overlapping deploy = 96 for 2
   instances; at 3+ instances use PgBouncer (docs/scaling.md "PgBouncer").
4. Set the pre-deploy command `cd backend && python manage.py migrate_locked --noinput`.
   Deploys become zero-downtime once the disk is gone.

### E. Only if measured: separate chat service (option c)

Trigger: `assistant_busy_fallback` above ~1% of chats at peak, or stream threads
regularly at the cap after D. Then deploy the same repo as a second web
service whose only public route is the chat view (same gthread start command,
`GUNICORN_THREADS=64`, `AI_MAX_STREAMS_PER_PROCESS=56`, no disk), add
`https://chat.naseebedu.com` to CORS, and point only `streamAssistant` in
`frontend/src/api.js` at it. Async (option b) goes in that service, never in
the main one.

### Expected result (est., verify in section 4)

| | Today | After A–C | After D (2 × Standard) |
|---|---|---|---|
| Concurrent provider streams | 8 | 32 | 96 |
| Chats/min before any fallback (40% to provider, 8 s) | ~60 | ~600 | ~1,800 |
| Threads always free for the site | 8 | 16 | 48 |
| Ordinary req/s | ~30–40 | ~30–40 | ~150–200 |

---

## 4. Load test

Run against a local server that matches production: gunicorn with the same
flags, Postgres, Redis, and a fake gateway. Never point a load test at the real
gateway (it spends the budget) or at production.

**Fake gateway** (`scratch` script, not committed), e.g. a tiny `aiohttp` app
on `:9999/v1/chat/completions` that returns an SSE stream: first chunk after
`FIRST_TOKEN_MS` (default 1500), then 120 `data: {"choices":[{"delta":{"content":"word "}}]}`
lines every 60 ms, a usage event, `data: [DONE]`. Env `SLOW=1` makes it 25 s
total, to test a slow provider.

**Server:**
```
AI_GATEWAY_URL=http://127.0.0.1:9999/v1/chat/completions AI_GATEWAY_API_KEY=test \
AI_ASSISTANT_DAILY_BUDGET=0 AI_ASSISTANT_USER_DAILY_LIMIT=0 \
WEB_CONCURRENCY=2 GUNICORN_THREADS=24 AI_MAX_STREAMS_PER_PROCESS=16 \
taskset/`cpulimit` to 0.5 CPU, or docker run --cpus=0.5 --memory=512m
```
(Check the budget settings: if `0` means "AI off" for the platform budget,
set a large number instead.)

**Locust outline** (`locustfile.py`):
- Setup: create 500 test students via a management command or fixture; each
  Locust user logs in once and keeps the Bearer token.
- `ChatUser` (weight 1): `POST /api/assistant/chat/` with a mix of 60%
  questions the local/cache path answers and 40% open-ended ones; read the
  body to the end (`stream=True`, iterate); record time to first byte, total
  time, status, `X-Assistant-Source`. Think time 20–40 s.
- `BrowseUser` (weight 4): the 5 most-used GET endpoints of the student
  dashboard (take them from access logs), think time 5–15 s.
- Ramp to 300 chats/min plus browsing, hold 10 min; then 600 chats/min; then
  `SLOW=1`.

**Pass criteria:**
- 0 responses with 503 from chat; `busy-fallback` < 1% at 300 chats/min.
- Browse p95 unchanged (within 20%) compared with a browse-only run at the same
  req/s; no `PoolTimeout` in logs.
- Chat time to first byte p95 < 3 s with the normal fake gateway.
- RSS per worker < 180 MB; total < 420 MB.
- After the run, Redis `ai-streams:*` keys are gone or at 0 (no leaked slots),
  including a run where Locust aborts half the streams mid-body.

k6 works the same way (`http.post` with `responseType: 'text'`, two scenarios
with `constant-arrival-rate`).

**Production check after each step:** Render metrics CPU/RAM, and from logs the
counts of `assistant_request mode=*`, `assistant_busy_fallback`,
`assistant_provider_failure`, and p95 `duration_ms`.

---

## 5. Rollback

| Step | Rollback | Time |
|---|---|---|
| C (env) | Set `GUNICORN_THREADS=8`, `AI_MAX_STREAMS_PER_PROCESS=4` back in the dashboard; the service restarts. | ~2 min |
| A, B (code) | Render "Rollback" to the previous deploy, or revert the commit. No migrations involved, so the rollback is safe. Setting `AI_STREAM_SLOT_WAIT_SECONDS=0` restores the old immediate refusal path without a deploy. | ~5 min |
| D (storage, instances) | Scale to 1 instance first. Storage: keep the disk attached and unchanged until S3 has been verified for a week; switching back is `STORAGE_BACKEND=filesystem` + `FILE_STORAGE_SINGLE_INSTANCE=True`, but files uploaded to S3 in between must be copied back. Plan downgrade: switch the plan back to Starter in the dashboard. | 10–30 min |
| E (chat service) | Point `streamAssistant` back to the main API (frontend redeploy); suspend the chat service. | ~5 min |

Watch for 30 minutes after every step: 5xx rate, chat 503/429 counts, RAM,
`PoolTimeout`, and a manual sign-in plus one chat in the browser.
