// A Telegram @username as the bot checks it: 5-32 characters of a-z, 0-9 and _, compared without case or '@'.
export const TELEGRAM_USERNAME_PATTERN = /^[a-z0-9_]{5,32}$/

export const normalizeTelegramUsername = (value) => String(value ?? '').trim().replace(/^@+/, '').trim().toLowerCase()

// '' when the value is fine to save (or empty: nothing to save), otherwise which rule it breaks.
export function telegramUsernameProblem(value) {
  const username = normalizeTelegramUsername(value)
  if (!username) return ''
  if (!/^[a-z0-9_]*$/.test(username)) return 'characters'
  if (username.length < 5) return 'short'
  if (username.length > 32) return 'long'
  return ''
}
