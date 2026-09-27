// Pure helpers for the document tabs rail (tested under plain node).

export const MAX_TABS = 100

// Tabs in reading order with their depth: [{ tab, depth, children }].
export function tabTree(tabs) {
  const sorted = [...tabs].sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.id - b.id)
  return sorted.filter((tab) => tab.parent == null).map((tab) => ({ tab, children: sorted.filter((child) => child.parent === tab.id) }))
}

export function siblingsOf(tabs, tab) {
  return [...tabs].filter((item) => (item.parent ?? null) === (tab.parent ?? null))
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.id - b.id)
}

// New sibling order after moving `tab` by `offset` (-1 up, +1 down), or null at an end.
export function movedOrder(tabs, tab, offset) {
  const ids = siblingsOf(tabs, tab).map((item) => item.id)
  const from = ids.indexOf(tab.id)
  const to = from + offset
  if (from < 0 || to < 0 || to >= ids.length) return null
  ids.splice(from, 1)
  ids.splice(to, 0, tab.id)
  return ids
}

// Deleting a tab also deletes its sub-tabs; a document keeps at least one tab.
export function canDeleteTab(tabs, tab) {
  return tabs.some((item) => item.id !== tab.id && item.parent !== tab.id)
}

// Opens document tabs. When clicks overlap, the latest one wins: a slow fetch
// for an earlier click never replaces the tab clicked after it.
export function createTabOpener({ isOpen, hasSession, fetchTab, openSession, setLoading, show, fail }) {
  let latest = 0
  return async function openTab(id, detail = null) {
    const mine = ++latest
    if (isOpen(id) || hasSession(id)) {
      setLoading(null)
      if (!isOpen(id)) show(id)
      return true
    }
    setLoading(id)
    let tab = detail
    try {
      tab ??= await fetchTab(id)
    } catch (error) {
      if (mine === latest) {
        setLoading(null)
        fail(error)
      }
      return false
    }
    if (mine !== latest) return false
    openSession(tab)
    setLoading(null)
    show(id)
    return true
  }
}
