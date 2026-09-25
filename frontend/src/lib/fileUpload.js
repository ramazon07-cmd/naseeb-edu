// Client-side rules for private student files. They mirror the backend
// (DOCUMENT_ALLOWED_EXTENSIONS / DOCUMENT_MAX_UPLOAD_SIZE in core/settings.py,
// checked by tests/fileUpload.test.mjs) so a wrong file is refused before any
// bytes are sent; the server still validates type, content and size.
export const UPLOAD_EXTENSIONS = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.webp', '.heic']
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024

// Extensions and media types together: phones use the media types to offer
// the camera and photo library next to the file browser.
export const UPLOAD_ACCEPT = [
  ...UPLOAD_EXTENSIONS,
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/heic',
].join(',')

// Types the browser can show inside the sandboxed preview.
const PREVIEWABLE_EXTENSIONS = new Set(['.pdf', '.jpg', '.jpeg', '.png', '.webp'])

export function fileExtension(name = '') {
  const match = /\.[^./\\]+$/.exec(String(name).trim())
  return match ? match[0].toLowerCase() : ''
}

// 'pdf' | 'word' | 'image' | 'file' — picks the icon and the preview note.
export function fileKind(name = '', contentType = '') {
  const extension = fileExtension(name)
  const type = String(contentType).split(';')[0].trim().toLowerCase()
  if (extension === '.pdf' || type === 'application/pdf') return 'pdf'
  if (['.doc', '.docx'].includes(extension) || type === 'application/msword' || type.includes('wordprocessingml')) return 'word'
  if (['.jpg', '.jpeg', '.png', '.webp', '.heic'].includes(extension) || type.startsWith('image/')) return 'image'
  return 'file'
}

export function canPreviewInBrowser(name = '') {
  return PREVIEWABLE_EXTENSIONS.has(fileExtension(name))
}

// -> null when the file may be sent, else { code: 'empty' | 'type' | 'size' }.
export function uploadProblem(file, { maxBytes = MAX_UPLOAD_BYTES, extensions = UPLOAD_EXTENSIONS } = {}) {
  if (!file) return null
  if (!extensions.includes(fileExtension(file.name))) return { code: 'type' }
  if (!file.size) return { code: 'empty' }
  if (file.size > maxBytes) return { code: 'size' }
  return null
}

// "transcript final.pdf" -> "transcript final": a title suggestion.
export function titleFromFileName(name = '') {
  const base = String(name).split(/[/\\]/).pop() || ''
  const extension = fileExtension(base)
  return (extension ? base.slice(0, -extension.length) : base).replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim()
}

export function uploadPercent(loaded, total) {
  if (!total || total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((loaded / total) * 100)))
}

// FormData for a multipart PATCH/POST: null means "clear" ('' is read as null
// by the API for nullable fields), booleans as true/false.
export function toFormData(values) {
  const payload = new FormData()
  for (const [name, value] of Object.entries(values)) {
    if (value === undefined) continue
    if (value === null) payload.append(name, '')
    else if (typeof Blob !== 'undefined' && value instanceof Blob) payload.append(name, value, value.name || 'file')
    else payload.append(name, String(value))
  }
  return payload
}

// Sends a body with XMLHttpRequest, the one browser API that reports upload
// progress. Resolves { status, text, contentType } for any HTTP answer and
// rejects only on network failure, timeout or abort (error.name says which).
export function sendWithProgress({ createRequest, method, url, headers = {}, body, onProgress, signal, timeoutMs = 0 }) {
  return new Promise((resolve, reject) => {
    const xhr = createRequest()
    const fail = (name) => {
      signal?.removeEventListener('abort', abort)
      const error = new Error(name)
      error.name = name
      reject(error)
    }
    const abort = () => xhr.abort()
    if (signal?.aborted) {
      fail('AbortError')
      return
    }
    xhr.open(method, url)
    for (const [name, value] of Object.entries(headers)) xhr.setRequestHeader(name, value)
    if (timeoutMs) xhr.timeout = timeoutMs
    xhr.upload?.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress?.(uploadPercent(event.loaded, event.total))
    })
    xhr.addEventListener('load', () => {
      signal?.removeEventListener('abort', abort)
      resolve({ status: xhr.status, text: xhr.responseText || '', contentType: xhr.getResponseHeader('Content-Type') || '' })
    })
    xhr.addEventListener('error', () => fail('NetworkError'))
    xhr.addEventListener('timeout', () => fail('TimeoutError'))
    xhr.addEventListener('abort', () => fail('AbortError'))
    signal?.addEventListener('abort', abort, { once: true })
    xhr.send(body)
  })
}
