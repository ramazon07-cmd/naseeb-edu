// Where an assistant answer came from, read from the X-Assistant-Source header.
// 'gateway' and 'cache' (a saved AI answer to a general question) were written by
// the AI model; the rest are built-in text. 'local' and 'cache' need no note.
// Older servers send no header: those answers keep the plain assistant name.

const SOURCES = {
  gateway: { ai: true, note: '' },
  local: { ai: false, note: '' },
  cache: { ai: true, note: '' },
  'local-fallback': { ai: false, note: 'AI isn’t available right now, so this is general guidance from Naseeb’s built-in tips.' },
  'budget-exhausted': { ai: false, note: 'AI answers are paused until tomorrow. Instant answers still work.' },
  'busy-fallback': { ai: false, note: 'AI is busy right now, so this is a quick tip. Ask again in a moment for a full answer.' },
  policy: { ai: false, note: 'This is a standard Naseeb safety reply.' },
}

export function assistantSource(header) {
  const key = String(header || '').trim().toLowerCase()
  if (!key) return null
  return { key, ...(SOURCES[key] || SOURCES['local-fallback']) }
}
