// Tiptap extensions for collaboration (our own; Tiptap Pro isn't used).
//
//  - BlockIds: every top-level block carries attrs.bid, a stable id the server
//    uses to merge edits paragraph by paragraph (docMerge.js). New blocks get a
//    random id; a split paragraph's second half never inherits the first's.
//  - Comment / SuggestInsert / SuggestDelete: marks holding the id of a
//    comment thread or suggestion (docDelta.js validates them like doc.py).
//    They sort after every formatting mark (low priority), in that order,
//    matching how the server writes them (collab.py MARK_RANK).
//
// The student never creates these marks; the server adds them and applies
// accept/reject decisions. The editor only shows them and reports clicks.
import { Extension, Mark, mergeAttributes } from '@tiptap/react'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { BID_PATTERN } from './docDelta.js'
import { applyDocChanges } from './editorMerge.js'

const BLOCK_TYPES = ['paragraph', 'heading', 'title', 'subtitle', 'bulletList', 'orderedList', 'blockquote', 'pageBreak']

export function randomBid(random = Math.random) {
  let id = 'r'
  const cryptoApi = typeof globalThis !== 'undefined' ? globalThis.crypto : null
  if (cryptoApi?.getRandomValues) {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(8))
    for (const byte of bytes) id += (byte % 36).toString(36)
    return id
  }
  for (let i = 0; i < 8; i += 1) id += Math.floor(random() * 36).toString(36)
  return id
}

const blockIdsKey = new PluginKey('blockIds')

export const BlockIds = Extension.create({
  name: 'blockIds',
  addGlobalAttributes() {
    return [{
      types: BLOCK_TYPES,
      attributes: {
        bid: { default: null, rendered: false, keepOnSplit: false, parseHTML: () => null },
      },
    }]
  },
  addProseMirrorPlugins() {
    return [new Plugin({
      key: blockIdsKey,
      appendTransaction(transactions, _oldState, state) {
        if (!transactions.some((tr) => tr.docChanged)) return null
        const seen = new Set()
        let tr = null
        state.doc.forEach((node, offset) => {
          const bid = node.attrs?.bid
          if (typeof bid === 'string' && BID_PATTERN.test(bid) && !seen.has(bid)) { seen.add(bid); return }
          if (!('bid' in (node.attrs || {}))) return
          let fresh = randomBid()
          while (seen.has(fresh)) fresh = randomBid()
          seen.add(fresh)
          tr = (tr || state.tr).setNodeAttribute(offset, 'bid', fresh)
        })
        if (tr) tr.setMeta('addToHistory', false)
        return tr
      },
    })]
  },
})

function idAttribute() {
  return {
    id: {
      default: null,
      parseHTML: () => null,
      renderHTML: (attributes) => (attributes.id ? { 'data-collab-id': String(attributes.id) } : {}),
    },
  }
}

// Marks are never pasted in from outside (parseHTML: none) and never grow when
// the student types at their edge (inclusive: false).
export const CommentMark = Mark.create({
  name: 'comment',
  priority: 30,
  inclusive: false,
  excludes: '',
  spanning: true,
  addAttributes: idAttribute,
  parseHTML: () => [],
  renderHTML: ({ HTMLAttributes }) => ['span', mergeAttributes(HTMLAttributes, { class: 'el-comment' }), 0],
})

export const SuggestInsertMark = Mark.create({
  name: 'suggestInsert',
  priority: 29,
  inclusive: false,
  addAttributes: idAttribute,
  parseHTML: () => [],
  renderHTML: ({ HTMLAttributes }) => ['ins', mergeAttributes(HTMLAttributes, { class: 'el-suggest-ins' }), 0],
})

export const SuggestDeleteMark = Mark.create({
  name: 'suggestDelete',
  priority: 28,
  inclusive: false,
  addAttributes: idAttribute,
  parseHTML: () => [],
  renderHTML: ({ HTMLAttributes }) => ['del', mergeAttributes(HTMLAttributes, { class: 'el-suggest-del' }), 0],
})

// ---------------------------------------------------------------------------
// The selected thread or suggestion is outlined (a decoration, never saved),
// and a click on marked text selects it.
export const collabKey = new PluginKey('collabFocus')

function markRanges(doc, type, id) {
  const ranges = []
  doc.descendants((node, pos) => {
    if (!node.isText) return true
    if (node.marks.some((mark) => mark.type.name === type && mark.attrs.id === id)) {
      const last = ranges[ranges.length - 1]
      if (last && last.to === pos) last.to = pos + node.nodeSize
      else ranges.push({ from: pos, to: pos + node.nodeSize })
    }
    return false
  })
  return ranges
}

// -> { comment: Set(ids), suggestion: Set(ids) } present in the doc.
export function anchoredIds(doc) {
  const comment = new Set()
  const suggestion = new Set()
  doc.descendants((node) => {
    if (!node.isText) return true
    for (const mark of node.marks) {
      if (mark.type.name === 'comment') comment.add(mark.attrs.id)
      else if (mark.type.name === 'suggestInsert' || mark.type.name === 'suggestDelete') suggestion.add(mark.attrs.id)
    }
    return false
  })
  return { comment, suggestion }
}

// Where an item's text starts (for sorting cards like the text and scrolling to it).
export function itemRange(doc, item) {
  if (!item) return null
  const types = item.kind === 'thread' ? ['comment'] : ['suggestDelete', 'suggestInsert']
  let best = null
  for (const type of types) {
    for (const range of markRanges(doc, type, item.id)) {
      if (!best || range.from < best.from) best = { from: range.from, to: Math.max(range.to, best?.to ?? 0) }
      else best.to = Math.max(best.to, range.to)
    }
  }
  return best
}

export const CollabFocus = Extension.create({
  name: 'collabFocus',
  addOptions() {
    return { onSelect: () => {} }
  },
  addProseMirrorPlugins() {
    const options = this.options
    return [new Plugin({
      key: collabKey,
      state: {
        init: () => null,
        apply(tr, previous) {
          const meta = tr.getMeta(collabKey)
          return meta !== undefined ? meta : previous
        },
      },
      props: {
        decorations(state) {
          const active = collabKey.getState(state)
          if (!active) return null
          const types = active.kind === 'thread' ? ['comment'] : ['suggestInsert', 'suggestDelete']
          const decorations = types.flatMap((type) => markRanges(state.doc, type, active.id))
            .map((range) => Decoration.inline(range.from, range.to, { class: 'el-collab-active' }))
          return decorations.length ? DecorationSet.create(state.doc, decorations) : null
        },
        handleClick(view, pos) {
          const $pos = view.state.doc.resolve(pos)
          const marks = [...($pos.nodeAfter?.marks || []), ...($pos.nodeBefore?.marks || [])]
          const suggestion = marks.find((mark) => mark.type.name === 'suggestInsert' || mark.type.name === 'suggestDelete')
          const comment = marks.find((mark) => mark.type.name === 'comment')
          const hit = suggestion ? { kind: 'suggestion', id: suggestion.attrs.id } : comment ? { kind: 'thread', id: comment.attrs.id } : null
          if (hit) options.onSelect(hit)
          return false
        },
      },
    })]
  },
})

export function setCollabFocus(editor, item) {
  if (!editor || editor.isDestroyed) return
  editor.view.dispatch(editor.state.tr.setMeta(collabKey, item ? { kind: item.kind, id: item.id } : null).setMeta('addToHistory', false))
}

// Takes a newer server doc into the editor (see editorMerge.js).
export { applyDocChanges }
