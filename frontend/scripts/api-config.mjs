// Where the browser reaches the API, checked at build time so a deploy can
// never end up fetching /api from a static host that answers with index.html.
//
//   VITE_API_URL relative ("/api", the default): the frontend host proxies
//     /api to Django, same origin as the app. Needs, depending on the host:
//       Vercel (VERCEL=1):    NASEEB_API_ORIGIN (read by middleware.js at runtime;
//                             set it for the Build step too so this check sees it)
//       nginx image (Docker): API_UPSTREAM (rendered into nginx.conf)
//       vite dev / preview:   API_PROXY_TARGET (default http://127.0.0.1:8000)
//   VITE_API_URL absolute: the browser calls the API directly. Same site
//     (app.example.com + api.example.com) works with SameSite=Lax; another
//     site needs AUTH_REFRESH_COOKIE_SAMESITE=None on the backend and loses
//     the session in browsers that block third-party cookies.

export function isRelativeApiUrl(apiUrl) {
  return !apiUrl || !/^[a-z][a-z\d+.-]*:\/\//i.test(apiUrl)
}

// An http(s) origin with no path, e.g. https://naseeb-api.onrender.com.
export function parseApiOrigin(value, name) {
  let url
  try { url = new URL(value) } catch { throw new Error(`${name}: expected an origin like https://api.example.com, got ${JSON.stringify(value)}`) }
  if (!/^https?:$/.test(url.protocol) || url.pathname.replace(/\/$/, '') || url.search) {
    throw new Error(`${name}: expected an origin like https://api.example.com (no path), got ${JSON.stringify(value)}`)
  }
  return url.origin
}

// Throws with an actionable message when this build could not reach the API.
export function checkBuildApiConfig(env) {
  const apiUrl = env.VITE_API_URL || '/api'
  if (!isRelativeApiUrl(apiUrl)) return { mode: 'direct', apiUrl }
  if (env.VERCEL) {
    if (!env.NASEEB_API_ORIGIN) {
      throw new Error(
        'VITE_API_URL is relative (' + apiUrl + ') but NASEEB_API_ORIGIN is not set: on Vercel, /api would be ' +
        'served index.html. Set NASEEB_API_ORIGIN (e.g. https://naseeb-api.onrender.com) for Production, Preview ' +
        'and the build. See docs/deployment-auth.md.',
      )
    }
    return { mode: 'vercel-proxy', apiUrl, upstream: parseApiOrigin(env.NASEEB_API_ORIGIN, 'NASEEB_API_ORIGIN') }
  }
  return { mode: 'proxy', apiUrl }
}
