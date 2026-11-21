// Ideas tab data: profile facts load by themselves (debounced, no AI, free); AI ideas load only when
// asked for, once per call. Framework-free so the rules can be tested with a fake clock.
import { AI_DAILY_LIMIT } from './letterModel.js'

export const FACTS_DEBOUNCE_MS = 1500

export function initialIdeasState() {
  return {
    facts: [], factsLoading: false, factsError: '',
    ai: { items: [], loading: false, error: '', available: true, left: null, limit: AI_DAILY_LIMIT, asked: false, unavailable: false },
  }
}

const unavailable = (response) => response && (response.ai_available === false || response.ai_enabled === false)

export function createIdeasController({ load, onChange, debounceMs = FACTS_DEBOUNCE_MS, schedule = setTimeout, cancel = clearTimeout }) {
  let state = initialIdeasState()
  let context = null
  let lastSent = null
  let timer = null
  let factsRun = 0
  let aiRun = 0
  let disposed = false

  const set = (patch) => {
    if (disposed) return
    state = { ...state, ...patch }
    onChange?.(state)
  }
  const setAi = (patch) => set({ ai: { ...state.ai, ...patch } })
  const takeMeta = (response) => {
    const patch = {}
    if (Number.isFinite(Number(response?.ai_left)) && response.ai_left !== null) patch.left = Math.max(0, Number(response.ai_left))
    if (Number.isFinite(Number(response?.ai_limit)) && response.ai_limit) patch.limit = Number(response.ai_limit)
    if (unavailable(response)) patch.available = false
    return patch
  }

  async function fetchFacts() {
    if (!context) return
    const run = ++factsRun
    lastSent = context.draft
    set({ factsLoading: true, factsError: '' })
    try {
      const response = await load({ ...context, ai: false })
      if (run !== factsRun) return
      set({ facts: (response?.suggestions || []).filter((item) => item.kind === 'fact'), factsLoading: false })
      const meta = takeMeta(response)
      if (Object.keys(meta).length) setAi(meta)
    } catch (error) {
      if (run !== factsRun) return
      lastSent = null // try again at the next pause
      set({ factsLoading: false, factsError: error?.status === 429 ? '' : (error?.message || 'error') })
    }
  }

  return {
    get state() { return state },
    // The first load, without a pause.
    start(next) {
      context = next
      cancel(timer)
      return fetchFacts()
    },
    // Typing: facts are re-read after a pause, only when the draft really changed.
    update(next) {
      context = next
      cancel(timer)
      if (lastSent === next.draft) return
      timer = schedule(fetchFacts, debounceMs)
    },
    // The one place AI is called: a click.
    async askAi() {
      if (!context || state.ai.loading || state.ai.available === false) return
      const run = ++aiRun
      setAi({ loading: true, error: '', asked: true, unavailable: false })
      try {
        const response = await load({ ...context, ai: true })
        if (run !== aiRun) return
        const items = (response?.suggestions || []).filter((item) => item.kind === 'sentence' || item.kind === 'idea')
        const facts = (response?.suggestions || []).filter((item) => item.kind === 'fact')
        if (facts.length) set({ facts })
        setAi({ ...takeMeta(response), loading: false, items, unavailable: response?.source !== 'ai' && !items.length })
      } catch (error) {
        if (run !== aiRun) return
        const gone = error?.status === 403 // 503 is a provider hiccup: the button stays
        setAi({ loading: false, error: error?.message || 'error', ...(gone ? { available: false } : {}) })
      }
    },
    dispose() {
      disposed = true
      cancel(timer)
    },
  }
}
