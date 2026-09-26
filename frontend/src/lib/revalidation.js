// Remembers the ETag of the last full load of one resource (e.g. the open
// conversation) so background polls can ask "changed since?" and get a 304.
// Only quiet polls of the same resource revalidate; a visible load, or a load
// after switching resources, always fetches the whole page.
export function createRevalidation() {
  let current = { key: null, etag: null }
  return {
    etagFor: (key, quiet) => (quiet && current.key === key ? current.etag : null),
    remember(key, etag) { current = { key, etag: etag || null } },
    reset() { current = { key: null, etag: null } },
  }
}
