// Pure helpers for the assistant chat: what is sent to the server and which
// questions are suggested. Chat text lives in React state only.

export const MAX_MESSAGE_LENGTH = 2000
export const HISTORY_LIMIT = 4

// History idle for longer than this is not sent again (the server drops it too).
export const HISTORY_MAX_AGE_MS = 10 * 60 * 1000

export function buildAssistantPayload(messages, language, now = Date.now()) {
  const history = (messages || [])
    .filter((message) => message && !message.local && message.content && (message.role === 'user' || message.role === 'assistant'))
    .filter((message) => !message.at || now - message.at <= HISTORY_MAX_AGE_MS || message === (messages || [])[(messages || []).length - 1])
    .slice(-HISTORY_LIMIT)
    .map(({ role, content }) => ({ role, content }))
  return { messages: history, language }
}

// Student questions are answered instantly from the student's own data (no AI cost).
const STUDENT_SUGGESTIONS = [
  'What’s my next deadline?',
  'Which tasks are overdue?',
  'How are my applications going?',
  'How do I book a meeting?',
  'Help me plan my essay',
]

const COUNSELOR_SUGGESTIONS = [
  'How many students are at risk?',
  'How many tasks are overdue?',
  'Help me plan my student check-ins',
]

// School admins ask about their school's totals; no personal records are involved.
const ADMIN_SUGGESTIONS = COUNSELOR_SUGGESTIONS.slice(0, 2)

export function assistantSuggestions(role) {
  if (role === 'admin') return ADMIN_SUGGESTIONS
  return role === 'counselor' ? COUNSELOR_SUGGESTIONS : STUDENT_SUGGESTIONS
}
