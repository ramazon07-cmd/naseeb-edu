// Block-level delta saves for Essay Lab documents.
//
// The client keeps the last document the server acknowledged and sends only
// the top-level blocks that changed, plus the sha256 of the whole resulting
// document. The server applies the ops to its stored copy under the row lock
// and checks the hash, so any disagreement turns into a full save, never into
// a wrong document.
//
// Must match backend/apps/admissions/essay_lab/doc.py (normalisation, canonical
// JSON, op format). Shared cases: fixtures/doc_delta_cases.json.
//
// Ops address the base block list by index, ascending and non-overlapping:
//   {at, delete, insert: [block…]}   replace base[at .. at+delete)
//   {at, patch: [prefix, suffix, s]} replace base[at] by patching its canonical
//                                    JSON: base[:prefix] + s + base[len-suffix:]
// Framework-free: runs in the browser and under plain `node`.

import { cleanText, MAX_DEPTH } from './docText.js'

// Past this many block edits a single splice of the changed range is sent:
// it keeps the diff O((n + m) · MAX_EDIT_DISTANCE) whatever the input.
export const MAX_EDIT_DISTANCE = 64

// --- normalisation (mirror of doc.py validate_doc's cleaning) ------------------

const INLINE = new Set(['text', 'hardBreak'])
const TEXT_BLOCKS = new Set(['paragraph', 'heading', 'title', 'subtitle'])
const FLOW = new Set([...TEXT_BLOCKS, 'bulletList', 'orderedList', 'blockquote'])
const ALLOWED_CHILDREN = {
  doc: new Set([...FLOW, 'pageBreak']),
  blockquote: FLOW,
  listItem: FLOW,
  bulletList: new Set(['listItem']),
  orderedList: new Set(['listItem']),
  paragraph: INLINE,
  heading: INLINE,
  title: INLINE,
  subtitle: INLINE,
}
const MARKS = new Set(['bold', 'italic', 'underline', 'strike', 'textStyle', 'highlight', 'link'])
const DROP_WHEN_EMPTY = new Set(['bulletList', 'orderedList', 'listItem', 'blockquote'])
export const TEXT_ALIGN = new Set(['center', 'right', 'justify'])
export const LINE_HEIGHTS = ['1', '1.15', '1.5', '2']
export const MAX_INDENT = 8
export const FONT_FAMILIES = [
  'Arial', 'Times New Roman', 'Georgia', 'Courier New', 'Verdana',
  'Newsreader', 'Montserrat', 'Merriweather', 'Lora', 'Roboto',
]
export const FONT_SIZE_RANGE = [8, 96]
const HEX_COLOR = /^#[0-9a-fA-F]{6}$/
const MAX_HREF = 2048
// Same character rules as doc.py's LINK_HREF (no /i and no \s: their Unicode rules differ from Python’s).
// eslint-disable-next-line no-control-regex
const LINK_HREF = /^(?:[hH][tT][tT][pP][sS]?:\/\/|[mM][aA][iI][lL][tT][oO]:)[^\x00-\x20\x7f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff<>"]+$/

class Invalid extends Error {}

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)
// Python truthiness: empty lists and objects are false too.
const truthy = (value) => (Array.isArray(value) ? value.length > 0 : isObject(value) ? Object.keys(value).length > 0 : Boolean(value))
const isInt = (value) => Number.isInteger(value) && typeof value === 'number'

function cleanColor(value) {
  if (value == null) return null
  if (typeof value !== 'string' || !HEX_COLOR.test(value)) throw new Invalid()
  return value.toLowerCase()
}

// Allowed attributes of a mark, or null when it carries nothing (then it is dropped).
function markAttrs(type, attrs) {
  if (attrs != null && !isObject(attrs)) throw new Invalid()
  const values = attrs || {}
  if (type === 'textStyle') {
    const cleaned = {}
    if (values.fontFamily != null) {
      if (!FONT_FAMILIES.includes(values.fontFamily)) throw new Invalid()
      cleaned.fontFamily = values.fontFamily
    }
    if (values.fontSize != null) {
      if (!isInt(values.fontSize) || values.fontSize < FONT_SIZE_RANGE[0] || values.fontSize > FONT_SIZE_RANGE[1]) throw new Invalid()
      cleaned.fontSize = values.fontSize
    }
    const color = cleanColor(values.color)
    if (color) cleaned.color = color
    return Object.keys(cleaned).length ? cleaned : null
  }
  if (type === 'highlight') {
    const color = cleanColor(values.color)
    return color ? { color } : null
  }
  if (type === 'link') {
    const { href } = values
    if (typeof href !== 'string' || [...href].length > MAX_HREF || !LINK_HREF.test(href)) throw new Invalid()
    return { href }
  }
  return {}
}

function cleanMarks(marks) {
  if (marks == null) return null
  if (!Array.isArray(marks) || marks.length > MARKS.size) throw new Invalid()
  const cleaned = []
  const seen = new Set()
  for (const mark of marks) {
    if (!isObject(mark) || !MARKS.has(mark.type)) throw new Invalid()
    const attrs = markAttrs(mark.type, mark.attrs)
    if (seen.has(mark.type) || attrs === null) continue
    seen.add(mark.type)
    cleaned.push(Object.keys(attrs).length ? { type: mark.type, attrs } : { type: mark.type })
  }
  return cleaned.length ? cleaned : null
}

function blockFormat(values, cleaned) {
  const align = values.textAlign
  if (align != null && align !== 'left') {
    if (!TEXT_ALIGN.has(align)) throw new Invalid()
    cleaned.textAlign = align
  }
  if (values.lineHeight != null) {
    if (!LINE_HEIGHTS.includes(values.lineHeight)) throw new Invalid()
    cleaned.lineHeight = values.lineHeight
  }
  const indent = values.indent
  if (indent != null) {
    if (!isInt(indent) || indent < 0 || indent > MAX_INDENT) throw new Invalid()
    if (indent) cleaned.indent = indent
  }
  return cleaned
}

function cleanAttrs(type, attrs) {
  if (attrs != null && !isObject(attrs)) throw new Invalid()
  const values = attrs || {}
  if (type === 'heading') {
    if (values.level !== 1 && values.level !== 2 && values.level !== 3) throw new Invalid()
    return blockFormat(values, { level: values.level })
  }
  if (TEXT_BLOCKS.has(type)) {
    const cleaned = blockFormat(values, {})
    return Object.keys(cleaned).length ? cleaned : null
  }
  if (type === 'bulletList') {
    if (values.style == null) return null
    if (values.style !== 'bullet' && values.style !== 'dash') throw new Invalid()
    return { style: values.style }
  }
  if (type === 'orderedList') {
    const start = values.start == null ? 1 : values.start
    if (!Number.isInteger(start) || start < 0 || start > 10000) throw new Invalid()
    return start === 1 ? null : { start }
  }
  return null
}

function cleanNode(node, depth, allowed) {
  if (depth > MAX_DEPTH || !isObject(node)) throw new Invalid()
  const type = node.type
  if (typeof type !== 'string' || !allowed.has(type)) throw new Invalid()
  if (type === 'text') {
    if (typeof node.text !== 'string') throw new Invalid()
    const text = cleanText(node.text)
    if (!text) return null
    const cleaned = { type: 'text', text }
    const marks = cleanMarks(node.marks)
    if (marks) cleaned.marks = marks
    return cleaned
  }
  if (truthy(node.marks)) throw new Invalid()
  if (type === 'hardBreak' || type === 'pageBreak') return { type }
  const cleaned = { type }
  const attrs = cleanAttrs(type, node.attrs)
  if (attrs) cleaned.attrs = attrs
  const content = node.content == null ? [] : node.content
  if (!Array.isArray(content)) throw new Invalid()
  const children = []
  for (const child of content) {
    const next = cleanNode(child, depth + 1, ALLOWED_CHILDREN[type])
    if (next) children.push(next)
  }
  if (children.length) cleaned.content = children
  else if (DROP_WHEN_EMPTY.has(type)) return null
  return cleaned
}

export const isAllowedHref = (href) => typeof href === 'string' && [...href].length <= MAX_HREF && LINK_HREF.test(href)

// What a student types in the link box -> an allowed href, or null.
export function normalizeHref(value) {
  const text = String(value || '').trim()
  if (!text) return null
  if (isAllowedHref(text)) return text
  if (/^[^\s@/]+@[^\s@/]+\.[^\s@/]+$/.test(text) && isAllowedHref(`mailto:${text}`)) return `mailto:${text}`
  if (/^[^\s:/]+\.[^\s]+$/.test(text) && isAllowedHref(`https://${text}`)) return `https://${text}`
  return null
}

// The editor's JSON with any formatting the server would reject dropped
// (a pasted link to a relative address, an odd colour): one bad mark must
// never block saving the whole text. Only marks and block attributes are
// repaired; the node structure comes from the editor schema.
export function repairDoc(node) {
  if (!isObject(node)) return node
  let next = node
  if (Array.isArray(node.marks)) {
    const marks = []
    for (const mark of node.marks) {
      try {
        const attrs = markAttrs(mark?.type, mark?.attrs)
        if (attrs !== null && MARKS.has(mark?.type)) marks.push(Object.keys(attrs).length ? { ...mark, attrs } : { type: mark.type })
      } catch {
        if (mark?.type === 'textStyle') {
          // Keep the parts that are fine.
          const kept = {}
          for (const key of ['fontFamily', 'fontSize', 'color']) {
            try { const one = markAttrs('textStyle', { [key]: mark.attrs?.[key] }); if (one) Object.assign(kept, one) } catch { /* drop it */ }
          }
          if (Object.keys(kept).length) marks.push({ type: 'textStyle', attrs: kept })
        }
      }
    }
    next = { ...next, marks }
  }
  if (TEXT_BLOCKS.has(node.type) && isObject(node.attrs)) {
    const attrs = { ...node.attrs }
    for (const key of ['textAlign', 'lineHeight', 'indent']) {
      try { blockFormat({ [key]: attrs[key] }, {}) } catch { attrs[key] = null }
    }
    next = { ...next, attrs }
  }
  if (Array.isArray(node.content)) next = { ...next, content: node.content.map(repairDoc) }
  return next
}

// -> the document exactly as the server would store it, or null when the
// server would reject it (the caller then sends it unchanged and gets the 400).
export function normalizeDoc(doc) {
  if (!isObject(doc) || doc.type !== 'doc') return null
  try {
    const cleaned = cleanNode(doc, 1, new Set(['doc']))
    if (!cleaned.content) cleaned.content = [{ type: 'paragraph' }]
    return cleaned
  } catch (error) {
    if (error instanceof Invalid || error instanceof RangeError) return null
    throw error
  }
}

// --- canonical JSON + sha256 ------------------------------------------------------

// Same bytes as Python's json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=True).
const NON_ASCII = /[\u007f-\uffff]/g
const escapeChar = (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, '0')}`
const quote = (text) => JSON.stringify(text).replace(NON_ASCII, escapeChar)

export function canonicalJson(value) {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return quote(value)
  if (typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`
  const keys = Object.keys(value).filter((key) => value[key] !== undefined).sort()
  return `{${keys.map((key) => `${quote(key)}:${canonicalJson(value[key])}`).join(',')}}`
}

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

// Synchronous sha256 of an ASCII string (canonical JSON always is), as hex.
// Synchronous so the save queue can decide what to send without awaiting.
export function sha256Ascii(text) {
  const length = text.length
  const blocks = ((length + 9 + 63) >> 6) << 4
  const words = new Uint32Array(blocks)
  for (let i = 0; i < length; i += 1) words[i >> 2] |= (text.charCodeAt(i) & 0xff) << (24 - (i & 3) * 8)
  words[length >> 2] |= 0x80 << (24 - (length & 3) * 8)
  words[blocks - 1] = length * 8
  words[blocks - 2] = Math.floor(length / 0x20000000)
  const h = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19])
  const w = new Uint32Array(64)
  for (let offset = 0; offset < blocks; offset += 16) {
    for (let i = 0; i < 16; i += 1) w[i] = words[offset + i]
    for (let i = 16; i < 64; i += 1) {
      const a = w[i - 15]
      const b = w[i - 2]
      const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3)
      const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10)
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0
    }
    let [a, b, c, d, e, f, g, hh] = h
    for (let i = 0; i < 64; i += 1) {
      const s1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7))
      const t1 = (hh + s1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0
      const s0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10))
      const t2 = (s0 + ((a & b) ^ (a & c) ^ (b & c))) | 0
      hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh
  }
  return Array.from(h, (value) => value.toString(16).padStart(8, '0')).join('')
}

const docJson = (blocks) => `{"content":[${blocks.join(',')}],"type":"doc"}`

export function docHash(doc) {
  return sha256Ascii(canonicalJson(doc))
}

// -> { doc, blocks: canonical JSON per top-level block, hash } or null (see normalizeDoc).
export function prepareDoc(doc) {
  const normalized = normalizeDoc(doc)
  if (!normalized) return null
  const blocks = normalized.content.map(canonicalJson)
  return { doc: normalized, blocks, hash: sha256Ascii(docJson(blocks)) }
}

// --- diff ----------------------------------------------------------------------

// Myers' O((n + m) · d) shortest edit script over a[lo..) / b[lo..), with at most
// `limit` edits. -> array of 'keep' | 'delete' | 'insert', or null past the limit.
function myers(a, b, limit) {
  const n = a.length
  const m = b.length
  const offset = n + m + 1
  const v = new Int32Array(2 * offset + 1)
  const trace = []
  for (let d = 0; d <= limit; d += 1) {
    trace.push(v.slice())
    for (let k = -d; k <= d; k += 2) {
      let x = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1
      let y = x - k
      while (x < n && y < m && a[x] === b[y]) { x += 1; y += 1 }
      v[offset + k] = x
      if (x >= n && y >= m) return backtrack(trace, n, m, offset)
    }
  }
  return null
}

function backtrack(trace, n, m, offset) {
  const script = []
  let x = n
  let y = m
  for (let d = trace.length - 1; d > 0; d -= 1) {
    const v = trace[d]
    const k = x - y
    const prevK = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? k + 1 : k - 1
    const prevX = v[offset + prevK]
    const prevY = prevX - prevK
    while (x > prevX && y > prevY) { script.push('keep'); x -= 1; y -= 1 }
    script.push(x === prevX ? 'insert' : 'delete')
    x = prevX
    y = prevY
  }
  while (x > 0 && y > 0) { script.push('keep'); x -= 1; y -= 1 }
  return script.reverse()
}

// Patch one block's canonical JSON: shared prefix/suffix plus the changed middle.
function patchOp(at, before, after) {
  const limit = Math.min(before.length, after.length)
  let prefix = 0
  while (prefix < limit && before.charCodeAt(prefix) === after.charCodeAt(prefix)) prefix += 1
  let suffix = 0
  while (suffix < limit - prefix && before.charCodeAt(before.length - 1 - suffix) === after.charCodeAt(after.length - 1 - suffix)) suffix += 1
  return { at, patch: [prefix, suffix, after.slice(prefix, after.length - suffix)] }
}

function pushHunk(ops, at, deleted, insertedFrom, insertedTo, base, next) {
  if (deleted === insertedTo - insertedFrom) {
    // Edited in place (the usual case: typing inside a paragraph): send each block
    // as a patch when that is shorter than sending the block itself.
    for (let i = 0; i < deleted; i += 1) {
      const before = base.blocks[at + i]
      const after = next.blocks[insertedFrom + i]
      const patch = patchOp(at + i, before, after)
      const patchSize = patch.patch[2].length + 24
      ops.push(patchSize < after.length ? patch : { at: at + i, delete: 1, insert: [next.doc.content[insertedFrom + i]] })
    }
    return
  }
  ops.push({ at, delete: deleted, insert: next.doc.content.slice(insertedFrom, insertedTo) })
}

// Ops turning `base` into `next` (both from prepareDoc). [] when they are equal.
export function diffDocs(base, next, limit = MAX_EDIT_DISTANCE) {
  const a = base.blocks
  const b = next.blocks
  let start = 0
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1
  let endA = a.length
  let endB = b.length
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) { endA -= 1; endB -= 1 }
  const ops = []
  if (start === endA && start === endB) return ops
  const script = endA > start && endB > start ? myers(a.slice(start, endA), b.slice(start, endB), limit) : null
  if (!script) {
    pushHunk(ops, start, endA - start, start, endB, base, next)
    return ops
  }
  let i = start
  let j = start
  let hunk = null
  const close = () => {
    if (hunk) pushHunk(ops, hunk.at, i - hunk.at, hunk.from, j, base, next)
    hunk = null
  }
  for (const step of script) {
    if (step === 'keep') { close(); i += 1; j += 1; continue }
    if (!hunk) hunk = { at: i, from: j }
    if (step === 'delete') i += 1
    else j += 1
  }
  close()
  return ops
}

// Applies ops to a list of blocks (objects). Mirrors doc.py apply_ops; throws on
// ops that don't fit, where the server answers 409 "resync".
export function applyOps(blocks, ops) {
  const result = []
  let cursor = 0
  for (const op of ops) {
    const { at } = op
    if (at < cursor || at > blocks.length) throw new Error('ops out of order or range')
    result.push(...blocks.slice(cursor, at))
    if (op.patch) {
      if (at >= blocks.length) throw new Error('patch past the end')
      const [prefix, suffix, middle] = op.patch
      const old = canonicalJson(blocks[at])
      if (prefix + suffix > old.length) throw new Error('patch does not fit')
      result.push(JSON.parse(old.slice(0, prefix) + middle + old.slice(old.length - suffix)))
      cursor = at + 1
    } else {
      if (at + op.delete > blocks.length) throw new Error('delete past the end')
      result.push(...op.insert)
      cursor = at + op.delete
    }
  }
  result.push(...blocks.slice(cursor))
  return result
}
