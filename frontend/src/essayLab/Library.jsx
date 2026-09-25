import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2, ChevronRight, Cloud, Copy, FileText, Folder, FolderInput, History, Inbox, LayoutGrid, List,
  MoreHorizontal, PenLine, Plus, RotateCcw, Sparkles, Trash2, X,
} from 'lucide-react'
import { t, tp } from '../i18n.js'
import Folders, { ESSAY_DRAG_TYPE } from './Folders.jsx'
import { Dialog, FolderSelect, Menu, ProgressBar, folderPath } from './ui.jsx'
import { essayLabApi, essayTypeName } from './essayLabApi.js'
import { STATUS_LABELS, relativeTime } from './format.js'
import { SCORE_KEYS, scoreBand } from './coachModel.js'
import { SharedBadge, useEssaySharing } from './ShareControl.jsx'

const LAYOUT_KEY = 'naseeb-essay-lab-layout'
const STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'draft', label: 'Drafts', match: (status) => status === 'draft' || !status },
  { id: 'counselor', label: 'With counselor', match: (status) => status === 'reviewing' || status === 'needs_revision' },
  { id: 'approved', label: 'Approved', match: (status) => status === 'approved' },
]

function readLayout() {
  try { return localStorage.getItem(LAYOUT_KEY) === 'list' ? 'list' : 'grid' } catch { return 'grid' }
}

const byRecent = (a, b) => Date.parse(b.last_edited_at || b.updated_at || 0) - Date.parse(a.last_edited_at || a.updated_at || 0)

export default function Library({ user, essays, folders, loading, error, setEssays, setFolders, refresh, notify, onOpen, onNew }) {
  const [selected, setSelected] = useState({ kind: 'all' })
  const [statusFilter, setStatusFilter] = useState('all')
  const [layout, setLayout] = useState(readLayout)
  const [trash, setTrash] = useState({ loading: false, items: [] })
  const [dialog, setDialog] = useState(null)
  // Phones show the folder panel as a sheet; wider screens keep it docked.
  const [panelOpen, setPanelOpen] = useState(false)

  useEffect(() => { try { localStorage.setItem(LAYOUT_KEY, layout) } catch { /* ignore */ } }, [layout])

  const loadTrash = useCallback(async () => {
    setTrash((current) => ({ ...current, loading: true }))
    try {
      const items = await essayLabApi.listEssays({ trashed: 1 })
      setTrash({ loading: false, items: items || [] })
    } catch (err) {
      setTrash({ loading: false, items: [], error: err?.message })
    }
  }, [])

  useEffect(() => { if (selected.kind === 'trash') loadTrash() }, [selected.kind, loadTrash])

  const folderIds = useMemo(() => {
    if (selected.kind !== 'folder') return null
    return new Set([selected.id, ...folders.filter((folder) => folder.parent === selected.id).map((folder) => folder.id)])
  }, [selected, folders])

  const visible = useMemo(() => {
    const status = STATUS_FILTERS.find((item) => item.id === statusFilter)
    return essays
      .filter((essay) => !folderIds || folderIds.has(essay.folder))
      .filter((essay) => !status?.match || status.match(essay.status))
      .sort(byRecent)
  }, [essays, folderIds, statusFilter])

  const pickup = useMemo(() => {
    if (selected.kind !== 'all') return null
    return [...essays].filter((essay) => essay.last_edited_at && (essay.word_count ?? 0) > 0).sort(byRecent)[0] || null
  }, [essays, selected.kind])

  const select = useCallback((next) => { setSelected(next); setPanelOpen(false) }, [])

  // --- essay actions ------------------------------------------------------
  const patchLocal = (updated) => setEssays((list) => list.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)))

  async function moveEssay(essay, folder) {
    const previous = essay.folder
    patchLocal({ id: essay.id, folder })
    try {
      patchLocal(await essayLabApi.updateEssay(essay.id, { folder }))
      notify(folder ? t('Moved to {folder}.', { folder: folderPath(folders, folder) }) : t('Moved out of the folder.'))
      refreshFolders()
    } catch (err) {
      patchLocal({ id: essay.id, folder: previous })
      notify(err?.message || t('Could not move the essay.'), 'error')
    }
  }

  async function trashEssay(essay) {
    setEssays((list) => list.filter((item) => item.id !== essay.id))
    try {
      await essayLabApi.trashEssay(essay.id)
      notify(t('“{title}” moved to trash.', { title: essay.title }))
      refreshFolders()
    } catch (err) {
      setEssays((list) => [essay, ...list])
      notify(err?.message || t('Could not move the essay to trash.'), 'error')
    }
  }

  async function restoreEssay(essay) {
    try {
      const restored = await essayLabApi.restoreEssay(essay.id)
      setTrash((current) => ({ ...current, items: current.items.filter((item) => item.id !== essay.id) }))
      setEssays((list) => [{ ...essay, ...restored, trashed_at: null }, ...list.filter((item) => item.id !== essay.id)])
      notify(t('“{title}” restored.', { title: essay.title }))
      refreshFolders()
    } catch (err) {
      notify(err?.message || t('Could not restore the essay.'), 'error')
    }
  }

  async function deleteForever(essay) {
    try {
      await essayLabApi.deleteEssay(essay.id)
      setTrash((current) => ({ ...current, items: current.items.filter((item) => item.id !== essay.id) }))
      notify(t('Deleted forever.'))
    } catch (err) {
      notify(err?.message || t('Could not delete the essay.'), 'error')
    }
  }

  async function refreshFolders() {
    try { setFolders(await essayLabApi.folders()) } catch { /* counts will catch up */ }
  }

  // --- folder actions -----------------------------------------------------
  async function reorderFolders(parent, ids) {
    const previous = folders
    setFolders((list) => list.map((folder) => {
      const position = ids.indexOf(folder.id)
      return position >= 0 && (folder.parent ?? null) === parent ? { ...folder, position } : folder
    }))
    try {
      // The server needs every folder at this level once and answers with all folders.
      const saved = await essayLabApi.orderFolders(parent, ids)
      if (Array.isArray(saved)) setFolders(saved)
    } catch (err) {
      setFolders(previous)
      notify(err?.message || t('Could not save the folder order.'), 'error')
    }
  }

  async function createFolder(name, parent) {
    if (!name) return
    try {
      const folder = await essayLabApi.createFolder(parent ? { name, parent } : { name })
      setFolders((list) => [...list, folder])
    } catch (err) {
      notify(err?.message || t('Could not create the folder.'), 'error')
    }
  }

  async function renameFolder(folder, name) {
    try {
      const saved = await essayLabApi.updateFolder(folder.id, { name })
      setFolders((list) => list.map((item) => (item.id === folder.id ? { ...item, ...saved } : item)))
    } catch (err) {
      notify(err?.message || t('Could not rename the folder.'), 'error')
    }
  }

  async function deleteFolder(folder) {
    try {
      await essayLabApi.deleteFolder(folder.id)
      if (selected.kind === 'folder' && selected.id === folder.id) setSelected({ kind: 'all' })
      await refresh()
      notify(t('Folder deleted. Its essays are safe.'))
    } catch (err) {
      notify(err?.message || t('Could not delete the folder.'), 'error')
    }
  }

  const sharing = useEssaySharing({ notify, onSaved: patchLocal })
  const essayMenu = (essay) => [
    { label: t('Open'), icon: <FileText size={15} />, onSelect: () => onOpen(essay.id) },
    sharing.menuItem(essay),
    { label: t('Rename'), icon: <PenLine size={15} />, onSelect: () => setDialog({ kind: 'rename', essay }) },
    { label: t('Make a copy for another university'), icon: <Copy size={15} />, onSelect: () => setDialog({ kind: 'copy', essay }) },
    { label: t('Move to folder…'), icon: <FolderInput size={15} />, onSelect: () => setDialog({ kind: 'move', essay }) },
    { label: t('Version history'), icon: <History size={15} />, onSelect: () => onOpen(essay.id, { panel: 'history' }) },
    { divider: true },
    { label: t('Move to trash'), icon: <Trash2 size={15} />, danger: true, onSelect: () => trashEssay(essay) },
  ]

  const title = selected.kind === 'trash' ? t('Trash') : selected.kind === 'folder' ? folderPath(folders, selected.id) : t('My essays')
  const newEssayFolder = selected.kind === 'folder' ? selected.id : null

  return <div className="el-library">
    <main className="el-main">
      {error && <div className="el-alert is-error" role="alert"><span>{error}</span><button type="button" className="el-btn is-small" onClick={refresh}>{t('Retry')}</button></div>}

      {pickup && <PickupCard essay={pickup} onOpen={onOpen} />}

      {selected.kind === 'trash'
        ? <TrashList trash={trash} onRestore={restoreEssay} onDelete={(essay) => setDialog({ kind: 'delete-forever', essay })} onBack={() => select({ kind: 'all' })} />
        : <section className="el-section" aria-labelledby="el-essays-heading">
          <div className="el-section-head">
            {selected.kind === 'folder' && <><button type="button" className="el-crumb" onClick={() => select({ kind: 'all' })}>{t('My essays')}</button><ChevronRight size={15} aria-hidden="true" className="el-crumb-sep" /></>}
            <h2 id="el-essays-heading">{title}</h2>
            <div className="el-chips" role="group" aria-label={t('Filter by status')}>
              {STATUS_FILTERS.map((filter) => <button key={filter.id} type="button" className={`el-chip${statusFilter === filter.id ? ' is-on' : ''}`} aria-pressed={statusFilter === filter.id} onClick={() => setStatusFilter(filter.id)}>{t(filter.label)}</button>)}
            </div>
            <div className="el-section-tools">
              <div className="el-toggle" role="group" aria-label={t('Layout')}>
                <button type="button" aria-label={t('Grid view')} aria-pressed={layout === 'grid'} className={layout === 'grid' ? 'is-on' : ''} onClick={() => setLayout('grid')}><LayoutGrid size={17} /></button>
                <button type="button" aria-label={t('List view')} aria-pressed={layout === 'list'} className={layout === 'list' ? 'is-on' : ''} onClick={() => setLayout('list')}><List size={17} /></button>
              </div>
              <button type="button" className="el-btn el-folders-toggle" aria-expanded={panelOpen} aria-controls="el-folder-panel" onClick={() => setPanelOpen(true)}><Folder size={16} aria-hidden="true" />{t('Folders')}</button>
              <button type="button" className="el-btn is-primary el-new-essay" onClick={() => onNew(newEssayFolder)}><Plus size={17} aria-hidden="true" />{t('New essay')}</button>
            </div>
          </div>

          {loading && !essays.length
            ? <div className="el-grid" aria-busy="true">{[0, 1, 2].map((key) => <div key={key} className="el-card is-skeleton" />)}</div>
            : layout === 'grid'
              ? <div className="el-grid">{visible.map((essay) => <EssayCard key={essay.id} essay={essay} onOpen={onOpen} menu={essayMenu(essay)} />)}</div>
              : <EssayTable essays={visible} folders={folders} onOpen={onOpen} menuFor={essayMenu} />}
          {!loading && !visible.length && <div className="el-empty-state">
            <p>{selected.kind === 'folder' ? t('No essays in this folder yet. Start one, or move an essay here from its menu.') : essays.length ? t('Nothing here yet.') : t('Your essays will appear here. Start with a new essay.')}</p>
            <button type="button" className="el-btn is-primary" onClick={() => onNew(newEssayFolder)}><Plus size={17} aria-hidden="true" />{t('New essay')}</button>
          </div>}
        </section>}
    </main>

    {panelOpen && <button type="button" className="el-panel-backdrop" aria-label={t('Close folders')} onClick={() => setPanelOpen(false)} />}
    <aside id="el-folder-panel" className={`el-panel${panelOpen ? ' is-open' : ''}`} aria-label={t('Essay folders')}>
      <div className="el-panel-card">
        <div className="el-panel-sheet-head">
          <span className="el-sheet-grabber" aria-hidden="true" />
          <button type="button" className="el-icon-btn is-small" aria-label={t('Close folders')} onClick={() => setPanelOpen(false)}><X size={18} /></button>
        </div>
        <Folders folders={folders} selected={selected} onSelect={select} onReorder={reorderFolders}
          onDropEssay={(essayId, folderId) => { const essay = essays.find((item) => item.id === essayId); if (essay && essay.folder !== folderId) moveEssay(essay, folderId) }}
          onCreate={createFolder} onRename={(folder) => setDialog({ kind: 'rename-folder', folder })} onDelete={(folder) => setDialog({ kind: 'delete-folder', folder })}>
          <button type="button" className={`el-nav-item${selected.kind === 'all' ? ' is-selected' : ''}`} aria-current={selected.kind === 'all' ? 'page' : undefined} onClick={() => select({ kind: 'all' })}>
            <FileText size={17} aria-hidden="true" />{t('All essays')}<span className="el-count">{essays.length}</span>
          </button>
        </Folders>
      </div>
      <div className="el-panel-card is-compact">
        <button type="button" className={`el-nav-item${selected.kind === 'trash' ? ' is-selected' : ''}`} aria-current={selected.kind === 'trash' ? 'page' : undefined} onClick={() => select({ kind: 'trash' })}>
          <Trash2 size={17} aria-hidden="true" />{t('Trash')}
        </button>
      </div>
      <div className="el-autosave-note"><Cloud size={16} aria-hidden="true" /><span>{t('Everything is saved automatically')}</span></div>
    </aside>

    {dialog?.kind === 'rename' && <TextDialog title={t('Rename essay')} label={t('Title')} initial={dialog.essay.title} max={220} onClose={() => setDialog(null)}
      onSubmit={async (value) => {
        setDialog(null)
        try { patchLocal(await essayLabApi.updateEssay(dialog.essay.id, { title: value })) } catch (err) { notify(err?.message || t('Could not rename.'), 'error') }
      }} />}
    {dialog?.kind === 'rename-folder' && <TextDialog title={t('Rename folder')} label={t('Folder name')} initial={dialog.folder.name} max={120} onClose={() => setDialog(null)}
      onSubmit={(value) => { setDialog(null); renameFolder(dialog.folder, value) }} />}
    {dialog?.kind === 'move' && <MoveDialog essay={dialog.essay} folders={folders} onClose={() => setDialog(null)} onMove={(folder) => { setDialog(null); moveEssay(dialog.essay, folder) }} />}
    {dialog?.kind === 'copy' && <CopyDialog essay={dialog.essay} folders={folders} onClose={() => setDialog(null)} notify={notify}
      onCopied={(copy) => { setDialog(null); setEssays((list) => [copy, ...list]); refreshFolders(); notify(t('Copy created.')); onOpen(copy.id) }} />}
    {dialog?.kind === 'delete-folder' && <ConfirmDialog title={t('Delete “{name}”?', { name: dialog.folder.name })} confirm={t('Delete folder')}
      body={t('Essays in this folder move to “No folder”, and its subfolders move up a level. No writing is deleted.')}
      onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); deleteFolder(dialog.folder) }} />}
    {dialog?.kind === 'delete-forever' && <ConfirmDialog title={t('Delete “{title}” forever?', { title: dialog.essay.title })} confirm={t('Delete forever')}
      body={t('This essay and its version history will be removed for good. This cannot be undone.')}
      onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); deleteForever(dialog.essay) }} />}
    {sharing.dialog}
  </div>
}

function PickupCard({ essay, onOpen }) {
  const [check, setCheck] = useState(undefined)
  useEffect(() => {
    let alive = true
    essayLabApi.latestDepthCheck(essay.id).then((result) => { if (alive) setCheck(result || null) }, () => { if (alive) setCheck(null) })
    return () => { alive = false }
  }, [essay.id])
  const limit = essay.word_limit
  const words = essay.word_count ?? 0
  return <section className="el-pickup" aria-labelledby="el-pickup-title">
    <div className="el-pickup-main">
      <span className="el-eyebrow is-accent">{t('PICK UP WHERE YOU LEFT OFF')}</span>
      <h1 id="el-pickup-title">{essay.title}</h1>
      {essay.preview && <p className="el-pickup-text">{essay.preview}{(essay.word_count ?? 0) > 30 ? '…' : ''}<span className="el-caret" aria-hidden="true" /></p>}
      <div className="el-pickup-meta">
        <span>{t('Last edited {when}', { when: relativeTime(essay.last_edited_at) })}</span>
        <span className="el-pickup-words">{limit ? tp('{count} / {limit} words', limit, { count: words, limit }) : tp('{count} words', words, { count: words })}
          {limit ? <ProgressBar ratio={words / limit} over={words > limit} /> : null}</span>
      </div>
      <div className="el-pickup-actions">
        <button type="button" className="el-btn is-primary is-large" onClick={() => onOpen(essay.id)}><PenLine size={17} aria-hidden="true" />{t('Continue writing')}</button>
        <button type="button" className="el-btn is-large" onClick={() => onOpen(essay.id, { focus: true })}>{t('Just write (focus mode)')}</button>
      </div>
    </div>
    {check && check.result?.scores && <div className="el-pickup-check">
      <div className="el-pickup-check-title"><Sparkles size={16} aria-hidden="true" />{t('Last depth check · {when}', { when: relativeTime(check.created_at) })}</div>
      <dl>
        {SCORE_KEYS.slice(0, 3).map((score) => {
          const band = scoreBand(check.result.scores[score.key])
          return <div key={score.key}><dt>{t(score.label)}</dt><dd className={`el-badge is-${band.tone}`}>{t(band.label)}</dd></div>
        })}
      </dl>
      <button type="button" className="el-link" onClick={() => onOpen(essay.id, { panel: 'coach' })}>{t('Open full report →')}</button>
    </div>}
  </section>
}

function statusBadge(status) {
  const tone = status === 'approved' ? 'good' : status === 'reviewing' ? 'info' : status === 'needs_revision' ? 'warn' : 'neutral'
  return <span className={`el-badge is-${tone}`}>{t(STATUS_LABELS[status] || 'Draft')}</span>
}

function wordsMeta(essay) {
  const words = essay.word_count ?? 0
  return essay.word_limit ? `${words} / ${essay.word_limit}` : tp('{count} words', words, { count: words })
}

function EssayCard({ essay, onOpen, menu }) {
  const dragStart = (event) => {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData(ESSAY_DRAG_TYPE, String(essay.id))
    event.dataTransfer.setData('text/plain', essay.title)
  }
  return <article className="el-card" draggable onDragStart={dragStart}>
    <button type="button" className="el-card-open" onClick={() => onOpen(essay.id)} aria-label={t('Open {title}', { title: essay.title })}>
      <div className="el-paper" aria-hidden="true">{essay.preview || <em>{t('Empty page')}</em>}</div>
      <div className="el-card-body">
        <strong>{essay.title}</strong>
        <span className="el-card-subrow"><span className="el-card-sub">{essay.university_name || t(essayTypeName(essay.essay_type))}</span><SharedBadge essay={essay} /></span>
        <div className="el-card-meta"><span>{wordsMeta(essay)} · {relativeTime(essay.last_edited_at || essay.updated_at)}</span>{statusBadge(essay.status)}</div>
      </div>
    </button>
    <Menu className="el-card-menu" label={t('More actions for {title}', { title: essay.title })} icon={<MoreHorizontal size={18} />} items={menu} />
  </article>
}

function EssayTable({ essays, folders, onOpen, menuFor }) {
  return <div className="el-table" role="table" aria-label={t('Essays')}>
    <div className="el-row is-head" role="row">
      <span role="columnheader">{t('Title')}</span><span role="columnheader">{t('Type')}</span><span role="columnheader">{t('Folder')}</span>
      <span role="columnheader">{t('Words')}</span><span role="columnheader">{t('Edited')}</span><span role="columnheader"><span className="el-sr-only">{t('Actions')}</span></span>
    </div>
    {essays.map((essay) => <div key={essay.id} className="el-row" role="row" draggable
      onDragStart={(event) => { event.dataTransfer.setData(ESSAY_DRAG_TYPE, String(essay.id)); event.dataTransfer.setData('text/plain', essay.title) }}>
      <span role="cell"><button type="button" className="el-row-title" onClick={() => onOpen(essay.id)}>{essay.title}</button> <SharedBadge essay={essay} /></span>
      <span role="cell">{t(essayTypeName(essay.essay_type))}</span>
      <span role="cell">{essay.folder ? folderPath(folders, essay.folder) : '—'}</span>
      <span role="cell">{wordsMeta(essay)}</span>
      <span role="cell">{relativeTime(essay.last_edited_at || essay.updated_at)}</span>
      <span role="cell"><Menu label={t('More actions for {title}', { title: essay.title })} icon={<MoreHorizontal size={18} />} items={menuFor(essay)} /></span>
    </div>)}
  </div>
}

function TrashList({ trash, onRestore, onDelete, onBack }) {
  return <section className="el-section" aria-labelledby="el-trash-heading">
    <div className="el-section-head">
      <button type="button" className="el-crumb" onClick={onBack}>{t('My essays')}</button><ChevronRight size={15} aria-hidden="true" className="el-crumb-sep" />
      <h2 id="el-trash-heading">{t('Trash')}</h2>
    </div>
    <p className="el-small">{t('Essays in the trash can be restored with their full history.')}</p>
    {trash.loading && <p className="el-empty" role="status">{t('Loading…')}</p>}
    {trash.error && <div className="el-alert is-error" role="alert">{trash.error}</div>}
    {!trash.loading && !trash.items.length && <p className="el-empty"><Inbox size={18} aria-hidden="true" /> {t('The trash is empty.')}</p>}
    <ul className="el-trash">
      {trash.items.map((essay) => <li key={essay.id}>
        <div><strong>{essay.title}</strong><span className="el-small">{t('Trashed {when}', { when: relativeTime(essay.trashed_at) })} · {wordsMeta(essay)}</span></div>
        <button type="button" className="el-btn is-small" onClick={() => onRestore(essay)}><RotateCcw size={15} aria-hidden="true" />{t('Restore')}</button>
        <button type="button" className="el-btn is-small is-danger" onClick={() => onDelete(essay)}>{t('Delete forever')}</button>
      </li>)}
    </ul>
  </section>
}

function TextDialog({ title, label, initial = '', max = 220, onSubmit, onClose }) {
  const [value, setValue] = useState(initial)
  const inputRef = useRef(null)
  useEffect(() => { inputRef.current?.select() }, [])
  const footer = <>
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="submit" form="el-text-dialog" className="el-btn is-primary" disabled={!value.trim()}>{t('Save')}</button>
  </>
  return <Dialog title={title} onClose={onClose} footer={footer}>
    <form id="el-text-dialog" className="el-form" onSubmit={(event) => { event.preventDefault(); if (value.trim()) onSubmit(value.trim().slice(0, max)) }}>
      <label className="el-label" htmlFor="el-text-input">{label}</label>
      <input ref={inputRef} id="el-text-input" data-autofocus className="el-input" value={value} maxLength={max} onChange={(event) => setValue(event.target.value)} />
    </form>
  </Dialog>
}

function MoveDialog({ essay, folders, onMove, onClose }) {
  const [folder, setFolder] = useState(essay.folder ?? null)
  const footer = <>
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="button" className="el-btn is-primary" onClick={() => onMove(folder)}>{t('Move')}</button>
  </>
  return <Dialog title={t('Move “{title}”', { title: essay.title })} onClose={onClose} footer={footer}>
    <label className="el-label" htmlFor="el-move-folder">{t('Folder')}</label>
    <FolderSelect id="el-move-folder" folders={folders} value={folder} onChange={setFolder} />
  </Dialog>
}

function CopyDialog({ essay, folders, onCopied, onClose, notify }) {
  const [university, setUniversity] = useState('')
  const [title, setTitle] = useState('')
  const [folder, setFolder] = useState(essay.folder ?? null)
  const [saving, setSaving] = useState(false)
  const suggested = university.trim() ? `${university.trim()} — ${essayTypeName(essay.essay_type)}` : t('{title} (copy)', { title: essay.title })
  async function submit(event) {
    event.preventDefault()
    setSaving(true)
    try {
      const payload = { title: (title.trim() || suggested).slice(0, 220), folder }
      if (university.trim()) payload.university_name = university.trim().slice(0, 220)
      onCopied(await essayLabApi.duplicateEssay(essay.id, payload))
    } catch (err) {
      notify(err?.message || t('Could not copy the essay.'), 'error')
      setSaving(false)
    }
  }
  const footer = <>
    <button type="button" className="el-btn" onClick={onClose}>{t('Cancel')}</button>
    <button type="submit" form="el-copy" className="el-btn is-primary" disabled={saving} aria-busy={saving}>{t('Make a copy')}</button>
  </>
  return <Dialog title={t('Make a copy for another university')} onClose={onClose} footer={footer}>
    <form id="el-copy" className="el-form" onSubmit={submit}>
      <p className="el-small">{t('The copy keeps your text so you can adapt it. The original stays as it is.')}</p>
      <label className="el-label" htmlFor="el-copy-uni">{t('University')}</label>
      <input id="el-copy-uni" data-autofocus className="el-input" value={university} maxLength={220} onChange={(event) => setUniversity(event.target.value)} />
      <label className="el-label" htmlFor="el-copy-title">{t('Title')}</label>
      <input id="el-copy-title" className="el-input" placeholder={suggested} value={title} maxLength={220} onChange={(event) => setTitle(event.target.value)} />
      <label className="el-label" htmlFor="el-copy-folder">{t('Folder')}</label>
      <FolderSelect id="el-copy-folder" folders={folders} value={folder} onChange={setFolder} />
    </form>
  </Dialog>
}

function ConfirmDialog({ title, body, confirm, onConfirm, onClose }) {
  const footer = <>
    <button type="button" className="el-btn" data-autofocus onClick={onClose}>{t('Cancel')}</button>
    <button type="button" className="el-btn is-danger-solid" onClick={onConfirm}><CheckCircle2 size={16} aria-hidden="true" />{confirm}</button>
  </>
  return <Dialog title={title} onClose={onClose} footer={footer}><p className="el-dialog-text">{body}</p></Dialog>
}

