import { getLanguage, t } from './i18n'
import {
  AUTH_CHANNEL, AUTH_LOCK, browserLock, createCookieAuth, createRefresher, createSessionStore, isSignOutSignal,
  migrateLegacyTokens,
} from './authTokens'
import { readPayload } from './lib/payload.js'
import { UNTRACKED_ENDPOINTS, createMutationTracker } from './lib/reloadPlan'
import { errorPayloadMessage } from './lib/apiErrors'
import { firstListPath } from './lib/listPath.js'
import { requestRetryDelay } from './lib/backoff.js'
import { protectedFileUrl, readProtectedFile } from './lib/protectedFile.js'
import { sendWithProgress } from './lib/fileUpload.js'
import { hasUserDrafts, removeUserDrafts } from './essayLab/drafts.js'

// Same origin by default: the Vite dev server, the nginx image (API_UPSTREAM)
// and Vercel (NASEEB_API_ORIGIN, middleware.js) proxy /api to Django, so the
// refresh cookie is first-party. An absolute URL is the cross-site setup
// (AUTH_REFRESH_COOKIE_SAMESITE=None on the backend); see docs/deployment-auth.md.
const DEFAULT_API_URL = '/api'
const API_URL = (import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/$/, '')
const REQUEST_TIMEOUT_MS = 15_000

const session = createSessionStore(() => window.localStorage)
// Successful writes are recorded so the app can reload only what changed.
const mutations = createMutationTracker(UNTRACKED_ENDPOINTS)

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

const getToken = (key) => session.get(key)
// Every token pair outside a refresh comes from a new sign-in (a new server session).
const saveTokens = (payload) => session.save(payload, { signIn: true })
const hasSession = () => session.hasSession()

// Fresh access tokens from other tabs (see createRefresher in authTokens.js).
const authChannel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(AUTH_CHANNEL)
authChannel?.addEventListener('message', (event) => {
  if (event.data?.type === 'access') session.adopt(event.data.access)
})

// The in-memory access token, or a fresh one from the refresh cookie after a
// reload (null when signed out).
async function accessToken() {
  return getToken('access') || (hasSession() ? refreshAccessToken() : null)
}

async function fetchWithTimeout(url, options = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, localize = true, ...fetchOptions } = options
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
    if (localize) headers.set('Accept-Language', getLanguage())
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

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { window.clearTimeout(id); reject(new DOMException('Aborted', 'AbortError')) }
    const id = window.setTimeout(() => { signal?.removeEventListener('abort', abort); resolve() }, ms)
    signal?.addEventListener('abort', abort, { once: true })
  })
}

// GETs are retried on transient failures with jittered backoff (lib/backoff.js);
// writes never are, since a write that timed out may still have landed.
async function fetchWithRetry(url, options) {
  const { retries, ...fetchOptions } = options
  const method = (fetchOptions.method || 'GET').toUpperCase()
  const limit = method === 'GET' ? retries : 0
  for (let attempt = 0; ; attempt += 1) {
    let response
    try {
      response = await fetchWithTimeout(url, fetchOptions)
    } catch (error) {
      const offline = typeof navigator !== 'undefined' && navigator.onLine === false
      const delay = error instanceof ApiError && !offline ? requestRetryDelay(attempt, error.status, null, { retries: limit }) : null
      if (delay == null) throw error
      await sleep(delay, fetchOptions.signal)
      continue
    }
    const delay = requestRetryDelay(attempt, response.status, response.headers.get('Retry-After'), { retries: limit })
    if (delay == null) return response
    await sleep(delay, fetchOptions.signal)
  }
}

// A presigned bucket URL: no API headers, no cookies, no referrer.
const fetchStoredFile = (url) => fetchWithTimeout(url, {
  timeoutMs: 120_000,
  localize: false,
  credentials: 'omit',
  cache: 'no-store',
  referrerPolicy: 'no-referrer',
})

async function protectedFileRequest(path, { download = false, query } = {}, retry = true) {
  const headers = new Headers()
  const access = await accessToken()
  if (access) headers.set('Authorization', `Bearer ${access}`)
  const response = await fetchWithTimeout(protectedFileUrl(API_URL, path, download, query), { headers, timeoutMs: 120_000 })
  if (response.status === 401 && retry && hasSession()) {
    await refreshAccessToken(access)
    return protectedFileRequest(path, { download, query }, false)
  }
  if (!response.ok) {
    const payload = await parseResponse(response)
    throw new ApiError(errorMessage(payload), response.status, payload)
  }
  return readProtectedFile(response, {
    fetchFile: fetchStoredFile,
    fileError: (status) => new ApiError(t('The file could not be downloaded. Retry.'), status, null),
  })
}

const documentFileRequest = (id, download = false) =>
  protectedFileRequest(`/documents/${id}/file/`, { download })

const evidenceFileRequest = (resource, id, download = false) =>
  protectedFileRequest(`/${resource}/${id}/proof-file/`, { download })

const taskSubmissionFileRequest = (id, download = false) =>
  protectedFileRequest(`/tasks/${id}/submission-file/`, { download })

// Chat attachments are served only to members of the conversation.
const messageAttachmentRequest = (id, download = false) =>
  protectedFileRequest(`/channel-messages/${id}/attachment/`, { download })

const recommendationFileRequest = (id, download = false) =>
  protectedFileRequest(`/recommendations/${id}/file/`, { download })

// Profile photos live in private storage, so they are fetched as blobs like
// every other personal file rather than pointed at with a media URL. With the
// photo's version the response is cacheable for a day.
const studentPhotoRequest = (id, version) =>
  protectedFileRequest(`/students/${id}/photo/`, { query: version ? { v: version } : {} })

// Essay Lab keeps unsynced text in local drafts under
// `naseeb-essay-draft:<userId>:<essayId>`. Before signing out, every open
// editor gets a real save attempt (up to SIGN_OUT_SYNC_MS). Only when all text
// reached the server — or the student chose to delete it — are the signing-out
// user's drafts removed; other accounts' drafts on this device are untouched.
// An expired session keeps them: the same student gets the text back after
// signing in again.
const SIGN_OUT_SYNC_MS = 4000
const beforeSignOut = new Set()

// entry: { save: () => Promise<boolean> (true = all text on the server), forget: () => void }
export function registerBeforeLogout(entry) {
  beforeSignOut.add(entry)
  return () => beforeSignOut.delete(entry)
}

// -> true when every open editor has synced and the user has no drafts left,
// false when some text would only survive in this device's drafts (offline,
// session expired, timed out, or left in an essay that is no longer open).
export async function syncBeforeSignOut(userId, timeoutMs = SIGN_OUT_SYNC_MS) {
  const synced = await saveOpenEditors(timeoutMs)
  if (!synced) return false
  try { return userId == null || !hasUserDrafts(window.localStorage, userId) } catch { return true }
}

async function saveOpenEditors(timeoutMs) {
  const entries = [...beforeSignOut]
  if (!entries.length) return true
  const attempts = entries.map((entry) => Promise.resolve().then(() => entry.save()).then((ok) => ok !== false, () => false))
  let timer
  const timeout = new Promise((resolve) => { timer = window.setTimeout(() => resolve(false), timeoutMs) })
  try {
    return await Promise.race([Promise.all(attempts).then((results) => results.every(Boolean)), timeout])
  } finally {
    window.clearTimeout(timer)
  }
}

const SESSION_ENDED_EVENT = 'naseeb:session-ended'

// Fires when this tab is left without a session: a request came back 401 with
// no session to refresh, the refresh cookie was rejected, or another tab signed
// out (it removes the shared, non-secret session flag).
// Without it, parts that fetch on their own (screen time, chat polling) keep
// running on a dead session and show the raw 401.
// The callback gets { fromOtherTab: true } when another tab signed out: that
// tab already ended the server session.
function onSessionEnded(callback) {
  const onStorage = (event) => {
    if (isSignOutSignal(event)) callback({ fromOtherTab: true })
  }
  window.addEventListener(SESSION_ENDED_EVENT, callback)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(SESSION_ENDED_EVENT, callback)
    window.removeEventListener('storage', onStorage)
  }
}

const authLock = browserLock(AUTH_LOCK)

// The refresh and logout calls, authenticated by the HttpOnly cookie.
const cookieAuth = createCookieAuth({
  apiUrl: API_URL,
  request: fetchWithTimeout,
  store: session,
  lock: authLock,
  settleRefreshes: () => refreshAccessToken.settled(),
})

// The previous frontend kept tokens in localStorage: revoke them, then drop them.
migrateLegacyTokens(() => window.localStorage, (token) => cookieAuth.revokeLegacy(token))

// The session ended on its own (expired, revoked, another tab signed out):
// end it here and, unless another tab already did, on the server too.
function logout({ server = true } = {}) {
  // The user's own sign-out is in progress: it decides when the counter goes.
  if (userSignOut) return userSignOut
  const signInId = session.endHere()
  if (!server) {
    session.clear(signInId)
    return Promise.resolve(true)
  }
  return cookieAuth.logout(signInId).then((ok) => {
    session.clear(signInId)
    return ok
  })
}

// The user signs out. Resolves true once the server ended the session; only
// then is the session counter removed (signing the other tabs out). On false
// (server unreachable after one retry) this tab is signed out locally but the
// cookie may still work: the caller offers retrySignOut() or forgetSession().
let userSignOut = null
let pendingSignInId
function endUserSession() {
  pendingSignInId = session.endHere()
  return retrySignOut()
}

function retrySignOut() {
  userSignOut = cookieAuth.logout(pendingSignInId).then((ok) => {
    if (ok) {
      session.clear(pendingSignInId)
      userSignOut = null
    }
    return ok
  })
  return userSignOut
}

// Gives up on the server: the session ends on this device only.
function forgetSession() {
  session.clear(pendingSignInId)
  userSignOut = null
}

// keepDrafts: "Sign in again" — end the session but leave this user's
// unsynced drafts on the device for the next sign-in.
function signOut(userId, { keepDrafts = false } = {}) {
  if (!keepDrafts) {
    for (const entry of [...beforeSignOut]) {
      try { entry.forget() } catch { /* best effort */ }
    }
  }
  const ended = endUserSession()
  if (!keepDrafts && userId != null) {
    try { removeUserDrafts(window.localStorage, userId) } catch { /* storage unavailable */ }
  }
  return ended
}

const parseResponse = readPayload

function errorMessage(payload) {
  if (!payload) return t('Unable to connect to the server.')
  if (typeof payload === 'string') {
    const isHtmlErrorPage = /<!doctype html>|<html[\s>]|<title>server error/i.test(payload)
    return isHtmlErrorPage ? t('The server could not complete this request. Please retry.') : payload
  }
  return errorPayloadMessage(payload, t) || t('The server could not complete this request. Please retry.')
}

// One shared refresh for every caller: parallel 401s must not each spend the
// (rotating, blacklisted-after-use) refresh token and then wipe the new pair.
const refreshAccessToken = createRefresher({
  store: {
    ...session,
    clear() {
      session.clear()
      window.dispatchEvent(new Event(SESSION_ENDED_EVENT))
    },
  },
  lock: authLock,
  jitterMs: 300,
  send: () => cookieAuth.refresh(),
  share: (access) => authChannel?.postMessage({ type: 'access', access }),
  warn: (message, payload) => console.warn(message, payload),
  expired: (status, payload) => new ApiError(t('Your session has expired. Sign in again.'), status, payload),
  failed: (status, payload) => new ApiError(errorMessage(payload), status, payload),
})

// `retries`: automatic retries for a GET on transient failures (0 turns them off).
// `etag` (a string, or null for none yet): revalidate; resolves to
// { notModified: true } on 304, else { notModified: false, etag, data }.
export async function request(path, options = {}, retry = true, unwrapPagination = true) {
  const { auth = true, retries = 2, etag, ...fetchOptions } = options
  const headers = new Headers(fetchOptions.headers || {})
  if (etag) headers.set('If-None-Match', etag)
  const isFormData = fetchOptions.body instanceof FormData
  if (!isFormData && fetchOptions.body !== undefined) headers.set('Content-Type', 'application/json')
  const access = auth ? await accessToken() : null
  if (access) headers.set('Authorization', `Bearer ${access}`)

  const response = await fetchWithRetry(`${API_URL}${path}`, { ...fetchOptions, headers, retries })
  if (auth && response.status === 401 && retry && hasSession()) {
    await refreshAccessToken(access)
    return request(path, options, false, unwrapPagination)
  }
  if (auth && response.status === 401 && !hasSession()) window.dispatchEvent(new Event(SESSION_ENDED_EVENT))
  if (etag !== undefined && response.status === 304) return { notModified: true }
  const payload = await parseResponse(response)
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status, payload)
  if (fetchOptions.method && fetchOptions.method !== 'GET') mutations.note(path)
  const data = unwrapPagination ? payload?.results ?? payload : payload
  return etag !== undefined ? { notModified: false, etag: response.headers.get('ETag'), data } : data
}

const UPLOAD_TIMEOUT_MS = 10 * 60_000

// A multipart write that reports upload progress (0-100) through onProgress.
// Like request(): one token refresh on 401, API errors as ApiError; an
// aborted upload rejects with an AbortError.
async function uploadRequest(method, path, body, { onProgress, signal } = {}, retry = true) {
  const headers = { 'Accept-Language': getLanguage() }
  const access = await accessToken()
  if (access) headers.Authorization = `Bearer ${access}`
  let response
  try {
    response = await sendWithProgress({
      createRequest: () => new XMLHttpRequest(),
      method,
      url: `${API_URL}${path}`,
      headers,
      body,
      onProgress,
      signal,
      timeoutMs: UPLOAD_TIMEOUT_MS,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    if (error.name === 'TimeoutError') throw new ApiError(t('The server is taking too long to respond. Check your connection and retry.'), 408, null)
    if (typeof navigator !== 'undefined' && !navigator.onLine) throw new ApiError(t('You appear to be offline. Reconnect and retry.'), 0, null)
    throw new ApiError(t('Unable to connect to the server. Check your connection and retry.'), 0, null)
  }
  if (response.status === 401 && retry && hasSession()) {
    await refreshAccessToken(access)
    onProgress?.(0)
    return uploadRequest(method, path, body, { onProgress, signal }, false)
  }
  let payload = null
  if (response.text) {
    try { payload = JSON.parse(response.text) } catch { payload = response.text }
  }
  if (response.status < 200 || response.status >= 300) throw new ApiError(errorMessage(payload), response.status, payload)
  mutations.note(path)
  return payload
}

async function streamRequest(path, payload, signal, retry = true) {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const access = await accessToken()
  if (access) headers.set('Authorization', `Bearer ${access}`)
  const response = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })
  if (response.status === 401 && retry && hasSession()) {
    await refreshAccessToken(access)
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

// Loads a whole (bounded) collection page by page. `onPage(itemsSoFar)` runs
// after every page so callers can render the first page while the rest
// arrives; only the workspace's own small collections use this — large staff
// lists are server-paged (hooks/usePagedList).
async function listAll(resource, query = '', { onPage } = {}) {
  let path = firstListPath(resource, query)
  const items = []
  const visited = new Set()
  while (path && !visited.has(path)) {
    visited.add(path)
    const payload = await request(path, {}, true, false)
    if (!payload || !Array.isArray(payload.results)) return payload ?? []
    items.push(...payload.results)
    path = nextApiPath(payload.next)
    if (path) onPage?.([...items])
  }
  return items
}

// One page of the keyset-cursor list contract: { results, next, has_more }.
const listPage = (resource, query, signal) => request(`/${resource}/${query}`, { signal }, true, false)

export const api = {
  baseUrl: API_URL,
  takeMutations: () => mutations.take(),
  hasSession,
  // After any sign-out (this tab or another) has finished, so its response
  // cannot delete the cookie this sign-in sets.
  login: (username, password) => cookieAuth.signIn(async () => {
    // credentials: the response sets the refresh cookie (cross-origin API too).
    const response = await fetchWithTimeout(`${API_URL}/auth/token/`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const payload = await parseResponse(response)
    if (!response.ok) throw new ApiError(errorMessage(payload), response.status, payload)
    saveTokens(payload)
    return payload
  }),
  logout,
  onSessionEnded,
  signOut,
  retrySignOut,
  forgetSession,
  syncBeforeSignOut,
  changePassword: async (newPassword, confirmPassword) => {
    const payload = await request('/users/accounts/change-password/', {
      method: 'POST',
      credentials: 'include',
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
  // Account settings. A password change ends the other sessions and hands this
  // one a new access token (kept here) and refresh cookie, so it stays signed in.
  changeOwnPassword: async (currentPassword, newPassword, confirmPassword) => {
    const payload = await request('/users/accounts/me/password/', {
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
    })
    saveTokens(payload)
    return payload
  },
  changeOwnEmail: (currentPassword, email) => request('/users/accounts/me/email/', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, email }),
  }),
  dashboardLayout: () => request('/users/accounts/me/dashboard-layout/'),
  saveDashboardLayout: (layout) => request('/users/accounts/me/dashboard-layout/', {
    method: 'PUT',
    body: JSON.stringify({ layout }),
  }),
  myParents: () => request('/my-parents/'),
  health: () => request('/health/'),
  dashboard: () => request('/dashboard/stats/'),
  collegeResearch: () => request('/college-research/'),
  // One College Search page (filters, sort and page size in `query`); never the whole catalogue.
  collegeSearch: (query, signal) => request(`/college-search/?${query}`, { signal }, true, false),
  updateCollegeResearchProfile: (payload) => request('/college-research/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  educationMatchAI: (payload) => request('/education-matches/ai/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  list: listAll,
  page: listPage,
  count: async (resource, query = '') => {
    const params = new URLSearchParams(query.replace(/^\?/, ''))
    params.set('page_size', '1')
    return (await request(`/${resource}/?${params}`, {}, true, false))?.count ?? 0
  },
  search: (query, signal, types = '') => request(`/search/?q=${encodeURIComponent(query)}${types ? `&types=${encodeURIComponent(types)}` : ''}`, { signal }, true, false),
  retrieve: (resource, id) => request(`/${resource}/${encodeURIComponent(id)}/`),
  create: (resource, payload) => request(`/${resource}/`, {
    method: 'POST',
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
  }),
  update: (resource, id, payload) => request(`/${resource}/${id}/`, {
    method: 'PATCH',
    body: payload instanceof FormData ? payload : JSON.stringify(payload),
  }),
  remove: (resource, id) => request(`/${resource}/${id}/`, { method: 'DELETE' }),
  studentOnboarding: () => request('/students/onboarding/'),
  saveStudentOnboarding: (payload) => request('/students/onboarding/', { method: 'POST', body: JSON.stringify(payload) }),
  // Some answers only (one Student Center section); the rest stay as saved.
  updateStudentAnswers: (payload) => request('/students/onboarding/', { method: 'PATCH', body: JSON.stringify(payload) }),
  // The résumé fields only (backend/apps/admissions/cv.py); never cached.
  myCv: () => request('/students/me/cv/'),
  studentCv: (id) => request(`/students/${id}/cv/`),
  quickCreateStudent: (payload) => request('/students/quick-create/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  studentAssignmentCandidates: (counselor = null, search = '', signal) => {
    const query = new URLSearchParams()
    if (counselor) query.set('counselor', counselor)
    if (search.trim()) query.set('search', search.trim())
    return request(`/students/assignment-candidates/${query.size ? `?${query}` : ''}`, { signal })
  },
  assignCounselorStudents: (payload) => request('/students/assign-counselor/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  createSchoolAccount: (schoolId, payload) => request(`/schools/${schoolId}/create-account/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  // Create (id null) or update a record from FormData with upload progress.
  saveWithFiles: (resource, id, payload, options) => (id
    ? uploadRequest('PATCH', `/${resource}/${id}/`, payload, options)
    : uploadRequest('POST', `/${resource}/`, payload, options)),
  studentPhoto: (id, version) => studentPhotoRequest(id, version),
  uploadStudentPhoto: (id, file) => {
    const payload = new FormData()
    payload.append('photo', file)
    return request(`/students/${id}/photo/`, { method: 'POST', body: payload, timeoutMs: 120_000 })
  },
  removeStudentPhoto: (id) => request(`/students/${id}/photo/`, { method: 'DELETE' }),
  // A staff account's own photo (User.avatar); each write returns the updated account.
  accountAvatar: (id, version) => protectedFileRequest(`/users/accounts/${id}/avatar/`, { query: version ? { v: version } : {} }),
  uploadAccountAvatar: (id, file) => {
    const payload = new FormData()
    payload.append('avatar', file)
    return request(`/users/accounts/${id}/`, { method: 'PATCH', body: payload, timeoutMs: 120_000 })
  },
  removeAccountAvatar: (id) => request(`/users/accounts/${id}/`, { method: 'PATCH', body: JSON.stringify({ avatar: null }) }),
  messageAttachment: (id) => messageAttachmentRequest(id),
  downloadMessageAttachment: (id) => messageAttachmentRequest(id, true),
  documentFile: (id) => documentFileRequest(id),
  downloadDocument: (id) => documentFileRequest(id, true),
  evidenceFile: (resource, id) => evidenceFileRequest(resource, id),
  downloadEvidence: (resource, id) => evidenceFileRequest(resource, id, true),
  taskSubmissionFile: (id) => taskSubmissionFileRequest(id),
  downloadTaskSubmission: (id) => taskSubmissionFileRequest(id, true),
  recommendationFile: (id) => recommendationFileRequest(id),
  downloadRecommendationFile: (id) => recommendationFileRequest(id, true),
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
  plans: () => request('/users/plans/'),
  updateSubscription: (schoolId, payload) => request(`/users/workspace-subscriptions/${schoolId}/`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  }),
  supportView: (id, reason) => request(`/users/accounts/${id}/support-view/`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  }),
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
  // Profile Assessment. Attempts are append-only: a retake is a new row, so
  // there is deliberately no update or delete here.
  challengeAttempts: (studentId) => listAll('challenge-attempts', studentId ? `?student=${encodeURIComponent(studentId)}` : ''),
  saveChallengeAttempt: (payload) => request('/challenge-attempts/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  approveTask: (id, note = '') => request(`/tasks/${id}/approve/`, { method: 'POST', body: JSON.stringify({ note }) }),
  approveRoadmapMission: (id, note = '') => request(`/roadmap-missions/${id}/approve/`, { method: 'POST', body: JSON.stringify({ note }) }),
  // Documents and achievements: accept them, optionally with a note for the student.
  approveRecord: (endpoint, id, note = '') => request(`/${endpoint}/${id}/approve/`, { method: 'POST', body: JSON.stringify({ note }) }),
  // A counselor returns submitted work (tasks, roadmap-missions, documents, achievements) with a note.
  sendBack: (endpoint, id, note) => request(`/${endpoint}/${id}/send-back/`, { method: 'POST', body: JSON.stringify({ note }) }),
  approveStudentLevel: (id) => request(`/students/${id}/approve-level/`, { method: 'POST' }),
  // A counselor's nudge about one open item (topic: task | mission | document | profile).
  remindStudent: (id, payload) => request(`/students/${id}/remind/`, { method: 'POST', body: JSON.stringify(payload) }),
  studentXpHistory: (id) => request(`/students/${id}/xp-history/`),
  studentDataVisibility: (id) => request(`/students/${id}/data-visibility/`),
  bookingParticipants: () => request('/bookings/participants/'),
  bookingAvailability: (participant) => request(`/bookings/availability/${participant ? `?participant=${participant}` : ''}`),
  addBookingAvailability: (payload) => request('/bookings/availability/', { method: 'POST', body: JSON.stringify(payload) }),
  removeBookingAvailability: (id) => request('/bookings/availability/', { method: 'DELETE', body: JSON.stringify({ id }) }),
  approveBooking: (id) => request(`/bookings/${id}/approve/`, { method: 'POST' }),
  rejectBooking: (id) => request(`/bookings/${id}/reject/`, { method: 'POST' }),
  completeBooking: (id) => request(`/bookings/${id}/complete/`, { method: 'POST' }),
  cancelBooking: (id) => request(`/bookings/${id}/cancel/`, { method: 'POST' }),
  rescheduleBooking: (id, payload) => request(`/bookings/${id}/reschedule/`, { method: 'POST', body: JSON.stringify(payload) }),
  telegramFeed: (before) => request(`/telegram-feed/${before ? `?before=${encodeURIComponent(before)}` : ''}`, {}, true, false),
  messageChannels: (kind = '', search = '') => {
    const query = new URLSearchParams()
    if (kind) query.set('kind', kind)
    if (search) query.set('search', search)
    return request(`/message-channels/${query.size ? `?${query}` : ''}`)
  },
  channelMessages: (channelId) => request(`/channel-messages/?channel=${encodeURIComponent(channelId)}&page_size=50`),
  // Polling: pass the ETag of the last load; { notModified: true } when nothing changed.
  // Resolves to { notModified } or { etag, data: { results, next } }.
  channelMessagesSince: (channelId, etag) => request(`/channel-messages/?channel=${encodeURIComponent(channelId)}&page_size=50`, { etag: etag || null }, true, false),
  // The page before message `beforeId`: { results (newest first), next }.
  channelMessagesBefore: (channelId, beforeId) => request(`/channel-messages/?channel=${encodeURIComponent(channelId)}&page_size=50&before=${encodeURIComponent(beforeId)}`, {}, true, false),
  messageContacts: () => request('/message-channels/contacts/'),
  messagingOverview: () => request('/message-channels/overview/'),
  channelMembers: (id) => request(`/message-channels/${id}/members/`),
  savedMessages: () => request('/message-channels/saved/', { method: 'POST' }),
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
  markStudentMessageRead: (id) => request(`/student-messages/${id}/read/`, { method: 'POST' }),
  notificationSummary: () => request('/notifications/summary/'),
  markNotificationRead: (id) => request(`/notifications/${id}/read/`, { method: 'POST' }),
  markAllNotificationsRead: () => request('/notifications/read-all/', { method: 'POST' }),
}
