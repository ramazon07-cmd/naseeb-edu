// The one localStorage key the session uses. Shared with the inline boot
// script in index.html, which gets it at build time (vite.config.js replaces
// __SESSION_HINT_KEY__), so the two can never drift apart.
export const SESSION_HINT_KEY = 'naseeb-session'

export const SESSION_KEY_PLACEHOLDER = '__SESSION_HINT_KEY__'

export function injectSessionKey(html) {
  return html.replaceAll(SESSION_KEY_PLACEHOLDER, SESSION_HINT_KEY)
}
