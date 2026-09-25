// Essay Lab API. Everything goes through the app's `request`
// helper, so JWT refresh, timeouts and error shapes match the rest of Naseeb.
// Errors are ApiError: { status, details: { detail, code, ... } }.
import { request } from '../api.js'

const BASE = '/essay-lab'
const json = (method, body, extra = {}) => ({ method, body: JSON.stringify(body ?? {}), ...extra })

function query(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export const essayLabApi = {
  // folder: id | 'none'; type: essay_type; q: search text; trashed: 0 | 1
  listEssays: (params = {}) => request(`${BASE}/essays/${query(params)}`),
  createEssay: (payload) => request(`${BASE}/essays/`, json('POST', payload)),
  // The document with every tab's metadata and one tab's doc (`tab`: which one).
  getEssay: (id, tab) => request(`${BASE}/essays/${id}/${query({ tab })}`),
  updateEssay: (id, payload) => request(`${BASE}/essays/${id}/`, json('PATCH', payload)),
  // payload carries `tab`: every tab saves on its own save_seq.
  autosave: (id, payload, { keepalive = false } = {}) => request(
    `${BASE}/essays/${id}/autosave/`,
    json('PUT', payload, keepalive ? { keepalive: true } : {}),
  ),

  // Tabs: create/duplicate answer { tab, tabs }, delete/order { tabs }.
  getTab: (id, tabId) => request(`${BASE}/essays/${id}/tabs/${tabId}/`),
  createTab: (id, payload) => request(`${BASE}/essays/${id}/tabs/`, json('POST', payload)),
  renameTab: (id, tabId, title) => request(`${BASE}/essays/${id}/tabs/${tabId}/`, json('PATCH', { title })),
  deleteTab: (id, tabId) => request(`${BASE}/essays/${id}/tabs/${tabId}/`, { method: 'DELETE' }),
  duplicateTab: (id, tabId) => request(`${BASE}/essays/${id}/tabs/${tabId}/duplicate/`, { method: 'POST' }),
  orderTabs: (id, parent, ids) => request(`${BASE}/essays/${id}/tabs/order/`, json('PUT', { parent: parent ?? null, ids })),
  trashEssay: (id) => request(`${BASE}/essays/${id}/trash/`, { method: 'POST' }),
  restoreEssay: (id) => request(`${BASE}/essays/${id}/restore/`, { method: 'POST' }),
  deleteEssay: (id) => request(`${BASE}/essays/${id}/`, { method: 'DELETE' }),
  duplicateEssay: (id, payload = {}) => request(`${BASE}/essays/${id}/duplicate/`, json('POST', payload)),
  // Idempotent; the answer is the essay summary with its new sharing state.
  shareEssay: (id) => request(`${BASE}/essays/${id}/share/`, { method: 'POST' }),
  unshareEssay: (id) => request(`${BASE}/essays/${id}/unshare/`, { method: 'POST' }),

  checkpoints: (id, tab) => request(`${BASE}/essays/${id}/checkpoints/${query({ tab })}`),
  checkpoint: (id, checkpointId) => request(`${BASE}/essays/${id}/checkpoints/${checkpointId}/`),
  createCheckpoint: (id, tab, label = '') => request(`${BASE}/essays/${id}/checkpoints/`, json('POST', label ? { tab, label } : { tab })),
  restoreCheckpoint: (id, checkpointId, baseSeq) => request(
    `${BASE}/essays/${id}/checkpoints/${checkpointId}/restore/`,
    json('POST', { base_seq: baseSeq }),
  ),

  depthCheck: (id, tab, baseSeq) => request(`${BASE}/essays/${id}/depth-check/`, json('POST', { tab, base_seq: baseSeq }, { timeoutMs: 60_000 })),
  // Without a tab: the document's latest check (the library card).
  latestDepthCheck: (id, tab) => request(`${BASE}/essays/${id}/depth-check/latest/${query({ tab })}`),

  folders: () => request(`${BASE}/folders/`),
  createFolder: (payload) => request(`${BASE}/folders/`, json('POST', payload)),
  updateFolder: (id, payload) => request(`${BASE}/folders/${id}/`, json('PATCH', payload)),
  deleteFolder: (id) => request(`${BASE}/folders/${id}/`, { method: 'DELETE' }),
  orderFolders: (parent, ids) => request(`${BASE}/folders/order/`, json('PUT', { parent: parent ?? null, ids })),
}

export function errorCode(error) {
  return error?.details?.code || null
}

export const ESSAY_TYPES = [
  { id: 'personal_statement', name: 'Personal statement', hint: 'Common App or your own prompt' },
  { id: 'supplement', name: 'Supplement', hint: '“Why us?”, activity, community…' },
  { id: 'scholarship', name: 'Scholarship', hint: 'Any scholarship question' },
  { id: 'free_writing', name: 'Free writing', hint: 'Just write, no question' },
]

export const essayTypeName = (id) => ESSAY_TYPES.find((type) => type.id === id)?.name || 'Essay'
