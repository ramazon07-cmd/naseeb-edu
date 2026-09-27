// The "Pages" view for the Essay Lab editor.
//
// The text stays one ProseMirror document. After the browser lays it out, the
// plugin reads where the top-level blocks (and the lines of a block that
// crosses a page end) sit and adds widget decorations ("gaps") that push what
// follows to the top of the next sheet: gap = rest of the page + bottom margin
// + space between sheets + top margin. The sheets are drawn behind the text
// (EditorPage.jsx). Gaps are view-only: they never enter the document, the
// undo history or autosave.
//
// A pass runs at most once per animation frame, only after the document, the
// width or the fonts changed, and starts at the first changed block: earlier
// gaps stay. It reads everything first and then writes one transaction, so
// typing never causes a read/write layout loop.
import { Extension } from '@tiptap/react'
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { gapKey, isAfter, paginate, sameGeometry } from './pageLayout.js'

const GAP = 'el-page-gap'

// A new, empty page at the end of the document, with the cursor on it.
export function appendBlankPage(tr) {
  const { schema } = tr.doc.type
  const end = tr.doc.content.size
  tr.insert(end, [schema.nodes.pageBreak.create(), schema.nodes.paragraph.create()])
  tr.setSelection(TextSelection.create(tr.doc, end + 2))
  return tr.scrollIntoView()
}

export const paginationKey = new PluginKey('pagination')

// The range of the new doc that a transaction touched (null when only the
// selection or metadata changed). Mark steps have empty step maps, so their
// own from/to count too: bold text can rewrap a paragraph.
export function changedRange(tr) {
  let from = Infinity
  let to = -Infinity
  tr.steps.forEach((step, index) => {
    const rest = tr.mapping.slice(index + 1)
    const add = (start, end) => {
      from = Math.min(from, rest.map(start, -1))
      to = Math.max(to, rest.map(end, 1))
    }
    tr.mapping.maps[index].forEach((_oldStart, _oldEnd, newStart, newEnd) => add(newStart, newEnd))
    if (typeof step.from === 'number') add(step.from, typeof step.to === 'number' ? step.to : step.from)
    else if (typeof step.pos === 'number') add(step.pos, step.pos + 1)
  })
  return from <= to ? { from, to } : null
}

function mergeRanges(a, b) {
  if (!a) return b
  if (!b) return a
  return { from: Math.min(a.from, b.from), to: Math.max(a.to, b.to) }
}

function gapWidget(pos, gap) {
  const inline = gap.pos != null
  return Decoration.widget(pos, () => {
    const element = document.createElement(inline ? 'span' : 'div')
    element.className = inline ? `${GAP} is-inline` : GAP
    element.style.height = `${gap.height}px`
    element.setAttribute('contenteditable', 'false')
    element.setAttribute('aria-hidden', 'true')
    return element
  }, { side: -1, key: `${gapKey(gap)}:${gap.page}:${gap.height}`, ignoreSelection: true, gap })
}

// The lines of a block, from its text fragments, as offsets from the block's
// top without the gaps already inside it.
function readLines(view, dom, blockTop, scale) {
  const inner = [...dom.querySelectorAll(`.${GAP}.is-inline`)].map((element) => element.getBoundingClientRect())
  const walker = document.createTreeWalker(dom, NodeFilter.SHOW_TEXT)
  const range = document.createRange()
  const fragments = []
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!node.nodeValue) continue
    range.selectNodeContents(node)
    for (const rect of range.getClientRects()) if (rect.height > 0) fragments.push(rect)
  }
  fragments.sort((a, b) => a.top - b.top || a.left - b.left)
  const lines = []
  for (const rect of fragments) {
    const last = lines[lines.length - 1]
    if (last && rect.top < last.bottom - 2) {
      last.bottom = Math.max(last.bottom, rect.bottom)
      last.left = Math.min(last.left, rect.left)
    } else {
      lines.push({ top: rect.top, bottom: rect.bottom, left: rect.left })
    }
  }
  return lines.map((line) => {
    const above = inner.reduce((total, gap) => total + (gap.top < line.top ? gap.height : 0), 0)
    let pos
    return {
      offset: (line.top - blockTop - above) / scale,
      height: (line.bottom - line.top) / scale,
      // Hit-testing is the costly part, so only lines that get a gap pay for it.
      get pos() {
        pos ??= view.posAtCoords({ left: line.left + 1, top: (line.top + line.bottom) / 2 })?.pos ?? null
        return pos
      },
    }
  })
}

const blockIndex = (doc, pos) => Math.min(doc.childCount - 1, doc.resolve(Math.max(0, Math.min(pos, doc.content.size))).index(0))

// The edited blocks, as a doc range. A gap inside one of them may no longer
// sit where its line wraps (the text or its width changed), and a gap
// forces a line break, so those gaps are dropped before measuring.
function dirtyBlocks(doc, dirty) {
  const from = blockIndex(doc, dirty.from)
  const to = blockIndex(doc, dirty.to)
  let start = 0
  for (let index = 0; index < from; index += 1) start += doc.child(index).nodeSize
  let end = start
  for (let index = from; index <= to; index += 1) end += doc.child(index).nodeSize
  return { from: start, to: end }
}

const isInlineGap = (spec) => spec.gap?.pos != null

// Reads the layout (reads only, no writes) and returns the next gaps.
function layout(view, state) {
  const { doc } = view.state
  const root = view.dom
  if (!root.isConnected || !root.offsetWidth) return null
  const box = root.getBoundingClientRect()
  // The sheets may be scaled down to fit a narrow window: work in layout px.
  const scale = box.width / root.offsetWidth || 1
  const count = doc.childCount
  const positions = new Array(count)
  let pos = 0
  for (let index = 0; index < count; index += 1) {
    positions[index] = pos
    pos += doc.child(index).nodeSize
  }
  const indexAt = (target) => blockIndex(doc, target)
  const start = indexAt(state.dirty.from)
  const dirtyEnd = indexAt(state.dirty.to)

  // The previous gaps, re-attached to their blocks (their positions were mapped).
  const old = []
  const spacerAt = new Set()
  const inlineIn = new Map()
  for (const decoration of state.decorations.find()) {
    const index = indexAt(decoration.from)
    const inline = decoration.spec.gap.pos != null
    if (!inline && positions[index] !== decoration.from) continue
    const gap = { ...decoration.spec.gap, index, pos: inline ? decoration.from : undefined }
    old.push(gap)
    if (inline) inlineIn.set(index, (inlineIn.get(index) || 0) + gap.height)
    else spacerAt.add(index)
  }

  let measured = 0
  const element = (index) => view.nodeDOM(positions[index])
  const measure = (index) => {
    measured += 1
    const dom = element(index)
    const rect = dom?.nodeType === 1 ? dom.getBoundingClientRect() : null
    const top = rect ? (rect.top - box.top) / scale : 0
    const node = doc.child(index)
    return {
      top,
      bottom: rect ? (rect.bottom - box.top) / scale : top,
      inlineGaps: inlineIn.get(index) || 0,
      pageBreak: node.type.name === 'pageBreak',
      spacer: spacerAt.has(index),
      lines: rect && node.textContent ? () => readLines(view, dom, rect.top, scale) : null,
    }
  }
  const margins = (index) => {
    const dom = element(index)
    if (!dom || dom.nodeType !== 1) return { top: 0, bottom: 0 }
    const style = window.getComputedStyle(dom)
    return { top: parseFloat(style.marginTop) || 0, bottom: parseFloat(style.marginBottom) || 0 }
  }
  const previous = new Map(old.map((gap) => [gapKey(gap), gap.page]))
  const result = paginate({ count, start, dirtyEnd, geometry: state.geometry, measure, margins, previous, previousPages: state.pages })

  const kept = old.filter((gap) => gap.index < start || (result.stop && isAfter(gap, result.stop)))
  const gaps = [...kept, ...result.gaps]
  const decorations = DecorationSet.create(doc, gaps.map((gap) => gapWidget(gap.pos ?? positions[gap.index], gap)))
  // How much of the document the pass had to look at (for diagnostics).
  const stats = { blocks: count, start, converged: Boolean(result.stop), measured }
  return { decorations, pages: result.pages, stats }
}

const EMPTY = { geometry: null, decorations: DecorationSet.empty, pages: 1, dirty: null, scroll: false, lastPass: null }

// Gaps and the page count, recomputed after layout from the first changed block on.
export function paginationPlugin() {
  return new Plugin({
    key: paginationKey,
    state: {
      init: () => EMPTY,
      apply(tr, value, _oldState, newState) {
        const meta = tr.getMeta(paginationKey)
        let next = value
        if (tr.docChanged && value.geometry) {
          const mapped = value.dirty && { from: tr.mapping.map(value.dirty.from, -1), to: tr.mapping.map(value.dirty.to, 1) }
          next = {
            ...next,
            decorations: value.decorations.map(tr.mapping, tr.doc),
            dirty: mergeRanges(mapped, changedRange(tr)),
            // The edit wanted the cursor in view, and new gaps may move it again.
            scroll: next.scroll || tr.scrolledIntoView,
          }
        }
        if (!meta) return next
        if ('geometry' in meta && !sameGeometry(meta.geometry, next.geometry)) {
          next = meta.geometry
            ? { ...next, geometry: meta.geometry, dirty: { from: 0, to: newState.doc.content.size } }
            : EMPTY
        }
        if (meta.relayout && next.geometry) next = { ...next, dirty: { from: 0, to: newState.doc.content.size } }
        if (meta.strip) next = { ...next, decorations: next.decorations.remove(next.decorations.find(meta.strip.from, meta.strip.to, isInlineGap)) }
        if (meta.layout) next = { ...next, decorations: meta.layout.decorations, pages: meta.layout.pages, lastPass: meta.layout.stats, dirty: null, scroll: false }
        return next
      },
    },
    props: {
      decorations: (state) => paginationKey.getState(state)?.decorations,
    },
    view() {
      let frame = 0
      let running = false
      let current = null
      const run = () => {
        frame = 0
        const view = current
        const state = view && !view.isDestroyed && paginationKey.getState(view.state)
        // Mid-composition (IME) the next transaction schedules the pass again.
        if (!state?.geometry || !state.dirty || view.composing || !view.dom.offsetWidth) return
        const started = window.performance.now()
        running = true
        try {
          const strip = dirtyBlocks(view.state.doc, state.dirty)
          if (state.decorations.find(strip.from, strip.to, isInlineGap).length) {
            view.dispatch(view.state.tr.setMeta(paginationKey, { strip }).setMeta('addToHistory', false))
          }
          const next = layout(view, paginationKey.getState(view.state))
          if (!next) return
          next.stats.ms = window.performance.now() - started
          const tr = view.state.tr.setMeta(paginationKey, { layout: next }).setMeta('addToHistory', false)
          view.dispatch(paginationKey.getState(view.state).scroll ? tr.scrollIntoView() : tr)
        } finally {
          running = false
        }
      }
      return {
        update(view) {
          current = view
          const state = paginationKey.getState(view.state)
          // Batched: however many transactions land in a frame, one pass runs.
          if (state?.geometry && state.dirty && !frame && !running) frame = window.requestAnimationFrame(run)
        },
        destroy() { if (frame) window.cancelAnimationFrame(frame) },
      }
    },
  })
}

export const Pagination = Extension.create({
  name: 'pagination',

  addCommands() {
    return {
      addBlankPage: () => ({ tr, dispatch }) => {
        if (dispatch) appendBlankPage(tr)
        return true
      },
    }
  },

  addProseMirrorPlugins() {
    return [paginationPlugin()]
  },
})

// View-only changes: they never touch the doc or the undo history.
export function setPageGeometry(editor, geometry) {
  if (!editor || editor.isDestroyed) return
  editor.view.dispatch(editor.state.tr.setMeta(paginationKey, { geometry }).setMeta('addToHistory', false))
}

export function relayoutPages(editor) {
  if (!editor || editor.isDestroyed) return
  editor.view.dispatch(editor.state.tr.setMeta(paginationKey, { relayout: true }).setMeta('addToHistory', false))
}

export function pageCount(editor) {
  return (editor && !editor.isDestroyed && paginationKey.getState(editor.state)?.pages) || 1
}
