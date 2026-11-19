# Sign-in sessions in production

The refresh token is an HttpOnly cookie (`naseeb_refresh`, `Path=/api/auth/`)
set by the API on sign-in and refresh and cleared on logout; the access token
lives only in the page's memory. Script on the page (an XSS) can read neither
the refresh token nor any token in storage. Logout revokes the whole sign-in
session on the server (every rotation of that sign-in), not just one token.

The cookie only reaches the API when the browser treats the request as
first-party, so **the app and the API must share an origin or a site**. Pick
one of the layouts below. **Production uses layout C:** `https://www.naseebedu.com` calls `https://api.naseebedu.com/api` directly. Vercel Preview deployments use layout A, because their `vercel.app` site differs from the API site.

Every layout keeps the CSRF protection of the cookie endpoints: refresh and
logout require the `X-Requested-With` header and an `Origin` that is the API's
own origin or listed in `CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_ORIGIN_REGEXES` or
`CSRF_TRUSTED_ORIGINS` (wildcards such as `https://*.example.com` work).

## A. Vercel Preview — same origin through a proxy

`frontend/middleware.js` (Vercel Routing Middleware) proxies `/api/*` to the
API, so the browser only ever talks to the Vercel origin.

Vercel project (root directory `frontend/`), Environment Variables, for
**Preview**, available at build time too (Production settings are in C):

| Variable | Value |
| --- | --- |
| `NASEEB_API_ORIGIN` | the API origin, no path: `https://api.naseebedu.com` (or the Render service origin) |
| `VITE_API_URL` | leave unset (defaults to `/api`) |

Without `NASEEB_API_ORIGIN` the build fails (`scripts/api-config.mjs`), and a
deployment that somehow lacks it answers `/api/*` with a JSON 502
(`api_proxy_unconfigured`), never with `index.html` (`vercel.json` excludes
`/api/` from the SPA rewrite).

Render web service (environment group `naseeb-backend`):

| Variable | Value |
| --- | --- |
| `CORS_ALLOWED_ORIGINS` | `https://naseeb-edu-demo.vercel.app` (plus any custom domain) |
| `CORS_ALLOWED_ORIGIN_REGEXES` | only if Preview deployments must sign in: `^https://naseeb-edu-[a-z0-9-]+-<vercel-team-slug>\.vercel\.app$`. Always anchor it to your team slug: anyone can create a `*.vercel.app` project. |
| `AUTH_REFRESH_COOKIE_SAMESITE` | `Lax` (default) |
| `NUM_PROXIES` | `2` (Vercel's proxy + Render's edge). Check once with a request log that the client IP is right: throttles and login lockouts key on it. |
| `ALLOWED_HOSTS` | the `onrender.com` host (Vercel forwards to it) |

To verify before relying on it: uploads (documents up to
`DOCUMENT_MAX_UPLOAD_SIZE`, 25 MB by default) and the assistant's streamed
replies pass through the Vercel proxy; test both on a Preview deployment.

## B. Docker / nginx image — same origin through nginx

Build the frontend image with `VITE_API_URL=/api` (the default) and
`API_UPSTREAM` set to where nginx can reach Django, e.g.
`--build-arg API_UPSTREAM=https://api.internal.example.com` (or
`http://backend:8000` as in `docker-compose.yml`). `scripts/render-nginx-conf.mjs`
renders the `/api/` proxy location into `nginx.conf`; the build fails if
`API_UPSTREAM` is missing. Put the app's public origin in
`CORS_ALLOWED_ORIGINS` and count nginx in `NUM_PROXIES`.

## C. Production — same site, API called directly

The production frontend is `https://www.naseebedu.com`; the API is
`https://api.naseebedu.com`. Both use HTTPS and belong to the same site,
so the API's host-only HttpOnly cookie stays first-party. The frontend sends
cross-origin API calls with credentials (`api.js` already does this).

| Service | Setting | Production value |
| --- | --- | --- |
| Vercel | `VITE_API_URL` | `https://api.naseebedu.com/api` |
| Render | `CORS_ALLOWED_ORIGINS` | `https://www.naseebedu.com` |
| Render | `CSRF_TRUSTED_ORIGINS` | `https://www.naseebedu.com` |
| Render | `ALLOWED_HOSTS` | `api.naseebedu.com` (plus the Render service host if needed) |
| Render | `AUTH_REFRESH_COOKIE_SAMESITE` | `Lax` |
| Render | `AUTH_REFRESH_COOKIE_SECURE` | `True` |
| Render | `AUTH_REFRESH_COOKIE_DOMAIN` | leave unset (host-only) |
| Render | `NUM_PROXIES` | `1` while the Cloudflare `api` record is **DNS only**; the orange cloud adds a hop. Measure it, do not guess: see [Measure `NUM_PROXIES`](#measure-num_proxies) |

Production does not need `NASEEB_API_ORIGIN` for direct API calls. Keep Preview's
`VITE_API_URL` unset and configure `NASEEB_API_ORIGIN` in Preview as described in A.
### Measure `NUM_PROXIES`

A wrong value either puts every user behind one proxy address (shared throttles and
lockouts) or lets a client choose its own address, so measure it once before schools sign in.
The `Procfile` start command appends the raw `X-Forwarded-For` header to every access-log
line as `xff="..."`. Paste the same command into the Render start command.

1. From a phone on mobile data, open `https://www.naseebedu.com/` and note your public IP
   (any "what is my IP" page).
2. In the Render service logs, find your `/api/` request and read its `xff="..."` list.
3. `NUM_PROXIES` is your IP's position counted from the right: `xff="<you>"` is `1`,
   `xff="<you>, <proxy>"` is `2`.
4. Set it in the `naseeb-backend` environment group and redeploy.

The service also answers on its `onrender.com` host, and a request there skips Cloudflare, so
it has one hop fewer. With the orange cloud and `NUM_PROXIES=2`, a client using that host can
send its own `X-Forwarded-For` and pick the address that throttles and lockouts see. Keep the
`api` record **DNS only** (value `1`) or accept that limit knowingly.

The log line then contains client IPs; drop `--access-logformat` again once the value is
confirmed if you do not want them in the logs.
If additional frontend domains also serve the app, explicitly add those origins
rather than allowing arbitrary Vercel projects.

`frontend/vercel.json` sends frame, MIME, referrer, permissions and HSTS headers
on pages and assets. Its CSP is **report-only**, with `https://api.naseebedu.com`
in `connect-src`; it logs policy violations without blocking resources. Inline
boot scripts have no hashes in this static policy yet. Review violations,
Preview behavior and private file-storage origins before enforcing CSP. The nginx
image continues to generate its enforced CSP with build-time script hashes.

## D. Different sites (last resort)

For a frontend and API on unrelated domains (e.g. `*.vercel.app` calling
`*.onrender.com` directly): `VITE_API_URL=https://<api>/api`,
`AUTH_REFRESH_COOKIE_SAMESITE=None` (the cookie is then always `Secure`) and the
frontend origin in `CORS_ALLOWED_ORIGINS`. Browsers that block third-party
cookies (Safari by default, Firefox strict mode, Chrome when the user opts in)
drop the cookie, so those users are signed out on every reload. Prefer A.

## Backend settings reference

| Variable | Default | Notes |
| --- | --- | --- |
| `AUTH_REFRESH_COOKIE_SAMESITE` | `Lax` | `Strict`, `Lax` or `None` (forces `Secure`) |
| `AUTH_REFRESH_COOKIE_SECURE` | on unless `DEBUG` | always on in production and with `None` |
| `AUTH_REFRESH_COOKIE_PATH` | `/api/auth/` | must match the path the browser uses for `/auth/` |
| `AUTH_REFRESH_COOKIE_DOMAIN` | unset (host-only) | |
| `AUTH_REFRESH_COOKIE_NAME` | `naseeb_refresh` | |
| `CORS_ALLOW_CREDENTIALS` | `True` (code) | needed for C and D |

## Rolling it out

1. Deploy the backend first (migration `users.0017_revoked_refresh_session`
   runs in the pre-deploy command), then the frontend right after. While the
   old frontend is still live, sign-in works but its sessions end after the
   30-minute access token.
2. Everyone signs in once more: on first load the new frontend sends the
   refresh token the old one left in localStorage to `/api/auth/logout/` (so it
   is revoked) and deletes the old keys.
3. The daily `flush_expired_tokens` cron also removes expired signed-out
   sessions.
