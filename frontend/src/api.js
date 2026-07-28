const DEFAULT_API_URL = 'http://127.0.0.1:8000/api'
const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/$/, '')

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
  if (!payload) return 'Server bilan aloqa xatosi.'
  if (typeof payload === 'string') return payload
  if (payload.detail) return payload.detail
  return Object.entries(payload)
    .map(([field, value]) => `${field}: ${Array.isArray(value) ? value.join(', ') : value}`)
    .join(' • ')
}

async function refreshAccessToken() {
  const refresh = getToken('refresh')
  if (!refresh) throw new ApiError('Sessiya tugagan.', 401)
  const response = await fetch(`${API_URL}/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  const payload = await parseResponse(response)
  if (!response.ok) {
    clearTokens()
    throw new ApiError('Sessiya tugagan. Qayta kiring.', response.status, payload)
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

  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (response.status === 401 && retry && getToken('refresh')) {
    await refreshAccessToken()
    return request(path, options, false, unwrapPagination)
  }
  const payload = await parseResponse(response)
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status, payload)
  return unwrapPagination ? payload?.results ?? payload : payload
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
    if (pages >= 100) throw new ApiError('Too many paginated API results.', 500, null)
  }
  return items
}

export const api = {
  baseUrl: API_URL,
  hasSession: () => Boolean(getToken('access') || getToken('refresh')),
  login: async (username, password) => {
    const response = await fetch(`${API_URL}/auth/token/`, {
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
  createSchoolAccount: (schoolId, payload) => request(`/schools/${schoolId}/create-account/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  approveTask: (id) => request(`/tasks/${id}/approve/`, { method: 'POST' }),
  approveRoadmapMission: (id) => request(`/roadmap-missions/${id}/approve/`, { method: 'POST' }),
  approveStudentLevel: (id) => request(`/students/${id}/approve-level/`, { method: 'POST' }),
  studentXpHistory: (id) => request(`/students/${id}/xp-history/`),
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
  markNotificationRead: (id) => request(`/notifications/${id}/read/`, { method: 'POST' }),
  extendLevelOneRoadmap: (student) => request('/roadmap-missions/extend-level-one/', {
    method: 'POST',
    body: JSON.stringify({ student }),
  }),
  likeCommunityPost: (id) => request(`/community-posts/${id}/like/`, { method: 'POST' }),
  markStudentMessageRead: (id) => request(`/student-messages/${id}/read/`, { method: 'POST' }),
}
