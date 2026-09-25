import { useEffect, useId, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { t } from '../i18n.js'
import { nextMenuIndex } from '../lib/menuNavigation.js'

// Up/Down/Home/End move between a menu's items (roving focus, wrapping).
function moveInMenu(event, items) {
  const next = nextMenuIndex(event.key, items.indexOf(document.activeElement), items.length)
  if (next == null) return
  event.preventDefault()
  items[next].focus()
}

const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Modal dialog: focus moves in, Tab stays inside, Esc closes, focus returns on close.
export function Dialog({ title, onClose, children, footer, wide = false, className = '' }) {
  const ref = useRef(null)
  const titleId = useId()
  useEffect(() => {
    const previous = document.activeElement
    const node = ref.current
    const first = node?.querySelector('[data-autofocus]') || node?.querySelector(FOCUSABLE)
    first?.focus()
    return () => { if (previous && typeof previous.focus === 'function') previous.focus() }
  }, [])
  const onKeyDown = (event) => {
    if (event.key === 'Escape') { event.stopPropagation(); onClose() }
    if (event.key !== 'Tab') return
    const items = [...(ref.current?.querySelectorAll(FOCUSABLE) || [])]
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="el-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`el-dialog${wide ? ' is-wide' : ''} ${className}`} onKeyDown={onKeyDown}>
      <div className="el-dialog-head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="el-icon-btn" aria-label={t('Close')} onClick={onClose}><X size={20} /></button>
      </div>
      <div className="el-dialog-body">{children}</div>
      {footer && <div className="el-dialog-foot">{footer}</div>}
    </div>
  </div>
}

// A button that opens a small menu. items: [{ label, onSelect, danger, divider, disabled, hint }]
// A disabled item stays focusable (so arrow keys still reach it) and its hint says why.
export function Menu({ label, icon, items, className = '', align = 'right', buttonClassName = 'el-icon-btn' }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const menuId = useId()
  useEffect(() => {
    if (!open) return undefined
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    root.current?.querySelector('[role="menuitem"]')?.focus()
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  const onKeyDown = (event) => {
    if (event.key === 'Escape') { setOpen(false); root.current?.querySelector('button')?.focus() }
    else if (open) moveInMenu(event, [...(root.current?.querySelectorAll('[role="menuitem"]') || [])])
  }
  return <div className={`el-menu-wrap ${className}`} ref={root} onKeyDown={onKeyDown}>
    <button type="button" className={buttonClassName} aria-label={label} title={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={(event) => { event.stopPropagation(); setOpen((value) => !value) }}>{icon}</button>
    {open && <div role="menu" id={menuId} className={`el-menu align-${align}`}>
      {items.filter(Boolean).map((item, index) => item.divider
        ? <div key={`d${index}`} className="el-menu-divider" role="separator" />
        : <button key={item.label} type="button" role="menuitem" className={item.danger ? 'is-danger' : ''} aria-disabled={item.disabled || undefined}
          title={item.disabled ? item.hint : undefined}
          onClick={(event) => { event.stopPropagation(); if (item.disabled) return; setOpen(false); item.onSelect() }}>
          {item.icon}{item.disabled && item.hint ? <span className="el-menu-text">{item.label}<small>{item.hint}</small></span> : item.label}
        </button>)}
    </div>}
  </div>
}

export function sortFolders(folders) {
  return [...folders].sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.id - b.id)
}

export function folderTree(folders) {
  const sorted = sortFolders(folders)
  const top = sorted.filter((folder) => folder.parent == null)
  return top.map((folder) => ({ ...folder, children: sorted.filter((child) => child.parent === folder.id) }))
}

export function folderPath(folders, id) {
  const folder = folders.find((item) => item.id === id)
  if (!folder) return ''
  const parent = folder.parent != null ? folders.find((item) => item.id === folder.parent) : null
  return parent ? `${parent.name} › ${folder.name}` : folder.name
}

export function FolderSelect({ folders, value, onChange, id }) {
  const tree = folderTree(folders)
  return <select id={id} className="el-input" value={value ?? ''} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : null)}>
    <option value="">{t('No folder')}</option>
    {tree.map((folder) => [
      <option key={folder.id} value={folder.id}>{folder.name}</option>,
      ...folder.children.map((child) => <option key={child.id} value={child.id}>{`${folder.name} › ${child.name}`}</option>),
    ])}
  </select>
}

export function ProgressBar({ ratio, over = false, label }) {
  return <span className={`el-progress${over ? ' is-over' : ''}`} role={label ? 'img' : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
    <span style={{ transform: `scaleX(${Math.max(0, Math.min(1, ratio || 0))})` }} />
  </span>
}

// A button with a small panel of arbitrary content (colour palettes, the font
// size box…). Closes on outside click, Esc and `close()` from the render prop.
// A panel holding a role="menu" list gets the same arrow keys as Menu.
export function Popover({ label, button, className = '', buttonClassName = 'el-tool', panelClassName = '', align = 'left', disabled = false, children }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const panelId = useId()
  useEffect(() => {
    if (!open) return undefined
    const close = (event) => { if (!root.current?.contains(event.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    root.current?.querySelector('[data-autofocus], [role="menuitem"], [role="menuitemradio"], button:not([aria-haspopup]), input')?.focus?.()
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  const close = () => setOpen(false)
  return <div className={`el-menu-wrap ${className}`} ref={root} onKeyDown={(event) => {
    if (!open) return
    if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); root.current?.querySelector('button')?.focus(); return }
    const items = [...(root.current?.querySelectorAll('[role="menu"] [role="menuitem"], [role="menu"] [role="menuitemradio"]') || [])]
    if (items.length) moveInMenu(event, items)
  }}>
    <button type="button" className={buttonClassName} aria-label={label} title={label} aria-haspopup="dialog" aria-expanded={open}
      aria-controls={open ? panelId : undefined} disabled={disabled}
      onMouseDown={(event) => event.preventDefault()}
      onClick={(event) => { event.stopPropagation(); setOpen((value) => !value) }}>{button}</button>
    {open && <div id={panelId} role="dialog" aria-label={label} className={`el-popover align-${align} ${panelClassName}`}>
      {typeof children === 'function' ? children(close) : children}
    </div>}
  </div>
}

// Phone bottom sheet with a grabber; tap outside or Esc closes it.
export function Sheet({ label, onClose, children, className = '' }) {
  const ref = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    ref.current?.querySelector('[data-autofocus], button, input')?.focus()
    return () => { if (previous && typeof previous.focus === 'function') previous.focus() }
  }, [])
  return <div className="el-sheet-layer" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}
    onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); onClose() } }}>
    <div ref={ref} role="dialog" aria-modal="true" aria-label={label} className={`el-sheet ${className}`}>
      <span className="el-sheet-grabber" aria-hidden="true" />
      {children}
    </div>
  </div>
}
