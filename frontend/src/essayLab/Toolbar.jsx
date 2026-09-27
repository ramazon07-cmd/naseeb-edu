import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useEditorState } from '@tiptap/react'
import {
  AlignCenter, AlignJustify, AlignLeft, AlignRight, Baseline, Bold, Check, ChevronDown, Highlighter, IndentDecrease,
  IndentIncrease, Italic, Link2, List, ListOrdered, Minus, MoreHorizontal, Plus, Redo2, RemoveFormatting, SeparatorHorizontal,
  Strikethrough, TextQuote, Type, Underline, Undo2, UnfoldVertical,
} from 'lucide-react'
import { t } from '../i18n.js'
import { Popover, Sheet } from './ui.jsx'
import { FONTS, DEFAULT_FONT, fontStack } from './fonts.js'
import {
  DEFAULT_FONT_SIZE, FONT_SIZES, HIGHLIGHT_COLORS, TEXT_COLORS, TEXT_STYLES, clampFontSize, styleOf,
} from './formatting.js'
import { LINE_HEIGHTS, normalizeHref } from './docDelta.js'
import { fitGroups } from './toolbarLayout.js'

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '')
const mod = isMac ? '⌘' : 'Ctrl+'
const shift = isMac ? '⇧' : 'Shift+'
const alt = isMac ? '⌥' : 'Alt+'

const ALIGNS = [
  { id: 'left', label: 'Left align', icon: AlignLeft, keys: `${mod}${shift}L` },
  { id: 'center', label: 'Center align', icon: AlignCenter, keys: `${mod}${shift}E` },
  { id: 'right', label: 'Right align', icon: AlignRight, keys: `${mod}${shift}R` },
  { id: 'justify', label: 'Justify', icon: AlignJustify, keys: `${mod}${shift}J` },
]
const SPACING_LABELS = { 1: 'Single', 1.15: '1.15', 1.5: '1.5', 2: 'Double' }

// Active state is read through one selector, so the toolbar re-renders only
// when something it shows actually changes — never on every keystroke.
function selectState(editor) {
  if (!editor || editor.isDestroyed) return null
  const { $from } = editor.state.selection
  const block = $from.depth ? $from.node($from.depth) : null
  const textStyle = editor.getAttributes('textStyle')
  return {
    style: styleOf(block?.isTextblock ? block : null),
    fontFamily: textStyle.fontFamily || DEFAULT_FONT,
    fontSize: textStyle.fontSize || DEFAULT_FONT_SIZE,
    color: textStyle.color || null,
    highlight: editor.getAttributes('highlight').color || null,
    align: block?.attrs?.textAlign || 'left',
    lineHeight: block?.attrs?.lineHeight || null,
    bold: editor.isActive('bold'),
    italic: editor.isActive('italic'),
    underline: editor.isActive('underline'),
    strike: editor.isActive('strike'),
    link: editor.isActive('link'),
    bullet: editor.isActive('bulletList') && !editor.isActive('bulletList', { style: 'dash' }),
    dash: editor.isActive('bulletList', { style: 'dash' }),
    ordered: editor.isActive('orderedList'),
    quote: editor.isActive('blockquote'),
    canUndo: editor.can().undo(),
    canRedo: editor.can().redo(),
  }
}

// The selector reads the editor passed in, not the store's snapshot: the store
// only notices a new editor (another tab opened) at its next transaction.
function useToolbarState(editor) {
  const selector = useCallback(() => selectState(editor), [editor])
  return useEditorState({ editor, selector })
}

// Keep the selection in the page: toolbar buttons never take focus on mouse down.
const keepFocus = (event) => event.preventDefault()

function Tool({ label, keys, icon: Icon, pressed, disabled, onClick, className = '' }) {
  const text = t(label)
  return <button type="button" className={`el-tool${pressed ? ' is-on' : ''} ${className}`} aria-label={text} aria-pressed={pressed}
    title={keys ? `${text} (${keys})` : text} disabled={disabled} onMouseDown={keepFocus} onClick={onClick}>
    <Icon size={18} strokeWidth={2} aria-hidden="true" />
  </button>
}

const run = (editor, fn) => fn(editor.chain().focus()).run()

// ---------------------------------------------------------------------------
// Controls (each used in the bar, the overflow panel and the phone sheet)

function StyleMenu({ editor, state, disabled }) {
  const current = TEXT_STYLES.find((style) => style.id === state.style) || TEXT_STYLES[0]
  return <Popover label={t('Text style')} disabled={disabled} buttonClassName="el-tool is-select is-style" panelClassName="el-style-menu"
    button={<><span>{t(current.label)}</span><ChevronDown size={14} aria-hidden="true" /></>}>
    {(close) => <div role="menu">
      {TEXT_STYLES.map((style) => <button key={style.id} type="button" role="menuitemradio" aria-checked={style.id === state.style}
        className={`el-style-option is-${style.id}`} onMouseDown={keepFocus}
        onClick={() => { run(editor, (c) => c.setTextStyle(style.id)); close() }}>
        <span>{t(style.label)}</span>{style.keys && <kbd>{`${mod}${alt}${style.keys}`}</kbd>}
      </button>)}
    </div>}
  </Popover>
}

function FontMenu({ editor, state, disabled }) {
  return <Popover label={t('Font')} disabled={disabled} buttonClassName="el-tool is-select is-font" panelClassName="el-font-menu"
    button={<><span style={{ fontFamily: fontStack(state.fontFamily) }}>{state.fontFamily}</span><ChevronDown size={14} aria-hidden="true" /></>}>
    {(close) => <div role="menu">
      {FONTS.map((font) => <button key={font.name} type="button" role="menuitemradio" aria-checked={font.name === state.fontFamily}
        style={{ fontFamily: font.stack }} onMouseDown={keepFocus}
        onClick={() => { run(editor, (c) => c.setFontFamily(font.name)); close() }}>
        {font.name === state.fontFamily ? <Check size={14} aria-hidden="true" /> : <span className="el-check-space" />}{font.name}
      </button>)}
    </div>}
  </Popover>
}

function FontSize({ editor, state, disabled }) {
  const [draft, setDraft] = useState(String(state.fontSize))
  useEffect(() => { setDraft(String(state.fontSize)) }, [state.fontSize])
  // Enter and the +/- buttons return to the text; leaving the box (Tab, a
  // click elsewhere) applies the size without taking focus back.
  const apply = (size, { focus = true } = {}) => {
    const value = clampFontSize(size)
    if (value == null) { setDraft(String(state.fontSize)); return }
    if (focus) run(editor, (c) => c.setFontSize(value))
    else editor.chain().setFontSize(value).run()
  }
  const step = (direction) => {
    const current = state.fontSize
    const next = direction > 0 ? FONT_SIZES.find((size) => size > current) ?? current : [...FONT_SIZES].reverse().find((size) => size < current) ?? current
    apply(next)
  }
  return <div className="el-size" role="group" aria-label={t('Font size')}>
    <button type="button" className="el-tool is-small" aria-label={t('Decrease font size')} title={t('Decrease font size')} disabled={disabled}
      onMouseDown={keepFocus} onClick={() => step(-1)}><Minus size={15} aria-hidden="true" /></button>
    <input className="el-size-input" inputMode="numeric" aria-label={t('Font size')} value={draft} disabled={disabled}
      onChange={(event) => setDraft(event.target.value.replace(/[^0-9]/g, '').slice(0, 2))}
      onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); apply(draft) } if (event.key === 'Escape') setDraft(String(state.fontSize)) }}
      onBlur={() => { if (draft !== String(state.fontSize)) apply(draft, { focus: false }) }} />
    <button type="button" className="el-tool is-small" aria-label={t('Increase font size')} title={t('Increase font size')} disabled={disabled}
      onMouseDown={keepFocus} onClick={() => step(1)}><Plus size={15} aria-hidden="true" /></button>
  </div>
}

function Palette({ colors, value, onPick, resetLabel }) {
  return <div className="el-palette">
    <div className="el-swatches">
      {colors.map((color) => <button key={color} type="button" className={`el-swatch${value === color ? ' is-on' : ''}`} style={{ background: color }}
        aria-label={color} title={color} aria-pressed={value === color} onMouseDown={keepFocus} onClick={() => onPick(color)} />)}
    </div>
    <button type="button" className="el-btn is-small" onMouseDown={keepFocus} onClick={() => onPick(null)}>{resetLabel}</button>
  </div>
}

function ColorTools({ editor, state, disabled }) {
  return <>
    <Popover label={t('Text color')} disabled={disabled} button={<span className="el-color-icon"><Baseline size={18} aria-hidden="true" /><i style={{ background: state.color || 'currentColor' }} /></span>}>
      {(close) => <Palette colors={TEXT_COLORS} value={state.color} resetLabel={t('Default color')}
        onPick={(color) => { run(editor, (c) => c.setColor(color)); close() }} />}
    </Popover>
    <Popover label={t('Highlight color')} disabled={disabled} button={<span className="el-color-icon"><Highlighter size={18} aria-hidden="true" /><i style={{ background: state.highlight || 'transparent' }} /></span>}>
      {(close) => <Palette colors={HIGHLIGHT_COLORS} value={state.highlight} resetLabel={t('No highlight')}
        onPick={(color) => { run(editor, (c) => c.setHighlight(color)); close() }} />}
    </Popover>
  </>
}

function LinkTool({ editor, state, disabled }) {
  return <Popover label={t('Insert link')} disabled={disabled} button={<Link2 size={18} aria-hidden="true" />} panelClassName="el-link-panel">
    {(close) => <LinkForm editor={editor} active={state.link} close={close} />}
  </Popover>
}

function LinkForm({ editor, active, close }) {
  const [value, setValue] = useState(() => editor.getAttributes('link').href || '')
  const [error, setError] = useState(false)
  const submit = (event) => {
    event.preventDefault()
    const href = normalizeHref(value)
    if (!href) { setError(true); return }
    const chain = editor.chain().focus().extendMarkRange('link')
    if (editor.state.selection.empty && !active) chain.insertContent({ type: 'text', text: value.trim(), marks: [{ type: 'link', attrs: { href } }] })
    else chain.setLink({ href })
    chain.run()
    close()
  }
  return <form className="el-link-form" onSubmit={submit}>
    <label className="el-label" htmlFor="el-link-input">{t('Link')}</label>
    <input id="el-link-input" data-autofocus className="el-input is-small" value={value} placeholder="https://" aria-invalid={error}
      onChange={(event) => { setValue(event.target.value); setError(false) }} />
    {error && <span className="el-small is-error">{t('Use a web address (https://…) or an email.')}</span>}
    <div className="el-note-actions">
      <button type="submit" className="el-btn is-small is-primary">{t('Apply')}</button>
      {active && <button type="button" className="el-btn is-small" onClick={() => { editor.chain().focus().extendMarkRange('link').unsetLink().run(); close() }}>{t('Remove link')}</button>}
    </div>
  </form>
}

function AlignTools({ editor, state, disabled, compact }) {
  if (compact) {
    const current = ALIGNS.find((item) => item.id === state.align) || ALIGNS[0]
    const Icon = current.icon
    return <Popover label={t('Align')} disabled={disabled} button={<><Icon size={18} aria-hidden="true" /><ChevronDown size={12} aria-hidden="true" /></>} buttonClassName="el-tool is-wide">
      {(close) => <div className="el-tool-row">{ALIGNS.map((item) => <Tool key={item.id} {...item} pressed={state.align === item.id} disabled={disabled}
        onClick={() => { run(editor, (c) => c.setTextAlign(item.id)); close() }} />)}</div>}
    </Popover>
  }
  return ALIGNS.map((item) => <Tool key={item.id} {...item} pressed={state.align === item.id} disabled={disabled}
    onClick={() => run(editor, (c) => c.setTextAlign(item.id))} />)
}

function SpacingMenu({ editor, state, disabled }) {
  return <Popover label={t('Line spacing')} disabled={disabled} button={<UnfoldVertical size={18} aria-hidden="true" />}>
    {(close) => <div role="menu">
      {LINE_HEIGHTS.map((value) => <button key={value} type="button" role="menuitemradio" aria-checked={state.lineHeight === value} onMouseDown={keepFocus}
        onClick={() => { run(editor, (c) => c.setLineHeight(value)); close() }}>
        {state.lineHeight === value ? <Check size={14} aria-hidden="true" /> : <span className="el-check-space" />}{t(SPACING_LABELS[value])}
      </button>)}
    </div>}
  </Popover>
}

// Groups in the order they give way when the bar gets narrow (last first).
const GROUPS = [
  { id: 'history', width: 76, render: ({ editor, state, disabled }) => <>
    <Tool label="Undo" keys={`${mod}Z`} icon={Undo2} disabled={disabled || !state.canUndo} onClick={() => run(editor, (c) => c.undo())} />
    <Tool label="Redo" keys={isMac ? `${mod}${shift}Z` : `${mod}Y`} icon={Redo2} disabled={disabled || !state.canRedo} onClick={() => run(editor, (c) => c.redo())} />
  </> },
  { id: 'style', width: 150, render: (props) => <StyleMenu {...props} /> },
  { id: 'font', width: 150, render: (props) => <FontMenu {...props} /> },
  { id: 'size', width: 116, render: (props) => <FontSize {...props} /> },
  { id: 'marks', width: 150, render: ({ editor, state, disabled }) => <>
    <Tool label="Bold" keys={`${mod}B`} icon={Bold} pressed={state.bold} disabled={disabled} onClick={() => run(editor, (c) => c.toggleBold())} />
    <Tool label="Italic" keys={`${mod}I`} icon={Italic} pressed={state.italic} disabled={disabled} onClick={() => run(editor, (c) => c.toggleItalic())} />
    <Tool label="Underline" keys={`${mod}U`} icon={Underline} pressed={state.underline} disabled={disabled} onClick={() => run(editor, (c) => c.toggleUnderline())} />
    <Tool label="Strikethrough" keys={`${mod}${shift}S`} icon={Strikethrough} pressed={state.strike} disabled={disabled} onClick={() => run(editor, (c) => c.toggleStrike())} />
  </> },
  { id: 'color', width: 76, render: (props) => <ColorTools {...props} /> },
  { id: 'link', width: 40, render: (props) => <LinkTool {...props} /> },
  { id: 'align', width: 152, compactWidth: 56, render: (props) => <AlignTools {...props} /> },
  { id: 'spacing', width: 40, render: (props) => <SpacingMenu {...props} /> },
  { id: 'lists', width: 114, render: ({ editor, state, disabled }) => <>
    <Tool label="Bulleted list" keys={`${mod}${shift}8`} icon={List} pressed={state.bullet} disabled={disabled} onClick={() => run(editor, (c) => c.togglePlainBulletList())} />
    <Tool label="Numbered list" keys={`${mod}${shift}7`} icon={ListOrdered} pressed={state.ordered} disabled={disabled} onClick={() => run(editor, (c) => c.toggleOrderedList())} />
    <Tool label="Dash list" keys={`${mod}${shift}9`} icon={Minus} pressed={state.dash} disabled={disabled} onClick={() => run(editor, (c) => c.toggleDashList())} />
  </> },
  { id: 'indent', width: 76, render: ({ editor, disabled }) => <>
    <Tool label="Decrease indent" keys={`${mod}[`} icon={IndentDecrease} disabled={disabled} onClick={() => run(editor, (c) => c.outdentBlock())} />
    <Tool label="Increase indent" keys={`${mod}]`} icon={IndentIncrease} disabled={disabled} onClick={() => run(editor, (c) => c.indentBlock())} />
  </> },
  { id: 'insert', width: 114, render: ({ editor, state, disabled }) => <>
    <Tool label="Block quote" keys={`${mod}${shift}B`} icon={TextQuote} pressed={state.quote} disabled={disabled} onClick={() => run(editor, (c) => c.toggleBlockquote())} />
    <Tool label="Page break" keys={`${mod}Enter`} icon={SeparatorHorizontal} disabled={disabled} onClick={() => run(editor, (c) => c.insertPageBreak())} />
    <Tool label="Clear formatting" keys={`${mod}\\`} icon={RemoveFormatting} disabled={disabled}
      onClick={() => run(editor, (c) => c.unsetAllMarks().clearNodes().setTextAlign('left').setLineHeight(null))} />
  </> },
]
function Toolbar({ editor, disabled = false }) {
  const state = useToolbarState(editor)
  const ref = useRef(null)
  const [visible, setVisible] = useState(GROUPS.length)
  useLayoutEffect(() => {
    const node = ref.current?.parentElement
    if (!node) return undefined
    const update = () => setVisible(fitGroups(node.clientWidth - 24, GROUPS))
    update()
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : null
    observer?.observe(node)
    return () => observer?.disconnect()
  }, [])
  if (!editor || !state) return <div ref={ref} className="el-toolbar" />
  const props = { editor, state, disabled }
  const shown = GROUPS.slice(0, visible)
  const hidden = GROUPS.slice(visible)
  return <div ref={ref} className="el-toolbar" role="toolbar" aria-label={t('Formatting')}>
    {shown.map((group) => <div key={group.id} className={`el-tool-group is-${group.id}`}>{group.render(props)}</div>)}
    {hidden.length > 0 && <Popover label={t('More formatting')} button={<MoreHorizontal size={18} aria-hidden="true" />} align="right" panelClassName="el-toolbar-more">
      {hidden.map((group) => <div key={group.id} className={`el-tool-group is-${group.id}`}>{group.render({ ...props, compact: true })}</div>)}
    </Popover>}
  </div>
}

export default memo(Toolbar)

// Phone: a compact bar with the everyday tools; "Aa" opens every option in a sheet.
export const CompactToolbar = memo(function CompactToolbar({ editor, disabled = false, count }) {
  const state = useToolbarState(editor)
  const [sheet, setSheet] = useState(false)
  if (!editor || !state) return null
  const props = { editor, state, disabled }
  return <div className="el-compact-bar" role="toolbar" aria-label={t('Formatting')}>
    <button type="button" className="el-tool is-aa" aria-label={t('Text formatting')} aria-haspopup="dialog" aria-expanded={sheet} disabled={disabled}
      onMouseDown={keepFocus} onClick={() => setSheet(true)}><Type size={18} aria-hidden="true" /><span aria-hidden="true">Aa</span></button>
    <Tool label="Bold" icon={Bold} pressed={state.bold} disabled={disabled} onClick={() => run(editor, (c) => c.toggleBold())} />
    <Tool label="Italic" icon={Italic} pressed={state.italic} disabled={disabled} onClick={() => run(editor, (c) => c.toggleItalic())} />
    <Tool label="Underline" icon={Underline} pressed={state.underline} disabled={disabled} onClick={() => run(editor, (c) => c.toggleUnderline())} />
    <Tool label="Bulleted list" icon={List} pressed={state.bullet} disabled={disabled} onClick={() => run(editor, (c) => c.togglePlainBulletList())} />
    <Tool label="Undo" icon={Undo2} disabled={disabled || !state.canUndo} onClick={() => run(editor, (c) => c.undo())} />
    <span className="el-compact-count">{count}</span>
    {sheet && <Sheet label={t('Text formatting')} onClose={() => setSheet(false)} className="el-format-sheet">
      <div className="el-sheet-section">
        <span className="el-sheet-title">{t('Text style')}</span>
        <div className="el-style-chips">
          {TEXT_STYLES.map((style) => <button key={style.id} type="button" className={`el-chip is-${style.id}${state.style === style.id ? ' is-on' : ''}`}
            aria-pressed={state.style === style.id} onMouseDown={keepFocus} onClick={() => run(editor, (c) => c.setTextStyle(style.id))}>{t(style.label)}</button>)}
        </div>
      </div>
      {GROUPS.filter((group) => group.id !== 'style' && group.id !== 'history').map((group) => <div key={group.id} className={`el-sheet-section el-tool-group is-${group.id}`}>
        {group.render({ ...props, compact: false })}
      </div>)}
      <button type="button" className="el-btn is-primary el-sheet-done" onClick={() => setSheet(false)}>{t('Done')}</button>
    </Sheet>}
  </div>
})

export const TOOLBAR_GROUPS = GROUPS
