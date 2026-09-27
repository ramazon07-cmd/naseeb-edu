// Browser storage that belongs to one signed-in account. Keys carry the user
// id so a shared computer never shows (or uploads) one person's data for the
// next, and everything here is removed on sign-out.

export const USER_STORAGE = {
  assessment: 'naseeb-find-personality-v1',
  assessmentPending: 'naseeb-assessment-pending-v1',
  screenTime: 'naseeb-screen-time-pending-v1',
  parentChild: 'naseeb-parent-selected-child-v1',
  onboardingDraft: 'naseeb-onboarding-draft-v1',
}

// Per-tab state (sessionStorage), scoped and cleared the same way.
export const USER_SESSION_STORAGE = {
  // No longer written (the open essay is in the URL); still cleared at
  // sign-out for tabs that an earlier version wrote it in.
  essayLabOpen: 'naseeb-essay-lab-open',
}

export function userStorageKey(base, userId) {
  if (userId === undefined || userId === null || userId === '') throw new Error('userStorageKey needs a user id')
  return `${base}:${userId}`
}

function safeStorage(storage) {
  try { return typeof storage === 'function' ? storage() : storage } catch { return null }
}

// Before these keys were scoped they were shared by every account on the
// device; nobody can tell whose data they hold, so they are discarded.
export function dropLegacySharedKeys(storage) {
  const target = safeStorage(storage)
  if (!target) return
  for (const base of Object.values(USER_STORAGE)) {
    try { target.removeItem(base) } catch { /* storage unavailable */ }
  }
}

export function clearUserStorage(storage, userId, bases = USER_STORAGE) {
  const target = safeStorage(storage)
  if (!target || userId === undefined || userId === null) return
  for (const base of Object.values(bases)) {
    try { target.removeItem(userStorageKey(base, userId)) } catch { /* storage unavailable */ }
  }
}

export function clearUserSessionStorage(storage, userId) {
  clearUserStorage(storage, userId, USER_SESSION_STORAGE)
  const target = safeStorage(storage)
  for (const base of Object.values(USER_SESSION_STORAGE)) {
    try { target?.removeItem(base) } catch { /* storage unavailable */ }
  }
}
