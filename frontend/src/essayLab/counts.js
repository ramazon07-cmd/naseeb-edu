// Counts for the status counter (tested under plain node).

const COUNTER_KEY = 'naseeb-essay-counter'
export const COUNT_MODES = ['words', 'chars', 'charsNoSpaces', 'pages']
const DEFAULT_SETTING = { mode: 'words', scope: 'tab' }

export function readCounter() {
  try {
    const value = JSON.parse(window.localStorage.getItem(COUNTER_KEY) || 'null')
    if (value && COUNT_MODES.includes(value.mode) && ['tab', 'document'].includes(value.scope)) return value
  } catch { /* use the default */ }
  return DEFAULT_SETTING
}

export function writeCounter(value) {
  try { window.localStorage.setItem(COUNTER_KEY, JSON.stringify(value)) } catch { /* a per-device convenience only */ }
}

// Counts for the open tab (live from the editor) and for the whole document
// (the other tabs' last saved counts plus the live open tab).
export function documentStats(tabs, activeId, live) {
  const liveTab = live && live.tab === activeId ? live : null
  const open = tabs.find((tab) => tab.id === activeId)
  const tab = {
    words: liveTab ? liveTab.wordCount : open?.word_count ?? 0,
    chars: liveTab ? liveTab.charCount : open?.char_count ?? 0,
    charsNoSpaces: liveTab ? liveTab.charCountNoSpaces : open?.char_count_no_spaces ?? 0,
  }
  const document = { ...tab }
  for (const other of tabs) {
    if (other.id === activeId) continue
    document.words += other.word_count ?? 0
    document.chars += other.char_count ?? 0
    document.charsNoSpaces += other.char_count_no_spaces ?? 0
  }
  return { tab, document }
}
