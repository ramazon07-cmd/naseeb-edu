// Private files are authorised by the API and then delivered either directly
// (local disk: the response is the file) or through a short-lived presigned
// object-storage URL. `?mode=url` asks for that URL as JSON instead of a 302,
// so the browser never replays the Authorization header against the bucket and
// the bucket only has to allow a plain CORS GET.
export const FILE_LINK_CONTENT_TYPE = 'application/vnd.naseeb.file-link+json'

export function protectedFileUrl(apiUrl, path, download = false, query = {}) {
  const params = new URLSearchParams({ mode: 'url', ...query })
  if (download) params.set('download', '1')
  return `${apiUrl}${path}?${params}`
}

export function responseFileName(response, fallback = 'document') {
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  try { return decodeURIComponent(encoded || plain || fallback) } catch { return plain || fallback }
}

// `fetchFile(url)` must send no credentials; `fileError(status)` builds the
// error thrown when the bucket refuses (for example an expired link).
export async function readProtectedFile(response, { fetchFile, fileError }) {
  const contentType = response.headers.get('Content-Type') || ''
  if (!contentType.startsWith(FILE_LINK_CONTENT_TYPE)) {
    return {
      blob: await response.blob(),
      contentType: contentType || 'application/octet-stream',
      fileName: responseFileName(response),
    }
  }
  const link = await response.json()
  const file = await fetchFile(link.url)
  if (!file.ok) throw fileError(file.status)
  return {
    blob: await file.blob(),
    contentType: link.content_type || file.headers.get('Content-Type') || 'application/octet-stream',
    fileName: link.file_name || 'document',
  }
}
