// Page geometry and the pagination pass for the "Pages" view.
//
// Pure functions only: the editor plugin (pagination.js) reads block and line
// positions from the DOM and hands them in through `measure`, so the algorithm
// runs (and is tested) without a browser.
//
// A block that does not fit on the rest of a sheet is split between two lines
// (the lines that fit stay, the rest starts the next sheet); a block whose
// first line does not fit, or that has no lines (an empty paragraph), moves
// to the next sheet whole.

export const PAGE_SIZES = ['a4', 'letter']

// Millimetres; both papers get Google Docs' default one-inch margins.
export const PAPER = {
  a4: { width: 210, height: 297, margin: 25.4 },
  letter: { width: 215.9, height: 279.4, margin: 25.4 },
}

export const SHEET_GAP = 20
const PX_PER_MM = 96 / 25.4
const EPSILON = 0.5
// A spacer must keep some height: a zero-height block lets the margins around
// it collapse, which would move the next block somewhere unexpected.
const MIN_SPACER = 1

export function normalizePageSize(size) {
  return PAGE_SIZES.includes(size) ? size : 'a4'
}

// The sheet's width at 100% zoom (A4: 794px, Letter: 816px).
export function paperWidth(size) {
  return Math.round(PAPER[normalizePageSize(size)].width * PX_PER_MM)
}

// Sheet geometry in CSS px at 100% zoom. Narrow windows scale the whole
// stack down (like Docs' zoom), so a page always holds the same text.
export function pageGeometry(size) {
  const paper = PAPER[normalizePageSize(size)]
  const round = (value) => Math.round(value * PX_PER_MM * 100) / 100
  const margin = round(paper.margin)
  return { size: normalizePageSize(size), width: round(paper.width), height: round(paper.height), gap: SHEET_GAP, top: margin, bottom: margin, side: margin }
}

export function sameGeometry(a, b) {
  if (!a || !b) return a === b
  return a.size === b.size
}

export const pitch = (geometry) => geometry.height + geometry.gap
export const contentTop = (geometry, page) => page * pitch(geometry) + geometry.top
export const contentBottom = (geometry, page) => page * pitch(geometry) + geometry.height - geometry.bottom
export const pageAt = (geometry, y) => Math.max(0, Math.floor(y / pitch(geometry)))

// Height of the whole stack of `pages` sheets.
export const stackHeight = (geometry, pages) => pages * geometry.height + Math.max(0, pages - 1) * geometry.gap

// Adjoining vertical margins collapse into the largest positive plus the most negative one.
export function collapseMargins(a, b) {
  return Math.max(a, b, 0) + Math.min(a, b, 0)
}

/**
 * One pagination pass over the top-level blocks from `start` on.
 *
 * measure(i) -> { top, bottom, inlineGaps, pageBreak, spacer, lines }: block i
 *   as laid out now, relative to the first sheet's top. `spacer`: a spacer
 *   from the previous pass sits right before it; `inlineGaps`: total height of
 *   the previous pass's gaps inside it; `lines()` (optional, read lazily):
 *   its lines as [{ offset, height, pos }], offsets from the block's top
 *   without those gaps.
 * margins(i) -> { top, bottom }: computed margins (read only where a spacer
 *   is added or removed).
 * previous: Map(key -> page) of the gaps from the previous pass (gapKey()).
 * dirtyEnd: the last block an edit touched. Past it, the pass stops at the
 *   first gap that lands where it was before: from there on the layout is the
 *   previous pass's, so its later gaps and page count stay valid.
 *
 * Blocks before `start` must be unchanged since the previous pass.
 * Returns { gaps: [{ index, pos?, height, page }], stop, pages }: the new gaps
 * for blocks start.. (a gap with `pos` sits inside block `index`, before the
 * line at `pos`). When `stop` is set the pass converged there: keep the
 * previous gaps after it (isAfter(gap, stop)); otherwise drop every previous
 * gap from `start` on.
 */
export function paginate({ count, start = 0, dirtyEnd = count - 1, geometry, measure, margins, previous = new Map(), previousPages = 1 }) {
  const gaps = []
  if (!count) return { gaps, stop: null, pages: 1 }
  let index = Math.min(Math.max(0, start), count - 1)
  // The block before `start` has not moved, so it is its own new position.
  let before = index > 0 ? measure(index - 1) : null
  let newTop = before ? before.top : 0
  let newBottom = before ? before.bottom : 0
  let lastIsBreak = false
  const converged = (gap) => gap.index > dirtyEnd && previous.get(gapKey(gap)) === gap.page

  for (; index < count; index += 1) {
    const block = measure(index)
    const height = block.bottom - block.top - (block.inlineGaps || 0)
    let top
    if (!before) {
      top = block.top
    } else {
      const gap = block.spacer ? collapseMargins(margins(index - 1).bottom, margins(index).top) : block.top - before.bottom
      top = newBottom + gap
    }

    let lines = null
    const readLines = () => (lines ??= (block.lines?.() || []))
    let target = null
    if (before) {
      const page = pageAt(geometry, top)
      const end = contentBottom(geometry, page)
      if (before.pageBreak) target = contentTop(geometry, pageAt(geometry, newTop) + 1)
      else if (top < contentTop(geometry, page) - EPSILON) target = contentTop(geometry, page)
      else if (top > end + EPSILON) target = contentTop(geometry, page + 1)
      else if (top + height > end + EPSILON && top > contentTop(geometry, page) + EPSILON) {
        // Split between lines when at least the first line fits here.
        const first = readLines()[0]
        if (!first || top + first.offset + first.height > end + EPSILON) target = contentTop(geometry, page + 1)
      }
    }

    if (target !== null && target > top + EPSILON) {
      const above = margins(index - 1).bottom
      const own = margins(index).top
      const size = Math.max(MIN_SPACER, target - newBottom - above - own)
      top = newBottom + above + size + own
      const gap = { index, height: round(size), page: pageAt(geometry, top) }
      gaps.push(gap)
      if (converged(gap)) return { gaps, stop: gap, pages: previousPages }
    }

    // Lines that run past the page's text area start the next sheet.
    let added = 0
    let page = pageAt(geometry, top)
    if (top + height > contentBottom(geometry, page) + EPSILON && !block.pageBreak) {
      for (const line of readLines().slice(1)) {
        const lineTop = top + line.offset + added
        if (lineTop + line.height <= contentBottom(geometry, page) + EPSILON || lineTop <= contentTop(geometry, page) + EPSILON) continue
        page = Math.max(page + 1, pageAt(geometry, lineTop))
        const size = contentTop(geometry, page) - lineTop
        if (size <= EPSILON || line.pos == null) continue
        const gap = { index, pos: line.pos, height: round(size), page }
        gaps.push(gap)
        added += size
        if (converged(gap)) return { gaps, stop: gap, pages: previousPages }
      }
    }

    newTop = top
    newBottom = top + height + added
    before = block
    lastIsBreak = Boolean(block.pageBreak)
  }

  const lastPage = Math.max(pageAt(geometry, newTop), pageAt(geometry, Math.max(newTop, newBottom - EPSILON)))
  return { gaps, stop: null, pages: lastPage + 1 + (lastIsBreak ? 1 : 0) }
}

const round = (value) => Math.round(value * 100) / 100

// Identity of a gap across passes: its block, and its line for a split.
export function gapKey(gap) {
  return gap.pos == null ? `b${gap.index}` : `l${gap.index}:${gap.pos}`
}

// Whether a previous gap lies after the point where a pass converged.
export function isAfter(gap, stop) {
  if (gap.index !== stop.index) return gap.index > stop.index
  if (stop.pos == null) return gap.pos != null
  return gap.pos != null && gap.pos > stop.pos
}

// "Pages" or "Pageless", remembered per user on this device.
export const PAGE_MODES = ['pages', 'pageless']
const MODE_PREFIX = 'naseeb-essay-page-mode:'

export function readPageMode(storage, userId) {
  try {
    const value = storage?.getItem(MODE_PREFIX + (userId ?? 'me'))
    return PAGE_MODES.includes(value) ? value : 'pages'
  } catch {
    return 'pages'
  }
}

export function writePageMode(storage, userId, mode) {
  try { storage?.setItem(MODE_PREFIX + (userId ?? 'me'), mode) } catch { /* a per-device convenience only */ }
}
