// "Share with counselor": essays are private to the student until shared.

export const isShared = (essay) => Boolean(essay?.shared_with_counselor)

// Sets the sharing state (idempotent on the server) and returns the saved summary.
export function setSharing(api, essay, shared) {
  return shared ? api.shareEssay(essay.id) : api.unshareEssay(essay.id)
}

// Only the sharing fields of a saved summary, so a list or editor copy keeps its own text.
export function sharingFields(saved) {
  return { id: saved.id, shared_with_counselor: Boolean(saved.shared_with_counselor), shared_at: saved.shared_at ?? null }
}
