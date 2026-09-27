// Google Docs formatting for the Essay Lab editor: text styles (Title,
// Subtitle, Heading 1-3), fonts, sizes, colours, highlight, alignment, line
// spacing, indent and page breaks.
//
// The saved JSON must pass the server's allowlist exactly (doc.py; the
// frontend mirror is docDelta.js normalizeDoc), so every attribute parses
// pasted HTML into an allowed value or into nothing.
import { Extension, Mark, Node, mergeAttributes } from '@tiptap/react'
import Document from '@tiptap/extension-document'
import { Selection } from '@tiptap/pm/state'
import { FONT_FAMILIES, FONT_SIZE_RANGE, LINE_HEIGHTS, MAX_INDENT, TEXT_ALIGN } from './docDelta.js'
import { DEFAULT_FONT, fontStack, loadFont } from './fonts.js'

export const TEXT_BLOCK_TYPES = ['paragraph', 'heading', 'title', 'subtitle']

// Docs' size menu; the box accepts any whole number in the allowed range.
export const FONT_SIZES = [8, 9, 10, 11, 12, 14, 18, 24, 30, 36, 48, 60, 72, 96]
export const DEFAULT_FONT_SIZE = 11

// Small palettes (Docs-like, readable on the ivory page).
export const TEXT_COLORS = [
  '#000000', '#434343', '#666666', '#999999', '#b91c1c', '#c2410c', '#a16207', '#15803d',
  '#0f766e', '#1d4ed8', '#6d28d9', '#be185d',
]
export const HIGHLIGHT_COLORS = ['#fef08a', '#fde68a', '#bbf7d0', '#bae6fd', '#ddd6fe', '#fbcfe8', '#fed7aa', '#e5e7eb']

// Text styles, in menu order. `node` + attrs is what the block becomes.
export const TEXT_STYLES = [
  { id: 'normal', label: 'Normal text', node: 'paragraph', keys: '0' },
  { id: 'title', label: 'Title', node: 'title' },
  { id: 'subtitle', label: 'Subtitle', node: 'subtitle' },
  { id: 'h1', label: 'Heading 1', node: 'heading', level: 1, keys: '1' },
  { id: 'h2', label: 'Heading 2', node: 'heading', level: 2, keys: '2' },
  { id: 'h3', label: 'Heading 3', node: 'heading', level: 3, keys: '3' },
]

export function styleOf(node) {
  if (!node) return 'normal'
  if (node.type.name === 'heading') return `h${node.attrs.level}`
  if (node.type.name === 'title' || node.type.name === 'subtitle') return node.type.name
  return 'normal'
}

// ---------------------------------------------------------------------------
// Parsing pasted HTML into allowed values (anything else -> null).

const HEX = /^#[0-9a-f]{6}$/i

export function toHex(value) {
  const text = String(value || '').trim().toLowerCase()
  if (HEX.test(text)) return text
  const short = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(text)
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`
  const rgb = /^rgba?\(\s*(\d{1,3})[\s,]+(\d{1,3})[\s,]+(\d{1,3})(?:[\s,/]+([\d.]+%?))?\s*\)$/.exec(text)
  if (!rgb) return null
  if (rgb[4] !== undefined && parseFloat(rgb[4]) === 0) return null // transparent
  const parts = rgb.slice(1, 4).map(Number)
  if (parts.some((part) => part > 255)) return null
  return `#${parts.map((part) => part.toString(16).padStart(2, '0')).join('')}`
}

export function toFontFamily(value) {
  const names = String(value || '').split(',').map((name) => name.trim().replace(/^['"]|['"]$/g, '').replace(/ Variable$/, ''))
  return FONT_FAMILIES.find((family) => names[0]?.toLowerCase() === family.toLowerCase()) || null
}

export function clampFontSize(value) {
  const size = Math.round(Number(value))
  if (!Number.isFinite(size)) return null
  return Math.min(FONT_SIZE_RANGE[1], Math.max(FONT_SIZE_RANGE[0], size))
}

export function toFontSize(value) {
  const match = /^([\d.]+)(pt|px)$/.exec(String(value || '').trim())
  if (!match) return null
  const points = match[2] === 'px' ? parseFloat(match[1]) * 0.75 : parseFloat(match[1])
  return clampFontSize(points)
}

// Sizes are points scaled by --el-pt (1pt on a page; larger in pageless view),
// so text keeps its proportions in both views.
const sizeCss = (size) => `calc(var(--el-pt, 1pt) * ${size})`

// ---------------------------------------------------------------------------
// Nodes

// The page break sits between top-level blocks only (as on the server).
export const EssayDocument = Document.extend({ content: '(block | pageBreak)+' })

function textStyleNode(name, tag, className) {
  return Node.create({
    name,
    group: 'block',
    content: 'inline*',
    defining: true,
    parseHTML: () => [{ tag: `${tag}.${className}` }, { tag: `[data-type="${name}"]`, priority: 60 }],
    renderHTML: ({ HTMLAttributes }) => [tag, mergeAttributes(HTMLAttributes, { class: className, 'data-type': name }), 0],
  })
}

export const Title = textStyleNode('title', 'p', 'el-title')
export const Subtitle = textStyleNode('subtitle', 'p', 'el-subtitle')

export const PageBreak = Node.create({
  name: 'pageBreak',
  atom: true,
  selectable: true,
  draggable: false,
  parseHTML: () => [{ tag: 'div[data-type="page-break"]' }, { tag: 'hr.el-page-break' }],
  renderHTML: () => ['div', { 'data-type': 'page-break', class: 'el-page-break', contenteditable: 'false' }],
})

// ---------------------------------------------------------------------------
// Marks

export const TextStyle = Mark.create({
  name: 'textStyle',
  priority: 101,
  addAttributes() {
    return {
      fontFamily: {
        default: null,
        parseHTML: (element) => toFontFamily(element.style.fontFamily),
        renderHTML: ({ fontFamily }) => (fontFamily && fontStack(fontFamily) ? { style: `font-family: ${fontStack(fontFamily)}` } : {}),
      },
      fontSize: {
        default: null,
        parseHTML: (element) => toFontSize(element.style.fontSize),
        renderHTML: ({ fontSize }) => (fontSize ? { style: `font-size: ${sizeCss(fontSize)}` } : {}),
      },
      color: {
        default: null,
        parseHTML: (element) => toHex(element.style.color),
        renderHTML: ({ color }) => (color ? { style: `color: ${color}` } : {}),
      },
    }
  },
  parseHTML: () => [{
    tag: 'span',
    getAttrs: (element) => (element.style.fontFamily || element.style.fontSize || element.style.color ? {} : false),
  }],
  renderHTML: ({ HTMLAttributes }) => ['span', HTMLAttributes, 0],
  addCommands() {
    const set = (attrs) => ({ chain }) => chain().setMark(this.name, attrs).removeEmptyTextStyle().run()
    return {
      setFontFamily: (fontFamily) => { loadFont(fontFamily); return set({ fontFamily: fontFamily === DEFAULT_FONT ? null : fontFamily }) },
      setFontSize: (fontSize) => set({ fontSize: fontSize === DEFAULT_FONT_SIZE ? null : clampFontSize(fontSize) }),
      setColor: (color) => set({ color: color ? toHex(color) : null }),
      removeEmptyTextStyle: () => ({ state, tr, dispatch }) => {
        const type = state.schema.marks.textStyle
        const { from, to, empty } = state.selection
        if (empty) {
          const mark = (state.storedMarks || state.selection.$from.marks()).find((item) => item.type === type)
          if (mark && Object.values(mark.attrs).every((value) => value == null) && dispatch) tr.removeStoredMark(type)
          return true
        }
        state.doc.nodesBetween(from, to, (node, pos) => {
          const mark = node.isText && node.marks.find((item) => item.type === type)
          if (mark && Object.values(mark.attrs).every((value) => value == null)) {
            tr.removeMark(Math.max(pos, from), Math.min(pos + node.nodeSize, to), type)
          }
        })
        return true
      },
    }
  },
})

export const Highlight = Mark.create({
  name: 'highlight',
  addAttributes() {
    return {
      color: {
        default: null,
        parseHTML: (element) => toHex(element.getAttribute('data-color') || element.style.backgroundColor),
        renderHTML: ({ color }) => (color ? { 'data-color': color, style: `background-color: ${color}` } : {}),
      },
    }
  },
  parseHTML: () => [{ tag: 'mark' }, {
    tag: 'span',
    getAttrs: (element) => (toHex(element.style.backgroundColor) ? {} : false),
  }],
  renderHTML: ({ HTMLAttributes }) => ['mark', mergeAttributes(HTMLAttributes, { class: 'el-highlight' }), 0],
  addCommands() {
    return {
      setHighlight: (color) => ({ commands }) => (color ? commands.setMark(this.name, { color: toHex(color) }) : commands.unsetMark(this.name)),
    }
  },
})

// ---------------------------------------------------------------------------
// Block formatting: alignment, line spacing and indent on every text block.

function blockFormatAttr(name, parse, render) {
  return { default: null, parseHTML: parse, renderHTML: (attrs) => (attrs[name] != null ? render(attrs[name]) : {}) }
}

export const BlockFormat = Extension.create({
  name: 'blockFormat',
  // Before StarterKit's heading shortcuts, which toggle instead of set.
  priority: 200,
  addGlobalAttributes() {
    return [{
      types: TEXT_BLOCK_TYPES,
      attributes: {
        textAlign: blockFormatAttr('textAlign', (element) => {
          const value = element.style.textAlign
          return TEXT_ALIGN.has(value) ? value : null
        }, (value) => ({ style: `text-align: ${value}` })),
        lineHeight: blockFormatAttr('lineHeight', (element) => {
          const value = String(parseFloat(element.style.lineHeight))
          return LINE_HEIGHTS.includes(value) ? value : null
        }, (value) => ({ style: `line-height: ${value}` })),
        indent: blockFormatAttr('indent', (element) => {
          const value = Number(element.getAttribute('data-indent'))
          return Number.isInteger(value) && value > 0 && value <= MAX_INDENT ? value : null
        }, (value) => ({ 'data-indent': value, style: `margin-left: calc(var(--el-pt, 1pt) * ${36 * value})` })),
      },
    }]
  },
  addCommands() {
    const update = (change) => ({ state, tr, dispatch }) => {
      const { from, to } = state.selection
      let changed = false
      state.doc.nodesBetween(from, to, (node, pos) => {
        if (!TEXT_BLOCK_TYPES.includes(node.type.name)) return true
        const next = change(node.attrs)
        if (next) {
          tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...next })
          changed = true
        }
        return false
      })
      if (changed && dispatch) dispatch(tr)
      return changed
    }
    return {
      setTextAlign: (align) => update(() => ({ textAlign: align === 'left' || !TEXT_ALIGN.has(align) ? null : align })),
      setLineHeight: (value) => update(() => ({ lineHeight: LINE_HEIGHTS.includes(value) ? value : null })),
      // In a list, indent nests the item (like Docs); elsewhere the paragraph moves.
      indentBlock: () => (props) => {
        if (props.editor.isActive('listItem')) return props.commands.sinkListItem('listItem')
        return update((attrs) => ((attrs.indent || 0) < MAX_INDENT ? { indent: (attrs.indent || 0) + 1 } : null))(props)
      },
      outdentBlock: () => (props) => {
        if (props.editor.isActive('listItem')) return props.commands.liftListItem('listItem')
        return update((attrs) => (attrs.indent ? { indent: attrs.indent > 1 ? attrs.indent - 1 : null } : null))(props)
      },
      // Normal text / Title / Subtitle / Heading 1-3, keeping alignment, spacing and indent.
      setTextStyle: (id) => ({ state, tr, dispatch }) => {
        const style = TEXT_STYLES.find((item) => item.id === id)
        if (!style) return false
        const type = state.schema.nodes[style.node]
        const { from, to } = state.selection
        let changed = false
        state.doc.nodesBetween(from, to, (node, pos) => {
          if (!node.isTextblock) return true
          const $pos = state.doc.resolve(pos)
          const index = $pos.index()
          if (!$pos.parent.canReplaceWith(index, index + 1, type)) return false
          const { textAlign, lineHeight, indent } = node.attrs
          const attrs = { textAlign: textAlign ?? null, lineHeight: lineHeight ?? null, indent: indent ?? null }
          if (style.level) attrs.level = style.level
          tr.setNodeMarkup(pos, type, attrs)
          changed = true
          return false
        })
        if (changed && dispatch) dispatch(tr.scrollIntoView())
        return changed
      },
      // Like Docs: split the block at the cursor and start the rest on a new page.
      insertPageBreak: () => ({ state, tr, dispatch }) => {
        if (!dispatch) return true
        const { schema } = state
        const { $to } = state.selection
        const topLevel = $to.depth === 1 && $to.parent.isTextblock
        const atStart = topLevel && $to.parentOffset === 0
        const atEnd = topLevel && $to.parentOffset === $to.parent.content.size
        let between
        if (topLevel && !atStart && !atEnd) {
          tr.split($to.pos)
          between = $to.pos + 1
        } else if (atStart && !atEnd) {
          between = $to.before(1)
        } else {
          between = $to.after(1)
        }
        tr.insert(between, schema.nodes.pageBreak.create())
        if (!topLevel || atEnd) tr.insert(between + 1, schema.nodes.paragraph.create())
        tr.setSelection(Selection.near(tr.doc.resolve(between + 2)))
        dispatch(tr.scrollIntoView())
        return true
      },
    }
  },
  addKeyboardShortcuts() {
    const shortcuts = {
      'Mod-Enter': () => this.editor.commands.insertPageBreak(),
      'Mod-]': () => this.editor.commands.indentBlock(),
      'Mod-[': () => this.editor.commands.outdentBlock(),
      'Mod-Shift-l': () => this.editor.commands.setTextAlign('left'),
      'Mod-Shift-e': () => this.editor.commands.setTextAlign('center'),
      'Mod-Shift-r': () => this.editor.commands.setTextAlign('right'),
      'Mod-Shift-j': () => this.editor.commands.setTextAlign('justify'),
    }
    for (const style of TEXT_STYLES) {
      if (style.keys) shortcuts[`Mod-Alt-${style.keys}`] = () => this.editor.commands.setTextStyle(style.id)
    }
    return shortcuts
  },
})
