// Pure helpers for the assistant chat: what is sent to the server and which
// questions are suggested. Chat text lives in React state only.

export const MAX_MESSAGE_LENGTH = 2000
export const HISTORY_LIMIT = 4

export function buildAssistantPayload(messages, language) {
  const history = (messages || [])
    .filter((message) => message && !message.local && message.content && (message.role === 'user' || message.role === 'assistant'))
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

export function assistantSuggestions(role) {
  return role === 'counselor' ? COUNSELOR_SUGGESTIONS : STUDENT_SUGGESTIONS
}
