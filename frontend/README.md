# Naseeb Edu React Frontend

## Start

```bash
cp .env.example .env
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`.

## Backend connection

```env
VITE_API_URL=/api
```

`npm run dev` and `npm run preview` proxy `/api` to Django (`API_PROXY_TARGET`,
default `http://127.0.0.1:8000`), so the app and the API share one origin.

Sessions: the refresh token is an HttpOnly cookie (`Path=/api/auth/`,
`SameSite=Lax` by default) set by the backend on sign-in and refresh; logout
(`POST /api/auth/logout/`) revokes the sign-in session and clears it. The
access token is kept in memory only and renewed silently on page load and
after a 401; tabs share fresh tokens over a BroadcastChannel and take turns
through a Web Lock. Nothing secret is stored in localStorage: `naseeb-session`
(`src/sessionKeys.js`) is a sign-in id and refresh counter, and removing it
signs out the other tabs.

Production needs the app and the API on one origin (Vercel: `NASEEB_API_ORIGIN`
and `middleware.js`; nginx image: `API_UPSTREAM`) or one site. A build that
could not reach the API fails. See
[docs/deployment-auth.md](../docs/deployment-auth.md) for the exact settings.

The API client supports JWT login, automatic refresh, pagination unwrapping, JSON requests, file uploads and normalized backend validation errors.

## Palette

The light and dark palettes are described once, in
[Brand and themes](../README.md#brand-and-themes) in the root README. The
tokens are defined in `src/styles.css`.

## Production build

```bash
npm ci
npm run build
```
