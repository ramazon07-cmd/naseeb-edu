// Comments and suggestions in the student's editor: what to show, in which
// order, how often to ask the server, and how history names people.
// Framework-free: runs in the browser and under plain `node`.

export const POLL_ACTIVE_MS = 5000
export const POLL_IDLE_MS = 30000

// Faster while someone else (the counselor) has the essay open.
export const collabPollDelay = (othersActive) => (othersActive ? POLL_ACTIVE_MS : POLL_IDLE_MS)

// Cards for the margin / sheet: pending suggestions and open threads in the
// order their text appears (positions: Map 'kind:id' -> doc position; items
// whose text is gone go last), then resolved threads.
export function feedbackItems(threads = [], suggestions = [], positions = new Map()) {
  const key = (item) => `${item.kind}:${item.id}`
  const place = (item) => (positions.has(key(item)) ? positions.get(key(item)) : Infinity)
  const open = [
    ...suggestions.filter((item) => item.status === 'pending').map((item) => ({ ...item, kind: 'suggestion' })),
    ...threads.filter((item) => item.status !== 'resolved').map((item) => ({ ...item, kind: 'thread' })),
  ].map((item) => ({ ...item, anchored: positions.has(key(item)) }))
  open.sort((a, b) => place(a) - place(b) || String(a.created_at).localeCompare(String(b.created_at)) || a.id - b.id)
  const resolved = threads.filter((item) => item.status === 'resolved').map((item) => ({ ...item, kind: 'thread', anchored: positions.has(`thread:${item.id}`) }))
  return { open, resolved }
}

// "Comments · N": what still waits for the student.
export function openCount(threads = [], suggestions = []) {
  return suggestions.filter((item) => item.status === 'pending').length + threads.filter((item) => item.status !== 'resolved').length
}

// Ids of the pending suggestions still in the text (what "Accept all" decides).
export function acceptAllIds(suggestions = [], anchoredSuggestionIds = new Set()) {
  return suggestions.filter((item) => item.status === 'pending' && anchoredSuggestionIds.has(item.id)).map((item) => item.id)
}

// A thread or suggestion list after the server answered for one of them.
export function replaceById(list, next) {
  return list.some((item) => item.id === next.id) ? list.map((item) => (item.id === next.id ? next : item)) : [...list, next]
}

// History line for a version made by feedback or decisions, as a message key
// plus its values: "Madina suggested 2 edits", "Ramazon accepted 1 suggestion".
// Null for ordinary versions (they keep their usual title).
export function historyLine(checkpoint) {
  const name = checkpoint?.author_name
  const detail = checkpoint?.detail || {}
  switch (checkpoint?.kind) {
    case 'suggest': {
      const n = Number(detail.suggestions) || 0
      return { key: n === 1 ? '{name} suggested 1 edit' : '{name} suggested {n} edits', n, name }
    }
    case 'comment':
      return { key: '{name} left a comment', n: 1, name }
    case 'decision': {
      const accepted = Number(detail.accepted) || 0
      const rejected = Number(detail.rejected) || 0
      if (accepted && rejected) return { key: '{name} accepted {a} and rejected {r} suggestions', n: accepted + rejected, name, a: accepted, r: rejected }
      if (accepted) return { key: accepted === 1 ? '{name} accepted 1 suggestion' : '{name} accepted {n} suggestions', n: accepted, name }
      return { key: rejected === 1 ? '{name} rejected 1 suggestion' : '{name} rejected {n} suggestions', n: rejected, name }
    }
    default:
      return null
  }
}
