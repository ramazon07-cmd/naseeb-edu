import { memo, useEffect, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight, Copy, CornerDownRight, FileText, MoreVertical, PenLine, Plus, Trash2 } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { Dialog, Menu, Sheet } from './ui.jsx'
import { MAX_TABS, canDeleteTab, movedOrder, siblingsOf, tabTree } from './tabsModel.js'

const DRAG_TYPE = 'application/x-naseeb-essay-tab'

function TabRow({ tab, depth, active, hasChildren, expanded, onToggle, actions, renaming, onRenamed, dragProps, sheet, deletable }) {
  const inputRef = useRef(null)
  const [draft, setDraft] = useState(tab.title)
  useEffect(() => {
    if (!renaming) return
    setDraft(tab.title)
    window.requestAnimationFrame(() => inputRef.current?.select())
  }, [renaming, tab.title])
  const finish = (save) => onRenamed(save && draft.trim() && draft.trim() !== tab.title ? draft.trim().slice(0, 100) : null)
  return <div className={`el-tab-row${active ? ' is-active' : ''}${sheet ? ' is-sheet' : ''}`} style={{ '--el-tab-depth': depth }} {...dragProps}>
    {hasChildren
      ? <button type="button" className="el-tab-caret" aria-label={expanded ? t('Hide sub-tabs') : t('Show sub-tabs')} aria-expanded={expanded} onClick={onToggle}>
        {expanded ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
      </button>
      : <span className="el-tab-caret" aria-hidden="true" />}
    {renaming
      ? <input ref={inputRef} className="el-tab-rename" aria-label={t('Tab name')} value={draft} maxLength={100}
        onChange={(event) => setDraft(event.target.value)} onBlur={() => finish(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') { event.preventDefault(); finish(true) }
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false) }
        }} />
      : <button type="button" className="el-tab-name" aria-current={active ? 'page' : undefined} onClick={actions.open}
        onDoubleClick={actions.rename} title={tab.title}>
        <FileText size={16} aria-hidden="true" /><span>{tab.title}</span>
      </button>}
    {!renaming && <Menu className="el-tab-menu" label={t('Tab options for {title}', { title: tab.title })} icon={<MoreVertical size={16} />} items={[
      { label: t('Rename'), icon: <PenLine size={15} />, onSelect: actions.rename },
      depth === 0 && { label: t('Add sub-tab'), icon: <CornerDownRight size={15} />, onSelect: actions.addChild },
      { label: t('Duplicate'), icon: <Copy size={15} />, onSelect: actions.duplicate },
      { label: t('Move up'), icon: <ArrowUp size={15} />, onSelect: actions.moveUp },
      { label: t('Move down'), icon: <ArrowDown size={15} />, onSelect: actions.moveDown },
      { divider: true },
      { label: t('Delete'), icon: <Trash2 size={15} />, danger: true, disabled: !deletable, hint: t('A document needs at least one tab.'), onSelect: actions.remove },
    ]} />}
  </div>
}

// The list shared by the desktop rail and the phone sheet.
function TabList({ tabs, activeId, outline, busy, onOpen, onAdd, onRename, onDuplicate, onReorder, onDelete, onOutline, sheet = false }) {
  const [collapsed, setCollapsed] = useState(() => new Set())
  const [renaming, setRenaming] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const [dragging, setDragging] = useState(null)
  const tree = tabTree(tabs)
  const activeParent = tabs.find((tab) => tab.id === activeId)?.parent ?? null

  const toggle = (id) => setCollapsed((current) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  })

  const move = (tab, offset) => {
    const ids = movedOrder(tabs, tab, offset)
    if (ids) onReorder(tab.parent ?? null, ids)
  }

  const dragPropsFor = (tab) => sheet ? {} : {
    draggable: renaming !== tab.id,
    onDragStart: (event) => { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData(DRAG_TYPE, String(tab.id)); setDragging(tab) },
    onDragEnd: () => setDragging(null),
    onDragOver: (event) => {
      if (dragging && dragging.id !== tab.id && (dragging.parent ?? null) === (tab.parent ?? null)) { event.preventDefault(); event.dataTransfer.dropEffect = 'move' }
    },
    onDrop: (event) => {
      event.preventDefault()
      if (!dragging || dragging.id === tab.id || (dragging.parent ?? null) !== (tab.parent ?? null)) return
      const ids = siblingsOf(tabs, tab).map((item) => item.id).filter((id) => id !== dragging.id)
      ids.splice(ids.indexOf(tab.id), 0, dragging.id)
      setDragging(null)
      onReorder(tab.parent ?? null, ids)
    },
  }

  const row = (tab, depth, hasChildren) => {
    const expanded = hasChildren && (!collapsed.has(tab.id) || activeParent === tab.id)
    return <div key={tab.id} className="el-tab-item">
      <TabRow tab={tab} depth={depth} active={tab.id === activeId} hasChildren={hasChildren} expanded={expanded} sheet={sheet} deletable={canDeleteTab(tabs, tab)}
        onToggle={() => toggle(tab.id)} renaming={renaming === tab.id} dragProps={dragPropsFor(tab)}
        onRenamed={(title) => { setRenaming(null); if (title) onRename(tab, title) }}
        actions={{
          open: () => onOpen(tab.id),
          rename: () => setRenaming(tab.id),
          addChild: () => onAdd(tab.id),
          duplicate: () => onDuplicate(tab),
          moveUp: () => move(tab, -1),
          moveDown: () => move(tab, 1),
          remove: () => setConfirm(tab),
        }} />
      {tab.id === activeId && !sheet && outline.length > 0 && <ul className="el-outline" aria-label={t('Outline')} style={{ '--el-tab-depth': depth }}>
        {outline.map((item) => <li key={item.pos}>
          <button type="button" className={`el-outline-item is-${item.kind}`} onClick={() => onOutline(item)}>{item.text}</button>
        </li>)}
      </ul>}
    </div>
  }

  const children = tabs.filter((tab) => tab.parent === confirm?.id).length
  return <>
    <div className="el-tab-list" role="list">
      {tree.map(({ tab, children: kids }) => <div key={tab.id} role="listitem">
        {row(tab, 0, kids.length > 0)}
        {kids.length > 0 && (!collapsed.has(tab.id) || activeParent === tab.id) && kids.map((kid) => row(kid, 1, false))}
      </div>)}
    </div>
    {confirm && <Dialog title={t('Delete “{name}”?', { name: confirm.title })} onClose={() => setConfirm(null)} footer={<>
      <button type="button" className="el-btn" data-autofocus onClick={() => setConfirm(null)}>{t('Cancel')}</button>
      <button type="button" className="el-btn is-danger-solid" disabled={busy} onClick={() => { const tab = confirm; setConfirm(null); onDelete(tab) }}>
        <Trash2 size={16} aria-hidden="true" />{t('Delete tab')}</button>
    </>}>
      <p className="el-dialog-text">{tabs.length - 1 - children <= 0
        ? t('A document needs at least one tab.')
        : children
          ? t('This tab, its {n} sub-tabs and their version history will be deleted.', { n: children })
          : t('This tab and its version history will be deleted.')}</p>
    </Dialog>}
  </>
}

// Desktop: the "Document tabs" rail on the left of the editor.
export const TabsRail = memo(function TabsRail(props) {
  const { tabs, busy, onAdd } = props
  return <aside className="el-tabs-rail" aria-label={t('Document tabs')}>
    <div className="el-tabs-head">
      <strong>{t('Document tabs')}</strong>
      <button type="button" className="el-icon-btn is-small" aria-label={t('Add tab')} title={t('Add tab')} disabled={busy || tabs.length >= MAX_TABS} onClick={() => onAdd(null)}>
        <Plus size={18} />
      </button>
    </div>
    <TabList {...props} />
  </aside>
})

// Phone: the open tab's name at the top; the tabs open in a bottom sheet.
export function TabsSheetButton({ tabs, activeId, onOpenSheet }) {
  const active = tabs.find((tab) => tab.id === activeId)
  const count = tp('{n} tabs', tabs.length, { n: tabs.length })
  // The name gets the room; the count shrinks to a number badge.
  return <button type="button" className="el-tab-sheet-btn" aria-haspopup="dialog" onClick={onOpenSheet}>
    <span className="el-tab-sheet-name">{active?.title || t('Tab')}</span>
    <span className="el-tab-sheet-count" title={count}><span aria-hidden="true">{tabs.length}</span><span className="el-sr-only">{count}</span></span>
    <ChevronDown size={16} aria-hidden="true" className="el-tab-sheet-caret" />
  </button>
}

export function TabsSheet(props) {
  const { tabs, busy, onAdd, onClose, onOpen } = props
  return <Sheet label={t('Document tabs')} onClose={onClose} className="el-tabs-sheet">
    <div className="el-tabs-head">
      <strong>{t('Document tabs')}</strong>
      <button type="button" className="el-btn is-small" disabled={busy || tabs.length >= MAX_TABS} onClick={() => onAdd(null)}><Plus size={16} aria-hidden="true" />{t('Add tab')}</button>
    </div>
    <TabList {...props} sheet onOpen={(id) => { onOpen(id); onClose() }} />
  </Sheet>
}
