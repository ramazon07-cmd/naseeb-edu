// Where an assistant answer came from, read from the X-Assistant-Source header.
// Only 'gateway' answers are written by the AI model; the rest are built-in text.
// Older servers send no header: those answers keep the plain assistant name.

const SOURCES = {
  gateway: { ai: true, note: '' },
  'local-fallback': { ai: false, note: 'AI isn’t available right now, so this is general guidance from Naseeb’s built-in tips.' },
  'budget-exhausted': { ai: false, note: 'Today’s AI limit is used up, so this is general guidance from Naseeb’s built-in tips.' },
  policy: { ai: false, note: 'This is a standard Naseeb safety reply.' },
}

export function assistantSource(header) {
  const key = String(header || '').trim().toLowerCase()
  if (!key) return null
  return { key, ...(SOURCES[key] || SOURCES['local-fallback']) }
}
