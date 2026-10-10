# Sign-in sessions in production

The refresh token is an HttpOnly cookie (`naseeb_refresh`, `Path=/api/auth/`)
set by the API on sign-in and refresh and cleared on logout; the access token
lives only in the page's memory. Script on the page (an XSS) can read neither
the refresh token nor any token in storage. Logout revokes the whole sign-in
session on the server (every rotation of that sign-in), not just one token.

The cookie only reaches the API when the browser treats the request as
first-party, so **the app and the API must share an origin or a site**. Pick
one of the layouts below; the first is the recommended one.

Every layout keeps the CSRF protection of the cookie endpoints: refresh and
logout require the `X-Requested-With` header and an `Origin` that is the API's
own origin or listed in `CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_ORIGIN_REGEXES` or
`CSRF_TRUSTED_ORIGINS` (wildcards such as `https://*.example.com` work).

## A. Vercel frontend, API on Render (current hosting) — same origin through a proxy

`frontend/middleware.js` (Vercel Routing Middleware) proxies `/api/*` to the
API, so the browser only ever talks to the Vercel origin.

Vercel project (root directory `frontend/`), Environment Variables, for
Production **and** Preview, available at build time too:

| Variable | Value |
| --- | --- |
| `NASEEB_API_ORIGIN` | the API origin, no path: `https://<render-service>.onrender.com` |
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

## C. Same site, API called directly (`app.example.com` + `api.example.com`)

Frontend: `VITE_API_URL=https://api.example.com/api` (the nginx image's CSP `connect-src`
picks the origin up). Backend: `CORS_ALLOWED_ORIGINS=https://app.example.com`,
`AUTH_REFRESH_COOKIE_SAMESITE=Lax` (or `Strict`).

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

1. Deploy the backend first (migration `users.0015_revoked_refresh_session`
   runs in the pre-deploy command), then the frontend right after. While the
   old frontend is still live, sign-in works but its sessions end after the
   30-minute access token.
2. Everyone signs in once more: on first load the new frontend sends the
   refresh token the old one left in localStorage to `/api/auth/logout/` (so it
   is revoked) and deletes the old keys.
3. The daily `flush_expired_tokens` cron also removes expired signed-out
   sessions.
