import { useRef, useState } from 'react'
import { ArrowDown, ArrowUp, Folder, FolderPlus, GripVertical, MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { t, tp } from '../i18n.js'
import { Menu, folderTree } from './ui.jsx'

export const ESSAY_DRAG_TYPE = 'application/x-naseeb-essay'
const FOLDER_DRAG_TYPE = 'application/x-naseeb-folder'

function moveItem(list, from, to) {
  const next = list.slice()
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

// Folder panel: one level of subfolders, drag to reorder (siblings only),
// a keyboard-friendly Reorder mode with up/down buttons, and essay drops.
// onReorder(parent, ids) persists a sibling order; onDropEssay(essayId, folderId).
export default function Folders({ folders, selected, onSelect, onReorder, onDropEssay, onCreate, onRename, onDelete, children }) {
  const [reordering, setReordering] = useState(false)
  const [drag, setDrag] = useState(null) // { id, parent }
  const [over, setOver] = useState(null) // { id, after }
  const [essayOver, setEssayOver] = useState(null)
  const [adding, setAdding] = useState(null) // { parent }
  const [announcement, setAnnouncement] = useState('')
  const listRef = useRef(null)
  const tree = folderTree(folders)

  const siblingsOf = (parent) => (parent == null ? tree : tree.find((folder) => folder.id === parent)?.children || [])

  function move(folder, delta) {
    const siblings = siblingsOf(folder.parent)
    const from = siblings.findIndex((item) => item.id === folder.id)
    const to = from + delta
    if (from < 0 || to < 0 || to >= siblings.length) return
    const ids = moveItem(siblings, from, to).map((item) => item.id)
    onReorder(folder.parent ?? null, ids)
    setAnnouncement(t('{name} moved to position {position} of {total}.', { name: folder.name, position: to + 1, total: siblings.length }))
    // Keep keyboard focus on the same control of the moved folder.
    const direction = delta < 0 ? 'up' : 'down'
    window.requestAnimationFrame(() => {
      const button = listRef.current?.querySelector(`[data-move="${folder.id}-${direction}"]`)
      const target = button && !button.disabled ? button : listRef.current?.querySelector(`[data-move="${folder.id}-${direction === 'up' ? 'down' : 'up'}"]`)
      target?.focus()
    })
  }

  function onDragStart(event, folder) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData(FOLDER_DRAG_TYPE, String(folder.id))
    event.dataTransfer.setData('text/plain', folder.name)
    setDrag({ id: folder.id, parent: folder.parent ?? null })
  }

  function onDragOver(event, folder) {
    const types = [...(event.dataTransfer?.types || [])]
    if (types.includes(ESSAY_DRAG_TYPE)) {
      event.preventDefault()
      event.dataTransfer.dropEffect = 'move'
      if (essayOver !== folder.id) setEssayOver(folder.id)
      return
    }
    if (!drag || (folder.parent ?? null) !== drag.parent || folder.id === drag.id) return
    event.preventDefault()
    const box = event.currentTarget.getBoundingClientRect()
    const after = event.clientY > box.top + box.height / 2
    if (over?.id !== folder.id || over?.after !== after) setOver({ id: folder.id, after })
  }

  function onDrop(event, folder) {
    event.preventDefault()
    const essayId = event.dataTransfer.getData(ESSAY_DRAG_TYPE)
    setEssayOver(null)
    if (essayId) { onDropEssay(Number(essayId), folder.id); return }
    if (!drag) return
    const siblings = siblingsOf(drag.parent)
    const from = siblings.findIndex((item) => item.id === drag.id)
    let to = siblings.findIndex((item) => item.id === folder.id)
    if (from < 0 || to < 0) return
    if (over?.after) to += 1
    if (from < to) to -= 1
    if (from !== to) {
      onReorder(drag.parent, moveItem(siblings, from, to).map((item) => item.id))
      setAnnouncement(t('{name} moved to position {position} of {total}.', { name: siblings[from].name, position: to + 1, total: siblings.length }))
    }
    setDrag(null)
    setOver(null)
  }

  const endDrag = () => { setDrag(null); setOver(null); setEssayOver(null) }

  function row(folder, index, siblings) {
    const isSelected = selected.kind === 'folder' && selected.id === folder.id
    const lineClass = over?.id === folder.id ? (over.after ? ' drop-after' : ' drop-before') : ''
    return <div key={folder.id}
      className={`el-folder${folder.parent != null ? ' is-child' : ''}${isSelected ? ' is-selected' : ''}${drag?.id === folder.id ? ' is-dragging' : ''}${essayOver === folder.id ? ' is-essay-over' : ''}${lineClass}`}
      draggable={!adding}
      onDragStart={(event) => onDragStart(event, folder)} onDragOver={(event) => onDragOver(event, folder)}
      onDragLeave={() => { if (essayOver === folder.id) setEssayOver(null) }}
      onDrop={(event) => onDrop(event, folder)} onDragEnd={endDrag}>
      <span className={`el-grip${reordering ? ' is-active' : ''}`} aria-hidden="true"><GripVertical size={14} /></span>
      <button type="button" className="el-folder-name" aria-current={isSelected ? 'true' : undefined} onClick={() => onSelect({ kind: 'folder', id: folder.id })}>
        <Folder size={16} aria-hidden="true" /><span>{folder.name}</span>
      </button>
      {reordering
        ? <span className="el-move-btns">
          <button type="button" className="el-mini-btn" data-move={`${folder.id}-up`} disabled={index === 0} aria-label={t('Move {name} up', { name: folder.name })} onClick={() => move(folder, -1)}><ArrowUp size={14} /></button>
          <button type="button" className="el-mini-btn" data-move={`${folder.id}-down`} disabled={index === siblings.length - 1} aria-label={t('Move {name} down', { name: folder.name })} onClick={() => move(folder, 1)}><ArrowDown size={14} /></button>
        </span>
        : <>
          <span className="el-count" aria-label={tp('{count} essays', folder.essay_count ?? 0, { count: folder.essay_count ?? 0 })}>{folder.essay_count ?? 0}</span>
          <Menu className="el-folder-menu" label={t('Folder actions for {name}', { name: folder.name })} icon={<MoreHorizontal size={16} />} buttonClassName="el-mini-btn" items={[
            { label: t('Rename'), icon: <Pencil size={15} />, onSelect: () => onRename(folder) },
            folder.parent == null && { label: t('New subfolder'), icon: <FolderPlus size={15} />, onSelect: () => setAdding({ parent: folder.id }) },
            { divider: true },
            { label: t('Delete folder'), icon: <Trash2 size={15} />, danger: true, onSelect: () => onDelete(folder) },
          ]} />
        </>}
    </div>
  }

  return <div className="el-folders">
    <div className="el-folders-head">
      <h2 className="el-folders-title">{t('Folders')}</h2>
      {folders.length > 1 && <button type="button" className={`el-chip-btn${reordering ? ' is-on' : ''}`} aria-pressed={reordering} onClick={() => setReordering((value) => !value)}>
        {reordering ? t('Done') : t('Reorder')}
      </button>}
      <button type="button" className="el-icon-btn is-small" aria-label={t('New folder')} onClick={() => setAdding({ parent: null })}><FolderPlus size={16} /></button>
    </div>
    {children}
    {reordering && <p className="el-reorder-hint">{t('Drag a folder by its handle, or use the arrows. Your order is saved automatically.')}</p>}
    <div ref={listRef} className="el-folder-list">
      {tree.map((folder, index) => <div key={folder.id} className="el-folder-group">
        {row(folder, index, tree)}
        {folder.children.length > 0 && <div className="el-folder-children">{folder.children.map((child, childIndex) => row(child, childIndex, folder.children))}</div>}
        {adding?.parent === folder.id && <NewFolderInput onDone={(name) => { setAdding(null); if (name) onCreate(name, folder.id) }} child />}
      </div>)}
    </div>
    {adding?.parent === null && <NewFolderInput onDone={(name) => { setAdding(null); if (name) onCreate(name, null) }} />}
    <span className="el-sr-only" role="status" aria-live="polite">{announcement}</span>
  </div>
}

function NewFolderInput({ onDone, child = false }) {
  const [name, setName] = useState('')
  const done = useRef(false)
  const finish = (value) => {
    if (done.current) return
    done.current = true
    onDone(value.trim().slice(0, 120))
  }
  return <form className={`el-new-folder${child ? ' is-child' : ''}`} onSubmit={(event) => { event.preventDefault(); finish(name) }}>
    <Folder size={16} aria-hidden="true" />
    <input autoFocus className="el-input is-small" aria-label={child ? t('Subfolder name') : t('Folder name')} placeholder={child ? t('Subfolder name') : t('Folder name')}
      value={name} maxLength={120} onChange={(event) => setName(event.target.value)}
      onKeyDown={(event) => { if (event.key === 'Escape') finish('') }} onBlur={() => finish(name)} />
  </form>
}
