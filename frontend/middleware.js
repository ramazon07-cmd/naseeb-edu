// Vercel Routing Middleware: /api/* is proxied to the Django API, so the app
// and the API share one origin and the HttpOnly refresh cookie is first-party.
// NASEEB_API_ORIGIN (e.g. https://naseeb-api.onrender.com) is read at request
// time; without it /api answers a JSON 502 instead of the SPA's index.html.
// See docs/deployment-auth.md.

export const config = { matcher: '/api/:path*' }

const json = (status, body) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
})

export function apiTarget(requestUrl, origin) {
  const url = new URL(requestUrl)
  return new URL(`${url.pathname}${url.search}`, origin).toString()
}

export default function middleware(request, env = globalThis.process?.env ?? {}) {
  const origin = (env.NASEEB_API_ORIGIN || '').trim().replace(/\/+$/, '')
  if (!/^https?:\/\/[^/]+$/.test(origin)) {
    return json(502, { detail: 'The API proxy is not configured (NASEEB_API_ORIGIN).', code: 'api_proxy_unconfigured' })
  }
  // What @vercel/functions' rewrite() returns: Vercel fetches the target and
  // streams its response (status, body, Set-Cookie) back under this origin.
  return new Response(null, { headers: { 'x-middleware-rewrite': apiTarget(request.url, origin) } })
}
