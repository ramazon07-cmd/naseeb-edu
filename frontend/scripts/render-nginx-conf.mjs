// Renders nginx.conf for the production image: computes the Content-Security-
// Policy from the built index.html (hashes of its inline scripts) and the API
// origin the bundle was built against, plus the object-storage origins private
// files are downloaded from (presigned URLs, fetched into blob: URLs).
//   FILE_STORAGE_ORIGINS=https://<bucket>.<account>.r2.cloudflarestorage.com \
//   node scripts/render-nginx-conf.mjs <nginx.conf> <dist/index.html> [apiUrl] > out.conf
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export function inlineScriptHashes(html) {
  const hashes = []
  for (const match of html.matchAll(/<script(\s[^>]*)?>([\s\S]*?)<\/script>/gi)) {
    const attributes = match[1] || ''
    if (/\ssrc\s*=/.test(attributes) || !match[2].trim()) continue
    hashes.push(`'sha256-${createHash('sha256').update(match[2], 'utf8').digest('base64')}'`)
  }
  return hashes
}

export function apiOrigin(apiUrl) {
  if (!apiUrl) return ''
  try {
    const url = new URL(apiUrl)
    return /^https?:$/.test(url.protocol) ? url.origin : ''
  } catch {
    return '' // relative URL: same origin, already covered by 'self'
  }
}

// Comma/space separated list; anything but a bare http(s) origin fails the build.
export function storageOrigins(value) {
  return String(value || '').split(/[\s,]+/).filter(Boolean).map((entry) => {
    let url
    try { url = new URL(entry) } catch { throw new Error(`FILE_STORAGE_ORIGINS: invalid origin ${entry}`) }
    if (!/^https?:$/.test(url.protocol) || url.origin !== entry.replace(/\/$/, '')) {
      throw new Error(`FILE_STORAGE_ORIGINS: expected an origin like https://files.example.com, got ${entry}`)
    }
    return url.origin
  })
}

export function buildCsp(html, apiUrl, fileOrigins = []) {
  // Private files are fetched from the bucket and shown via blob: URLs, so the
  // bucket only needs connect-src (img-src/frame-src already allow blob:).
  const connect = [...new Set(["'self'", apiOrigin(apiUrl), ...fileOrigins].filter(Boolean))].join(' ')
  return [
    "default-src 'self'",
    `script-src 'self' ${inlineScriptHashes(html).join(' ')}`.trim(),
    // React style={} attributes and the inline boot <style> need this.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect}`,
    // Google Docs previews and blob: previews of private uploaded files.
    "frame-src https://docs.google.com blob:",
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join('; ')
}

export function renderNginxConf(template, html, apiUrl, fileOrigins = []) {
  if (template.split('__CSP__').length !== 2) throw new Error('nginx.conf must contain exactly one __CSP__ placeholder')
  const csp = buildCsp(html, apiUrl, fileOrigins).replace(/"/g, '\\"')
  return template.replace('__CSP__', () => csp)
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [templatePath, htmlPath, apiUrl = process.env.VITE_API_URL || ''] = process.argv.slice(2)
  const fileOrigins = storageOrigins(process.env.FILE_STORAGE_ORIGINS)
  process.stdout.write(renderNginxConf(readFileSync(templatePath, 'utf8'), readFileSync(htmlPath, 'utf8'), apiUrl, fileOrigins))
}
