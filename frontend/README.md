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
`SameSite=Strict`) set by the backend on sign-in and refresh and cleared by
`POST /api/auth/logout/`; the access token is kept in memory only and renewed
silently on page load and after a 401. Nothing secret is stored in
localStorage (`naseeb-session` is only a "signed in" flag; removing it signs
out the other tabs). A production frontend must be on the same site as the API
(`app.example.com` + `api.example.com`, or one origin behind a proxy), and
its origin must be in the backend's `CORS_ALLOWED_ORIGINS`.

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
