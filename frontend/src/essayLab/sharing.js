// "Share with counselor": essays are private to the student until shared.

export const isShared = (essay) => Boolean(essay?.shared_with_counselor)

// What the counselor may do with a shared essay; the student chooses when sharing.
export const COUNSELOR_ACCESS = [
  { id: 'comment', label: 'Can comment', hint: 'Your counselor can leave comments. Only you change the text.' },
  { id: 'suggest', label: 'Can suggest edits', hint: 'Your counselor can comment and suggest edits. Nothing changes until you accept.' },
]
export const DEFAULT_ACCESS = 'suggest'

export const accessOf = (essay) => (COUNSELOR_ACCESS.some((item) => item.id === essay?.counselor_access) ? essay.counselor_access : DEFAULT_ACCESS)

// Sets the sharing state (idempotent on the server) and returns the saved summary.
// Sharing an already shared essay with another `access` only changes the access.
export function setSharing(api, essay, shared, access) {
  if (!shared) return api.unshareEssay(essay.id)
  return access ? api.shareEssay(essay.id, access) : api.shareEssay(essay.id)
}

// Only the sharing fields of a saved summary, so a list or editor copy keeps its own text.
export function sharingFields(saved) {
  return {
    id: saved.id,
    shared_with_counselor: Boolean(saved.shared_with_counselor),
    shared_at: saved.shared_at ?? null,
    ...(saved.counselor_access ? { counselor_access: saved.counselor_access } : {}),
  }
}
