import { getLanguage, t } from './i18n'

const DEFAULT_API_URL = 'http://127.0.0.1:8000/api'
const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 15_000

const TOKEN_KEYS = {
  access: 'admitflow-access-token',
  refresh: 'admitflow-refresh-token',
}

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

function getToken(key) {
  return localStorage.getItem(TOKEN_KEYS[key])
}

function saveTokens(tokens) {
  if (tokens.access) localStorage.setItem(TOKEN_KEYS.access, tokens.access)
  if (tokens.refresh) localStorage.setItem(TOKEN_KEYS.refresh, tokens.refresh)
}

async function fetchWithTimeout(url, options = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...fetchOptions } = options
  const controller = new AbortController()
  const callerSignal = fetchOptions.signal
  let timedOut = false
  const abortFromCaller = () => controller.abort()
  if (callerSignal?.aborted) controller.abort()
  else callerSignal?.addEventListener('abort', abortFromCaller, { once: true })
  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  try {
    const headers = new Headers(fetchOptions.headers || {})
    headers.set('Accept-Language', getLanguage())
    return await fetch(url, { ...fetchOptions, headers, signal: controller.signal })
  } catch (error) {
    if (timedOut) throw new ApiError(t('The server is taking too long to respond. Check your connection and retry.'), 408, null)
    if (typeof navigator !== 'undefined' && !navigator.onLine) throw new ApiError(t('You appear to be offline. Reconnect and retry.'), 0, null)
    if (error?.name === 'AbortError') throw error
    throw new ApiError(t('Unable to connect to the server. Check your connection and retry.'), 0, null)
  } finally {
    window.clearTimeout(timeoutId)
    callerSignal?.removeEventListener('abort', abortFromCaller)
  }
}

function responseFileName(response, fallback = 'document') {
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  try { return decodeURIComponent(encoded || plain || fallback) } catch { return plain || fallback }
}

async function protectedFileRequest(path, download = false, retry = true) {
  const headers = new Headers()
  const access = getToken('access')
  if (access) headers.set('Authorization', `Bearer ${access}`)
  const response = await fetchWithTimeout(
    `${API_URL}${path}${download ? '?download=1' : ''}`,
    { headers, timeoutMs: 120_000 },
  )
  if (response.status === 401 && retry && getToken('refresh')) {
    await refreshAccessToken()
    return protectedFileRequest(path, download, false)
  }
  if (!response.ok) {
    const payload = await parseResponse(response)
    throw new ApiError(errorMessage(payload), response.status, payload)
  }
  return {
    blob: await response.blob(),
    contentType: response.headers.get('Content-Type') || 'application/octet-stream',
    fileName: responseFileName(response),
  }
}

const documentFileRequest = (id, download = false) =>
  protectedFileRequest(`/documents/${id}/file/`, download)

const evidenceFileRequest = (resource, id, download = false) =>
  protectedFileRequest(`/${resource}/${id}/proof-file/`, download)

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEYS.access)
  localStorage.removeItem(TOKEN_KEYS.refresh)
}

async function parseResponse(response) {
  const text = await response.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

function errorMessage(payload) {
  if (!payload) return t('Unable to connect to the server.')
  if (typeof payload === 'string') return payload
  if (payload.detail) return payload.detail
  return Object.entries(payload)
    .map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(', ') : value}`)
    .join(' • ')
}

async function refreshAccessToken() {
  const refresh = getToken('refresh')
  if (!refresh) throw new ApiError(t('Your session has expired.'), 401)
  const response = await fetchWithTimeout(`${API_URL}/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  const payload = await parseResponse(response)
  if (!response.ok) {
    clearTokens()
    throw new ApiError(t('Your session has expired. Sign in again.'), response.status, payload)
  }
  saveTokens(payload)
  return payload.access
}

export async function request(path, options = {}, retry = true, unwrapPagination = true) {
  const headers = new Headers(options.headers || {})
  const isFormData = options.body instanceof FormData
  if (!isFormData && options.body !== undefined) headers.set('Content-Type', 'application/json')
  const access = getToken('access')
  if (access) headers.set('Authorization', `Bearer ${access}`)

  const response = await fetchWithTimeout(`${API_URL}${path}`, { ...options, headers })
  if (response.status === 401 && retry && getToken('refresh')) {
    await refreshAccessToken()
    return request(path, options, false, unwrapPagination)
  }
  const payload = await parseResponse(response)
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status, payload)
  return unwrapPagination ? payload?.results ?? payload : payload
}

async function streamRequest(path, payload, signal, retry = true) {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const access = getToken('access')
  if (access) headers.set('Authorization', `Bearer ${access}`)
  const response = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })
  if (response.status === 401 && retry && getToken('refresh')) {
    await refreshAccessToken()
    return streamRequest(path, payload, signal, false)
  }
  if (!response.ok) {
    const errorPayload = await parseResponse(response)
    throw new ApiError(errorMessage(errorPayload), response.status, errorPayload)
  }
  return response
}

function nextApiPath(url) {
  if (!url) return null
  if (url.startsWith(API_URL)) return url.slice(API_URL.length)
  const parsed = new URL(url)
  const apiIndex = parsed.pathname.indexOf('/api/')
  const pathname = apiIndex >= 0 ? parsed.pathname.slice(apiIndex + 4) : parsed.pathname
  return `${pathname.startsWith('/') ? pathname : `/${pathname}`}${parsed.search}`
}

async function listAll(resource, query = '') {
  let path = `/${resource}/${query}`
  const items = []
  let pages = 0
  while (path) {
    const payload = await request(path, {}, true, false)
    if (!payload || !Array.isArray(payload.results)) return payload ?? []
    items.push(...payload.results)
    path = nextApiPath(payload.next)
    pages += 1
    if (pages >= 100) throw new ApiError(t('Too many paginated API results.'), 500, null)
  }
  return items
}

export const api = {
  baseUrl: API_URL,
  hasSession: () => Boolean(getToken('access') || getToken('refresh')),
  login: async (username, password) => {
    const response = await fetchWithTimeout(`${API_URL}/auth/token/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const payload = await parseResponse(response)
    if (!response.ok) throw new ApiError(errorMessage(payload), response.status, payload)
    saveTokens(payload)
    return payload
  },
  logout: clearTokens,
  changePassword: async (newPassword, confirmPassword) => {
    const payload = await request('/users/accounts/change-password/', {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword }),
    })
    saveTokens(payload)
    return payload
  },
  issueTemporaryCredential: (userId, password = '') => request(`/users/accounts/${userId}/temporary-credential/`, {
    method: 'POST',
    body: JSON.stringify(password ? { password } : {}),
  }),
  me: () => request('/users/accounts/me/'),
  health: () => request('/health/'),
  dashboard: () => request('/dashboard/stats/'),
  collegeResearch: () => request('/college-research/'),
  updateCollegeResearchProfile: (payload) => request('/college-research/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  list: listAll,
  create: (resource, payload) => request(`/${resource}/`, {
    method: 'POST',
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
  }),
  update: (resource, id, payload) => request(`/${resource}/${id}/`, {
    method: 'PATCH',
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
  }),
  remove: (resource, id) => request(`/${resource}/${id}/`, { method: 'DELETE' }),
  quickCreateStudent: (payload) => request('/students/quick-create/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  studentAssignmentCandidates: (counselor = null) => request(
    `/students/assignment-candidates/${counselor ? `?counselor=${encodeURIComponent(counselor)}` : ''}`,
  ),
  assignCounselorStudents: (payload) => request('/students/assign-counselor/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  createSchoolAccount: (schoolId, payload) => request(`/schools/${schoolId}/create-account/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  uploadDocument: (payload) => request('/documents/', {
    method: 'POST',
    body: payload,
    timeoutMs: 120_000,
  }),
  documentFile: (id) => documentFileRequest(id),
  downloadDocument: (id) => documentFileRequest(id, true),
  evidenceFile: (resource, id) => evidenceFileRequest(resource, id),
  downloadEvidence: (resource, id) => evidenceFileRequest(resource, id, true),
  createIndividualCounselor: (payload) => request('/users/accounts/create-individual-counselor/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  transferCounselor: (id, school) => request(`/users/accounts/${id}/transfer-school/`, {
    method: 'POST',
    body: JSON.stringify({ school }),
  }),
  createCounselor: (payload) => request('/users/accounts/create-counselor/', { method: 'POST', body: JSON.stringify(payload) }),
  deactivateAccount: (id) => request(`/users/accounts/${id}/deactivate/`, { method: 'POST' }),
  submitCounselorMission: (roadmapId, mission, counselorNote) => request(`/counselor-roadmaps/${roadmapId}/submit-mission/`, { method: 'POST', body: JSON.stringify({ mission, counselor_note: counselorNote }) }),
  reviewCounselorMission: (roadmapId, mission, decision, adminFeedback = '') => request(`/counselor-roadmaps/${roadmapId}/review-mission/`, { method: 'POST', body: JSON.stringify({ mission, decision, admin_feedback: adminFeedback }) }),
  trackScreenTime: (entries) => request('/screen-time/track/', {
    method: 'POST',
    body: JSON.stringify({ entries }),
  }),
  screenTimeSummary: (days = 7) => request(`/screen-time/summary/?days=${encodeURIComponent(days)}`),
  parentPortal: () => request('/parent-portal/'),
  inviteParent: (payload) => request('/parent-links/invite/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  acceptParentInvite: (id) => request(`/parent-links/${id}/accept/`, { method: 'POST' }),
  revokeParentLink: (id) => request(`/parent-links/${id}/revoke/`, { method: 'POST' }),
  approveTask: (id) => request(`/tasks/${id}/approve/`, { method: 'POST' }),
  approveRoadmapMission: (id) => request(`/roadmap-missions/${id}/approve/`, { method: 'POST' }),
  approveStudentLevel: (id) => request(`/students/${id}/approve-level/`, { method: 'POST' }),
  studentXpHistory: (id) => request(`/students/${id}/xp-history/`),
  studentDataVisibility: (id) => request(`/students/${id}/data-visibility/`),
  bookingParticipants: () => request('/bookings/participants/'),
  approveBooking: (id) => request(`/bookings/${id}/approve/`, { method: 'POST' }),
  rejectBooking: (id) => request(`/bookings/${id}/reject/`, { method: 'POST' }),
  completeBooking: (id) => request(`/bookings/${id}/complete/`, { method: 'POST' }),
  messageChannels: (kind = '', search = '') => {
    const query = new URLSearchParams()
    if (kind) query.set('kind', kind)
    if (search) query.set('search', search)
    return request(`/message-channels/${query.size ? `?${query}` : ''}`)
  },
  channelMessages: (channelId) => request(`/channel-messages/?channel=${encodeURIComponent(channelId)}&page_size=50`),
  messageContacts: () => request('/message-channels/contacts/'),
  messagingOverview: () => request('/message-channels/overview/'),
  channelMembers: (id) => request(`/message-channels/${id}/members/`),
  openDirectChannel: (userId) => request('/message-channels/direct/', {
    method: 'POST',
    body: JSON.stringify({ user: userId }),
  }),
  joinChannel: (id) => request(`/message-channels/${id}/join/`, { method: 'POST' }),
  leaveChannel: (id) => request(`/message-channels/${id}/leave/`, { method: 'POST' }),
  markChannelRead: (id) => request(`/message-channels/${id}/mark-read/`, { method: 'POST' }),
  addChannelMember: (id, userId, role = 'member') => request(`/message-channels/${id}/members/`, {
    method: 'POST',
    body: JSON.stringify({ user: userId, role }),
  }),
  removeChannelMember: (id, userId) => request(`/message-channels/${id}/members/`, {
    method: 'DELETE',
    body: JSON.stringify({ user: userId }),
  }),
  acceptChannelMessage: (id) => request(`/channel-messages/${id}/accept/`, { method: 'POST' }),
  reportChannelMessage: (id, payload) => request(`/channel-messages/${id}/report/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  messageReports: (status = 'pending') => request(`/message-reports/${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  reviewMessageReport: (id) => request(`/message-reports/${id}/review/`, { method: 'POST' }),
  dismissMessageReport: (id, payload = {}) => request(`/message-reports/${id}/dismiss/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  resolveMessageReport: (id, payload) => request(`/message-reports/${id}/resolve/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  streamAssistant: (messages, signal) => streamRequest('/assistant/chat/', { messages }, signal),
  markSupportViewed: (id) => request(`/support-tickets/${id}/mark-viewed/`, { method: 'POST' }),
  extendLevelOneRoadmap: (student) => request('/roadmap-missions/extend-level-one/', {
    method: 'POST',
    body: JSON.stringify({ student }),
  }),
  likeCommunityPost: (id) => request(`/community-posts/${id}/like/`, { method: 'POST' }),
  markStudentMessageRead: (id) => request(`/student-messages/${id}/read/`, { method: 'POST' }),
}
