// Tiptap / ProseMirror extensions for the Essay Lab editor.
import { Extension, wrappingInputRule } from '@tiptap/react'
import { BulletList } from '@tiptap/extension-list'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { buildIndex, locateQuotes } from './anchors.js'

// ---------------------------------------------------------------------------
// Dash list = bulletList with attrs.style "dash" (rendered as a CSS class).
// "- " starts a dash list, "* " / "+ " / "• " a bullet list.
export const DashBulletList = BulletList.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      style: {
        default: null,
        parseHTML: (element) => (element.getAttribute('data-style') === 'dash' || element.classList.contains('list-dash') ? 'dash' : null),
        renderHTML: (attributes) => (attributes.style === 'dash' ? { 'data-style': 'dash', class: 'list-dash' } : {}),
      },
    }
  },
  addCommands() {
    return {
      ...this.parent?.(),
      toggleDashList: () => ({ editor, commands, chain }) => {
        if (editor.isActive('bulletList', { style: 'dash' })) return commands.toggleBulletList()
        if (editor.isActive('bulletList')) return commands.updateAttributes('bulletList', { style: 'dash' })
        return chain().toggleBulletList().updateAttributes('bulletList', { style: 'dash' }).run()
      },
      togglePlainBulletList: () => ({ editor, commands, chain }) => {
        if (editor.isActive('bulletList', { style: 'dash' })) return commands.updateAttributes('bulletList', { style: null })
        if (editor.isActive('bulletList')) return commands.toggleBulletList()
        return chain().toggleBulletList().updateAttributes('bulletList', { style: null }).run()
      },
    }
  },
  addKeyboardShortcuts() {
    return {
      'Mod-Shift-8': () => this.editor.commands.togglePlainBulletList(),
      'Mod-Shift-9': () => this.editor.commands.toggleDashList(),
    }
  },
  addInputRules() {
    return [
      // Only join the list above when it has the same style, so "* " right
      // after a dash list starts a bullet list instead of extending it.
      wrappingInputRule({ find: /^\s*-\s$/, type: this.type, getAttributes: () => ({ style: 'dash' }), joinPredicate: (_match, node) => node.attrs.style === 'dash' }),
      wrappingInputRule({ find: /^\s*([+*•])\s$/, type: this.type, getAttributes: () => ({ style: null }), joinPredicate: (_match, node) => node.attrs.style !== 'dash' }),
    ]
  },
})

// ---------------------------------------------------------------------------
// Editor-level shortcuts: Mod-\ clears formatting (like Google Docs),
// Mod-s saves now instead of opening the browser's "save page" dialog.
export const EssayShortcuts = Extension.create({
  name: 'essayShortcuts',
  addOptions() {
    return { onSave: () => {}, onEscape: () => false }
  },
  addKeyboardShortcuts() {
    return {
      'Mod-\\': () => this.editor.chain().focus().unsetAllMarks().clearNodes().run(),
      'Mod-s': () => { this.options.onSave(); return true },
      Escape: () => Boolean(this.options.onEscape()),
    }
  },
})

// ---------------------------------------------------------------------------
// Coach highlights. Decorations only (never marks), so they are never saved.
// After every change the quotes are searched again (one textblock at a time,
// cached per node) and a highlight whose text is gone is dropped.
export const coachKey = new PluginKey('coachHighlights')
const indexCache = new WeakMap()

function textblocks(doc) {
  const blocks = []
  doc.descendants((node, pos) => {
    if (!node.isTextblock) return true
    let index = indexCache.get(node)
    if (!index) {
      index = buildIndex(node.textBetween(0, node.content.size, undefined, '\n'))
      indexCache.set(node, index)
    }
    blocks.push({ offset: pos + 1, index })
    return false
  })
  return blocks
}

function buildDecorations(doc, notes, located, activeId) {
  const decorations = []
  for (const note of notes) {
    const range = located.get(note.id)
    if (!range || range.from >= range.to) continue
    decorations.push(Decoration.inline(range.from, range.to, {
      class: `el-hl el-hl-${note.kind || 'reflect'}${note.id === activeId ? ' is-active' : ''}`,
      'data-note-id': note.id,
    }, { noteId: note.id }))
  }
  return DecorationSet.create(doc, decorations)
}

function anchorKey(located) {
  return [...located.keys()].sort().join('|')
}

export const CoachHighlights = Extension.create({
  name: 'coachHighlights',
  addOptions() {
    return { onAnchorsChange: () => {}, onNoteClick: () => {} }
  },
  addProseMirrorPlugins() {
    const options = this.options
    return [new Plugin({
      key: coachKey,
      state: {
        init: () => ({ notes: [], activeId: null, located: new Map(), decorations: DecorationSet.empty }),
        apply(tr, previous, _oldState, newState) {
          const meta = tr.getMeta(coachKey)
          if (!meta && (!tr.docChanged || !previous.notes.length)) return previous
          const notes = meta?.notes ?? previous.notes
          const activeId = meta && 'activeId' in meta ? meta.activeId : previous.activeId
          let located = previous.located
          if (meta?.notes || tr.docChanged) {
            const hints = new Map()
            if (!meta?.notes) for (const [id, range] of previous.located) hints.set(id, tr.mapping.map(range.from))
            located = notes.length ? locateQuotes(textblocks(newState.doc), notes, hints) : new Map()
          }
          return { notes, activeId, located, decorations: buildDecorations(newState.doc, notes, located, activeId) }
        },
      },
      props: {
        decorations: (state) => coachKey.getState(state)?.decorations,
        handleClick(view, pos) {
          const { located } = coachKey.getState(view.state) || {}
          if (!located) return false
          for (const [id, range] of located) {
            if (pos >= range.from && pos <= range.to) { options.onNoteClick(id); break }
          }
          return false
        },
      },
      view() {
        let lastKey = ''
        return {
          update(view) {
            const state = coachKey.getState(view.state)
            const key = anchorKey(state.located)
            if (key !== lastKey) {
              lastKey = key
              options.onAnchorsChange(new Set(state.located.keys()))
            }
          },
        }
      },
    })]
  },
})

export function setCoachNotes(editor, notes, activeId = null) {
  editor?.view.dispatch(editor.state.tr.setMeta(coachKey, { notes, activeId }).setMeta('addToHistory', false))
}

export function setActiveNote(editor, activeId) {
  editor?.view.dispatch(editor.state.tr.setMeta(coachKey, { activeId }).setMeta('addToHistory', false))
}

export function noteRange(editor, id) {
  return editor ? coachKey.getState(editor.state)?.located.get(id) || null : null
}

// ---------------------------------------------------------------------------
// Focus mode dims every block except the one holding the cursor. The same
// plugin flashes the paragraph the student returns to ("welcome back").
export const blockKey = new PluginKey('focusBlock')

function currentBlock(state) {
  const { $head } = state.selection
  if ($head.depth < 1) return null
  const start = $head.before(1)
  const node = state.doc.nodeAt(start)
  return node ? { from: start, to: start + node.nodeSize } : null
}

export const FocusBlock = Extension.create({
  name: 'focusBlock',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: blockKey,
      state: {
        init: () => ({ focus: false, flash: false }),
        apply(tr, previous) {
          const meta = tr.getMeta(blockKey)
          const next = meta ? { ...previous, ...meta } : previous
          if (next.flash && tr.docChanged) return { ...next, flash: false }
          return next
        },
      },
      props: {
        decorations(state) {
          const mode = blockKey.getState(state)
          if (!mode?.focus && !mode?.flash) return null
          const block = currentBlock(state)
          if (!block) return null
          const className = [mode.focus && 'el-current-block', mode.flash && 'el-flash-block'].filter(Boolean).join(' ')
          return DecorationSet.create(state.doc, [Decoration.node(block.from, block.to, { class: className })])
        },
        attributes: (state) => (blockKey.getState(state)?.focus ? { class: 'is-focus-mode' } : {}),
      },
    })]
  },
})

export function setBlockMode(editor, mode) {
  editor?.view.dispatch(editor.state.tr.setMeta(blockKey, mode).setMeta('addToHistory', false))
}
